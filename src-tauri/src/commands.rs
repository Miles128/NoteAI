use tauri::LogicalPosition;
use tauri::Manager;

use crate::state::AppState;

fn validate_workspace_path(state: &tauri::State<'_, AppState>, path: &str) -> Result<String, String> {
    let workspace = state.workspace_path.lock().unwrap_or_else(|e| e.into_inner());
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
pub async fn open_folder_dialog(
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
pub async fn open_file_dialog(
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

#[tauri::command]
pub fn get_workspace_path(state: tauri::State<'_, AppState>) -> Option<String> {
    state.workspace_path.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

#[tauri::command]
pub fn set_workspace_path(state: tauri::State<'_, AppState>, path: String) -> Result<(), String> {
    let p = std::path::Path::new(&path);
    let canonical = p.canonicalize()
        .unwrap_or_else(|_| p.to_path_buf());
    *state.workspace_path.lock().unwrap_or_else(|e| e.into_inner()) = Some(canonical.to_string_lossy().to_string());
    Ok(())
}

#[tauri::command]
pub fn read_file(state: tauri::State<'_, AppState>, path: String) -> Result<String, String> {
    let validated = validate_workspace_path(&state, &path)?;
    std::fs::read_to_string(&validated).map_err(|e| format!("Failed to read file: {}", e))
}

#[tauri::command]
pub fn write_file(state: tauri::State<'_, AppState>, path: String, content: String) -> Result<(), String> {
    let validated = validate_workspace_path(&state, &path)?;
    if let Some(parent) = std::path::Path::new(&validated).parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create directory: {}", e))?;
    }
    std::fs::write(&validated, &content).map_err(|e| format!("Failed to write file: {}", e))
}

#[tauri::command]
pub fn list_dir(state: tauri::State<'_, AppState>, path: String) -> Result<Vec<serde_json::Value>, String> {
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
pub async fn open_file_in_new_window(
    app: tauri::AppHandle,
    path: String,
    name: Option<String>,
) -> Result<(), String> {
    use tauri::WebviewUrl;

    let window_label = format!("preview_{}", uuid::Uuid::new_v4());
    let window_title = name.unwrap_or_else(|| "NoteAI Preview".to_string());

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