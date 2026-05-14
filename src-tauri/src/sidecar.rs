use std::path::PathBuf;
use tauri::Emitter;
use tauri::Manager;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

use crate::state::{AppState, PyResponse};

pub fn find_python() -> Result<PathBuf, String> {
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

pub async fn start_python_sidecar(app: tauri::AppHandle) -> Result<(), String> {
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
        .env("HF_ENDPOINT", std::env::var("HF_ENDPOINT").unwrap_or_else(|_| "https://hf-mirror.com".to_string()))
        .env("NO_PROXY", std::env::var("NO_PROXY").unwrap_or_else(|_| "huggingface.co,hf-mirror.com".to_string()))
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
                let truncated: String = line.chars().take(200).collect();
                eprintln!("[Rust] Failed to parse Python stdout: {}", truncated);
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