mod state;
mod sidecar;
mod rpc;
mod commands;

use crate::state::AppState;
use tauri::Emitter;
use tauri::Manager;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .setup(|app| {
            let app_handle = app.handle().clone();
            let app_handle2 = app.handle().clone();

            tauri::async_runtime::block_on(async {
                match sidecar::start_python_sidecar(app_handle).await {
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
            rpc::py_call,
            commands::open_folder_dialog,
            commands::open_file_dialog,
            commands::get_workspace_path,
            commands::set_workspace_path,
            commands::read_file,
            commands::write_file,
            commands::list_dir,
            commands::open_file_in_new_window,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let label = window.label().to_string();
                if label != "main" {
                    return;
                }
                let state = window.state::<AppState>();
                let child_arc = state.python_child.clone();
                let stdin_arc = state.python_stdin.clone();
                {
                    let mut pending = state.pending_requests.lock().unwrap_or_else(|e| e.into_inner());
                    for (_, sender) in pending.drain() {
                        let _ = sender.send(serde_json::Value::Null);
                    }
                }
                let child_arc_clone = child_arc.clone();
                let stdin_arc_clone = stdin_arc.clone();
                std::thread::spawn(move || {
                    tauri::async_runtime::block_on(async {
                        if let Some(mut child) = child_arc_clone.lock().await.take() {
                            let _ = child.kill().await;
                        }
                        *stdin_arc_clone.lock().await = None;
                    });
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}