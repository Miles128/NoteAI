#[cfg(target_os = "macos")]
use tauri::LogicalPosition;
use tauri::Manager;

use crate::state::AppState;

fn normalize_path(path: &std::path::Path) -> std::path::PathBuf {
    let mut stack: Vec<std::path::Component> = Vec::new();
    for component in path.components() {
        match component {
            std::path::Component::Normal(_) => stack.push(component),
            std::path::Component::ParentDir => {
                // Only pop normal components; never pop a root/prefix component
                // so that excessive ".." segments collapse to the root instead of panicking.
                if matches!(stack.last(), Some(std::path::Component::Normal(_))) {
                    stack.pop();
                }
            }
            std::path::Component::RootDir | std::path::Component::Prefix(_) => {
                stack.clear();
                stack.push(component);
            }
            std::path::Component::CurDir => {}
        }
    }
    stack.iter().map(|c| c.as_os_str()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn normalize_simple_path() {
        let p = PathBuf::from("/a/b/c");
        assert_eq!(normalize_path(&p), PathBuf::from("/a/b/c"));
    }

    #[test]
    fn normalize_strips_curdir() {
        let p = PathBuf::from("/a/./b");
        assert_eq!(normalize_path(&p), PathBuf::from("/a/b"));
    }

    #[test]
    fn normalize_resolves_parentdir() {
        let p = PathBuf::from("/a/b/c/../d");
        assert_eq!(normalize_path(&p), PathBuf::from("/a/b/d"));
    }

    #[test]
    fn normalize_excessive_parentdir_does_not_panic() {
        // Excessive ".." beyond the root should collapse to root, not panic.
        let p = PathBuf::from("/a/../../..");
        let result = normalize_path(&p);
        assert!(
            result.starts_with("/"),
            "result should remain under root: {:?}",
            result
        );
    }

    #[test]
    fn normalize_relative_excessive_parentdir() {
        let p = PathBuf::from("../../etc/passwd");
        let result = normalize_path(&p);
        // Relative paths with excessive ".." should not contain ".." segments.
        let s = result.to_string_lossy();
        assert!(
            !s.contains(".."),
            "result should not contain '..': {:?}",
            result
        );
    }

    #[test]
    fn resolve_allows_new_file_under_workspace() {
        let base = std::env::temp_dir().join(format!("noteai-path-test-{}", uuid::Uuid::new_v4()));
        let workspace = base.join("workspace");
        std::fs::create_dir_all(&workspace).unwrap();

        let resolved =
            resolve_workspace_target(workspace.to_str().unwrap(), "Notes/new/topic.md").unwrap();

        assert_eq!(
            resolved,
            workspace.canonicalize().unwrap().join("Notes/new/topic.md")
        );
        std::fs::remove_dir_all(&base).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn resolve_rejects_new_file_beneath_external_symlink() {
        use std::os::unix::fs::symlink;

        let base = std::env::temp_dir().join(format!("noteai-path-test-{}", uuid::Uuid::new_v4()));
        let workspace = base.join("workspace");
        let outside = base.join("outside");
        std::fs::create_dir_all(&workspace).unwrap();
        std::fs::create_dir_all(&outside).unwrap();
        symlink(&outside, workspace.join("external")).unwrap();

        let result = resolve_workspace_target(workspace.to_str().unwrap(), "external/escaped.md");

        assert_eq!(result.unwrap_err(), "Path is outside workspace");
        std::fs::remove_dir_all(&base).unwrap();
    }
}

fn resolve_workspace_target(workspace: &str, path: &str) -> Result<std::path::PathBuf, String> {
    let workspace_abs = std::path::Path::new(workspace)
        .canonicalize()
        .map_err(|e| format!("Invalid workspace: {}", e))?;
    let target = std::path::Path::new(path);
    let target_abs = if target.is_absolute() {
        target.to_path_buf()
    } else {
        workspace_abs.join(path)
    };
    let resolved = normalize_path(&target_abs);

    // Canonicalize the nearest existing ancestor. Canonicalizing the complete
    // target alone is insufficient for a new file: it fails and would leave a
    // symlinked parent unresolved.
    let mut ancestor = resolved.as_path();
    let mut missing_tail = Vec::new();
    while !ancestor.exists() {
        let name = ancestor
            .file_name()
            .ok_or_else(|| "Invalid target path".to_string())?;
        missing_tail.push(name.to_os_string());
        ancestor = ancestor
            .parent()
            .ok_or_else(|| "Invalid target path".to_string())?;
    }
    let canonical_ancestor = ancestor
        .canonicalize()
        .map_err(|e| format!("Invalid target path: {}", e))?;
    if !canonical_ancestor.starts_with(&workspace_abs) {
        return Err("Path is outside workspace".to_string());
    }
    let mut safe_target = canonical_ancestor;
    for part in missing_tail.iter().rev() {
        safe_target.push(part);
    }
    if !safe_target.starts_with(&workspace_abs) {
        return Err("Path is outside workspace".to_string());
    }
    Ok(safe_target)
}

fn validate_workspace_path(
    state: &tauri::State<'_, AppState>,
    path: &str,
) -> Result<String, String> {
    let workspace = state
        .workspace_path
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    let workspace = workspace.as_ref().ok_or("Workspace not set")?;
    resolve_workspace_target(workspace, path).map(|value| value.to_string_lossy().to_string())
}

#[tauri::command]
pub async fn open_folder_dialog(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|p| p.to_string()))
}

#[tauri::command]
pub async fn open_file_dialog(app: tauri::AppHandle) -> Result<Option<Vec<String>>, String> {
    use tauri_plugin_dialog::DialogExt;
    let files = app
        .dialog()
        .file()
        .add_filter(
            "文档文件",
            &["pdf", "docx", "doc", "pptx", "ppt", "html", "htm", "txt"],
        )
        .blocking_pick_files();
    Ok(files.map(|paths| paths.into_iter().map(|p| p.to_string()).collect()))
}

#[tauri::command]
pub fn get_workspace_path(state: tauri::State<'_, AppState>) -> Option<String> {
    state
        .workspace_path
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
}

#[tauri::command]
pub fn set_workspace_path(state: tauri::State<'_, AppState>, path: String) -> Result<(), String> {
    let p = std::path::Path::new(&path);
    let canonical = p
        .canonicalize()
        .map_err(|e| format!("Invalid workspace: {}", e))?;
    if !canonical.is_dir() {
        return Err("Workspace must be an existing directory".to_string());
    }
    *state
        .workspace_path
        .lock()
        .unwrap_or_else(|e| e.into_inner()) = Some(canonical.to_string_lossy().to_string());
    Ok(())
}

#[tauri::command]
pub fn read_file(state: tauri::State<'_, AppState>, path: String) -> Result<String, String> {
    let validated = validate_workspace_path(&state, &path)?;
    std::fs::read_to_string(&validated).map_err(|e| format!("Failed to read file: {}", e))
}

#[tauri::command]
pub fn write_file(
    state: tauri::State<'_, AppState>,
    path: String,
    content: String,
) -> Result<(), String> {
    let validated = validate_workspace_path(&state, &path)?;
    if let Some(parent) = std::path::Path::new(&validated).parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create directory: {}", e))?;
    }
    std::fs::write(&validated, &content).map_err(|e| format!("Failed to write file: {}", e))
}

#[tauri::command]
pub fn list_dir(
    state: tauri::State<'_, AppState>,
    path: String,
) -> Result<Vec<serde_json::Value>, String> {
    let validated = validate_workspace_path(&state, &path)?;
    let entries =
        std::fs::read_dir(&validated).map_err(|e| format!("Failed to read directory: {}", e))?;

    let mut result = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let metadata = entry.metadata().map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().to_string();
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

    #[allow(unused_mut)]
    let mut builder =
        tauri::WebviewWindowBuilder::new(&app, window_label, WebviewUrl::App("index.html".into()))
            .title(window_title)
            .inner_size(1000.0, 700.0)
            .min_inner_size(800.0, 600.0)
            .decorations(true);

    #[cfg(target_os = "macos")]
    {
        builder = builder
            .title_bar_style(tauri::TitleBarStyle::Overlay)
            .hidden_title(true)
            .traffic_light_position(LogicalPosition::new(14.0, 22.0));
    }

    builder
        .initialization_script(format!(
            "window.__PREVIEW_FILE_PATH__ = {}; window.__IS_PREVIEW_WINDOW__ = true;",
            serde_json::to_string(&safe_path).unwrap_or_else(|_| "\"\"".to_string())
        ))
        .build()
        .map_err(|e| format!("Failed to create window: {}", e))?;

    Ok(())
}
