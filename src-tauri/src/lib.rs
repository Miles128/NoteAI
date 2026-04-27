use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex as StdMutex};
use tauri::{Emitter, Manager};
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
                        let _ = app_clone.emit("python-event", &result);
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

    eprintln!("[DEBUG] exe_dir: {:?}", exe_dir);

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

    eprintln!("[DEBUG] Python candidates: {:?}", candidates);

    for candidate in candidates {
        if candidate.exists() {
            eprintln!("[DEBUG] Found Python: {:?}", candidate);
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

#[tauri::command]
async fn py_call(
    state: tauri::State<'_, AppState>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
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
        .blocking_pick_files();
    Ok(files.map(|paths| paths.into_iter().map(|p| p.to_string()).collect()))
}

#[tauri::command]
fn get_workspace_path(state: tauri::State<'_, AppState>) -> Option<String> {
    state.workspace_path.lock().unwrap().clone()
}

#[tauri::command]
fn set_workspace_path(state: tauri::State<'_, AppState>, path: String) {
    *state.workspace_path.lock().unwrap() = Some(path);
}

#[tauri::command]
fn read_file(path: String) -> Result<String, String> {
    std::fs::read_to_string(&path).map_err(|e| format!("Failed to read file: {}", e))
}

#[tauri::command]
fn write_file(path: String, content: String) -> Result<(), String> {
    if let Some(parent) = std::path::Path::new(&path).parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create directory: {}", e))?;
    }
    std::fs::write(&path, &content).map_err(|e| format!("Failed to write file: {}", e))
}

#[tauri::command]
fn list_dir(path: String) -> Result<Vec<serde_json::Value>, String> {
    let entries = std::fs::read_dir(&path)
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

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::block_on(async {
                match start_python_sidecar(app_handle).await {
                    Ok(()) => {
                        println!("[INFO] Python sidecar started");
                    }
                    Err(e) => {
                        eprintln!("[ERROR] Failed to start Python sidecar: {}", e);
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
        ])
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
