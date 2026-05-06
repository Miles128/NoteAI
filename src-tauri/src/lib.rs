use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex as StdMutex};
use tauri::{Emitter, Manager, LogicalPosition};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{Mutex as AsyncMutex, oneshot};

pub struct AppState {
    python_stdin: Arc<AsyncMutex<Option<ChildStdin>>>,
    pending_requests: StdMutex<HashMap<String, oneshot::Sender<serde_json::Value>>>,
    workspace_path: StdMutex<Option<String>>,
    python_child: Arc<AsyncMutex<Option<Child>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            python_stdin: Arc::new(AsyncMutex::new(None)),
            pending_requests: StdMutex::new(HashMap::new()),
            workspace_path: StdMutex::new(None),
            python_child: Arc::new(AsyncMutex::new(None)),
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
struct PyRequest {
    id: String,
    method: String,
    params: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct PyResponse {
    id: String,
    result: Option<serde_json::Value>,
    error: Option<String>,
}

async fn start_python_sidecar(app: tauri::AppHandle) -> Result<(), String> {
    let python_path = find_python()?;

    let script_path = {
        let exe_dir = std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("No parent dir")?
            .to_path_buf();

        let candidates = vec![
            exe_dir.join("..").join("python").join("main.py"),
            exe_dir.join("..").join("..").join("python").join("main.py"),
            exe_dir.join("..").join("..").join("..").join("python").join("main.py"),
            std::path::PathBuf::from("python/main.py"),
        ];

        let mut found = None;
        for candidate in candidates {
            let canonicalized = candidate.canonicalize().ok();
            if let Some(ref path) = canonicalized {
                if path.exists() {
                    found = Some(path.clone());
                    break;
                }
            }
        }

        match found {
            Some(p) => p,
            None => return Err("Python sidecar main.py not found".into()),
        }
    };

    let mut child = Command::new(&python_path)
        .arg(&script_path)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start Python: {}", e))?;

    let stdin = child.stdin.take();
    let stdout = child.stdout.take().ok_or("Failed to capture Python stdout")?;
    let stderr = child.stderr.take().ok_or("Failed to capture Python stderr")?;

    let app_clone = app.clone();
    tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if let Ok(resp) = serde_json::from_str::<PyResponse>(&line) {
                if resp.id == "event" {
                    if let Some(result) = resp.result {
                        eprintln!("[Rust] Emitting python-event: {:?}", result);
                        match app_clone.emit("python-event", &result) {
                            Ok(_) => {}
                            Err(e) => eprintln!("[Rust] Failed to emit event: {}", e),
                        }
                    }
                } else {
                    let state = app_clone.state::<AppState>();
                    let mut pending = state.pending_requests.lock().unwrap();
                    if let Some(tx) = pending.remove(&resp.id) {
                        let value = if let Some(result) = resp.result {
                            result
                        } else if let Some(error) = resp.error {
                            serde_json::json!({"success": false, "message": error})
                        } else {
                            serde_json::Value::Null
                        };
                        let _ = tx.send(value);
                    }
                }
            } else {
                eprintln!("[Rust] Failed to parse Python stdout: {}", &line[..line.len().min(200)]);
            }
        }
    });

    tokio::spawn(async move {
        let reader = BufReader::new(stderr);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            eprintln!("[Python] {}", line);
        }
    });

    let state = app.state::<AppState>();
    *state.python_stdin.lock().await = stdin;
    *state.python_child.lock().await = Some(child);

    Ok(())
}

fn find_python() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("No parent dir")?
        .to_path_buf();

    let mut candidates: Vec<PathBuf> = vec![];

    let mut dir = exe_dir.clone();
    for _ in 0..6 {
        candidates.push(dir.join(".venv").join("bin").join("python"));
        if let Some(parent) = dir.parent() {
            dir = parent.to_path_buf();
        } else {
            break;
        }
    }

    for cmd in &["python3", "python"] {
        if let Ok(path) = which::which(cmd) {
            candidates.push(path);
        }
    }

    for candidate in candidates {
        if candidate.exists() {
            return Ok(candidate);
        }
    }

    Err("Python not found. Please install Python 3.".into())
}

async fn call_python(
    state: &tauri::State<'_, AppState>,
    method: &str,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let id = uuid::Uuid::new_v4().to_string();

    let request = PyRequest {
        id: id.clone(),
        method: method.to_string(),
        params,
    };

    let (tx, rx) = oneshot::channel();
    {
        let mut pending = state.pending_requests.lock().unwrap();
        pending.insert(id.clone(), tx);
    }

    {
        let mut stdin_guard = state.python_stdin.lock().await;
        match stdin_guard.as_mut() {
            Some(stdin) => {
                let mut json_line = serde_json::to_string(&request).map_err(|e| e.to_string())?;
                json_line.push('\n');
                stdin
                    .write_all(json_line.as_bytes())
                    .await
                    .map_err(|e| format!("Write failed: {}", e))?;
                stdin
                    .flush()
                    .await
                    .map_err(|e| format!("Flush failed: {}", e))?;
            }
            None => return Err("Python process not running".into()),
        }
    }

    match tokio::time::timeout(std::time::Duration::from_secs(120), rx).await {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(_)) => Err("Python response channel closed".into()),
        Err(_) => {
            let mut pending = state.pending_requests.lock().unwrap();
            pending.remove(&id);
            Err("Python request timed out".into())
        }
    }
}

static ALLOWED_PYTHON_METHODS: &[&str] = &[
    "set_workspace_path", "get_workspace_status", "get_workspace_tree", "on_file_selected",
    "read_file_raw", "delete_file", "move_file", "search_files", "auto_assign_topic",
    "batch_auto_assign_topics", "add_tag_to_file",
    "resolve_topic", "get_relation_graph", "discover_links", "llm_rewrite", "llm_rewrite_stream", "llm_rewrite_apply",
    "start_note_integration",
    "save_api_config", "test_api_connection",
    "ai_topic_analyze", "ai_topic_survey", "apply_topic_suggestion",
    "auto_tag_files",
    "get_file_preview", "can_preview_file", "save_file_content",
    "get_all_tags", "get_topic_tree", "save_tags_md", "ensure_tags_md",
    "create_topic", "create_tag", "get_pending_topics", "rename_topic",
    "delete_topic", "rename_tag", "delete_tag", "move_file_to_topic",
    "get_api_config", "get_ui_config", "save_ui_config",
    "get_theme_preference", "save_theme_preference",
    "import_files",
    "start_web_download", "start_file_conversion", "extract_topics",
    "refresh_log", "get_backlinks", "confirm_link", "reject_link",
    "confirm_all_links", "sync_wiki_with_files",
    "check_workspace_path_valid", "clear_saved_workspace", "reveal_in_finder",
];

#[tauri::command]
async fn py_call(
    state: tauri::State<'_, AppState>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if !ALLOWED_PYTHON_METHODS.contains(&method.as_str()) {
        return Err(format!("Method not allowed: {}", method));
    }
    call_python(&state, &method, params).await
}

#[tauri::command]
async fn open_folder_dialog(
    app: tauri::AppHandle,
) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let folder = app
        .dialog()
        .file()
        .blocking_pick_folder();
    Ok(folder.map(|p| p.to_string()))
}

#[tauri::command]
async fn open_file_dialog(
    app: tauri::AppHandle,
) -> Result<Option<Vec<String>>, String> {
    use tauri_plugin_dialog::DialogExt;
    let files = app
        .dialog()
        .file()
        .add_filter("文档文件", &["pdf", "docx", "doc", "pptx", "ppt", "html", "htm", "txt"])
        .blocking_pick_files();
    Ok(files.map(|paths| paths.into_iter().map(|p| p.to_string()).collect()))
}

fn validate_workspace_path(state: &tauri::State<'_, AppState>, path: &str) -> Result<String, String> {
    let workspace = state.workspace_path.lock().unwrap();
    let workspace = workspace.as_ref().ok_or("Workspace not set")?;
    let workspace_abs = std::path::Path::new(workspace).canonicalize()
        .map_err(|e| format!("Invalid workspace: {}", e))?;
    let target = std::path::Path::new(path);
    let target_abs = if target.is_absolute() {
        target.to_path_buf()
    } else {
        workspace_abs.join(path)
    };
    let resolved = target_abs.canonicalize()
        .map_err(|e| format!("Failed to resolve path: {}", e))?;
    resolved.strip_prefix(&workspace_abs)
        .map_err(|_| "Path is outside workspace".to_string())?;
    Ok(resolved.to_string_lossy().to_string())
}

#[tauri::command]
fn get_workspace_path(state: tauri::State<'_, AppState>) -> Option<String> {
    state.workspace_path.lock().unwrap().clone()
}

#[tauri::command]
fn set_workspace_path(state: tauri::State<'_, AppState>, path: String) -> Result<(), String> {
    let p = std::path::Path::new(&path);
    let canonical = p.canonicalize()
        .unwrap_or_else(|_| p.to_path_buf());
    *state.workspace_path.lock().unwrap() = Some(canonical.to_string_lossy().to_string());
    Ok(())
}

#[tauri::command]
fn read_file(state: tauri::State<'_, AppState>, path: String) -> Result<String, String> {
    let validated = validate_workspace_path(&state, &path)?;
    std::fs::read_to_string(&validated).map_err(|e| format!("Failed to read file: {}", e))
}

#[tauri::command]
fn write_file(state: tauri::State<'_, AppState>, path: String, content: String) -> Result<(), String> {
    let validated = validate_workspace_path(&state, &path)?;
    if let Some(parent) = std::path::Path::new(&validated).parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create directory: {}", e))?;
    }
    std::fs::write(&validated, &content).map_err(|e| format!("Failed to write file: {}", e))
}

#[tauri::command]
fn list_dir(state: tauri::State<'_, AppState>, path: String) -> Result<Vec<serde_json::Value>, String> {
    let validated = validate_workspace_path(&state, &path)?;
    let entries = std::fs::read_dir(&validated)
        .map_err(|e| format!("Failed to read directory: {}", e))?;

    let mut result = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let metadata = entry.metadata().map_err(|e| e.to_string())?;
        let name = entry
            .file_name()
            .to_string_lossy()
            .to_string();
        if name.starts_with('.') {
            continue;
        }
        result.push(serde_json::json!({
            "name": name,
            "path": entry.path().to_string_lossy(),
            "type": if metadata.is_dir() { "dir" } else { "file" },
            "size": metadata.len(),
        }));
    }

    result.sort_by(|a, b| {
        let a_dir = a["type"].as_str() == Some("dir");
        let b_dir = b["type"].as_str() == Some("dir");
        b_dir.cmp(&a_dir).then(
            a["name"]
                .as_str()
                .unwrap_or("")
                .cmp(b["name"].as_str().unwrap_or("")),
        )
    });

    Ok(result)
}

#[tauri::command]
async fn open_file_in_new_window(
    app: tauri::AppHandle,
    path: String,
    name: Option<String>,
) -> Result<(), String> {
    use tauri::WebviewUrl;

    let window_label = format!("preview_{}", uuid::Uuid::new_v4());
    let window_title = name.unwrap_or_else(|| "NoteAI Preview".to_string());

    // Validate path is within workspace when set
    let state = app.state::<AppState>();
    let safe_path = validate_workspace_path(&state, &path)?;

    tauri::WebviewWindowBuilder::new(
        &app,
        window_label,
        WebviewUrl::App("index.html".into())
    )
    .title(window_title)
    .inner_size(1000.0, 700.0)
    .min_inner_size(800.0, 600.0)
    .decorations(true)
    .title_bar_style(tauri::TitleBarStyle::Overlay)
    .hidden_title(true)
    .traffic_light_position(LogicalPosition::new(14.0, 22.0))
    .initialization_script(&format!(
        "window.__PREVIEW_FILE_PATH__ = {}; window.__IS_PREVIEW_WINDOW__ = true;",
        serde_json::to_string(&safe_path).unwrap_or_else(|_| "\"\"".to_string())
    ))
    .build()
    .map_err(|e| format!("Failed to create window: {}", e))?;

    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .setup(|app| {
            let app_handle = app.handle().clone();
            let app_handle2 = app.handle().clone();
            tauri::async_runtime::block_on(async {
                match start_python_sidecar(app_handle).await {
                    Ok(()) => {
                        println!("[INFO] Python sidecar started");
                    }
                    Err(e) => {
                        eprintln!("[ERROR] Failed to start Python sidecar: {}", e);
                        let _ = app_handle2.emit("python-event", serde_json::json!({
                            "type": "sidecar_error",
                            "message": format!("Python 后端启动失败: {}", e),
                        }));
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            py_call,
            open_folder_dialog,
            open_file_dialog,
            get_workspace_path,
            set_workspace_path,
            read_file,
            write_file,
            list_dir,
            open_file_in_new_window,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<AppState>();
                let child_arc = state.python_child.clone();
                let stdin_arc = state.python_stdin.clone();
                tauri::async_runtime::block_on(async {
                    if let Some(mut child) = child_arc.lock().await.take() {
                        let _ = child.kill().await;
                    }
                    *stdin_arc.lock().await = None;
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
