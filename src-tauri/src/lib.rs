mod commands;
mod rpc;
mod sidecar;
mod state;

use crate::state::AppState;
use tauri::Emitter;
use tauri::Manager;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .setup(|app| {
            // S1: app_handle 无条件注入——初始启动失败后前端 RPC 仍可
            // 触发 restart_python_sidecar，形成自动恢复闭环
            {
                let state = app.state::<AppState>();
                *state.app_handle.lock().unwrap() = Some(app.handle().clone());
            }

            // P3: 后台启动 sidecar，不阻塞主线程（find_python 会对多个
            // 候选串行探测 Python 版本）；完成后经 python-event 通知 UI
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                crate::sidecar::SIDECAR_STARTING.store(true, std::sync::atomic::Ordering::SeqCst);
                match crate::sidecar::start_python_sidecar(handle.clone()).await {
                    Ok(()) => {
                        println!("[INFO] Python sidecar started");
                    }
                    Err(e) => {
                        eprintln!("[ERROR] Failed to start Python sidecar: {}", e);
                        let _ = handle.emit_to(
                            "main",
                            "python-event",
                            serde_json::json!({
                                "type": "sidecar_error",
                                "message": format!("Python 后端启动失败: {}", e),
                            }),
                        );
                    }
                }
                crate::sidecar::SIDECAR_STARTING.store(false, std::sync::atomic::Ordering::SeqCst);
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            rpc::py_call,
            commands::open_folder_dialog,
            commands::open_file_dialog,
            commands::open_archive_dialog,
            commands::set_workspace_path,
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
                    let mut pending = state
                        .pending_requests
                        .lock()
                        .unwrap_or_else(|e| e.into_inner());
                    for (_, sender) in pending.drain() {
                        let _ = sender.send(serde_json::Value::Null);
                    }
                }
                let child_arc_clone = child_arc.clone();
                let stdin_arc_clone = stdin_arc.clone();
                std::thread::spawn(move || {
                    tauri::async_runtime::block_on(async {
                        if let Some(mut child) = child_arc_clone.lock().await.take() {
                            crate::sidecar::kill_process_group(&child);
                            let _ = child.start_kill();
                            let _ = child.wait().await;
                        }
                        *stdin_arc_clone.lock().await = None;
                    });
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
