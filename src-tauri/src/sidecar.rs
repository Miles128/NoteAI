use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

use crate::state::{AppState, PyResponse};

static SIDECAR_GEN: AtomicU64 = AtomicU64::new(0);
static SIDECAR_RESTARTING: AtomicBool = AtomicBool::new(false);

fn hf_cache_dir() -> PathBuf {
    if let Ok(home) = std::env::var("HOME") {
        let p = PathBuf::from(home)
            .join("Library")
            .join("Application Support")
            .join("NoteAI")
            .join("hf_hub");
        let _ = std::fs::create_dir_all(&p);
        return p;
    }
    PathBuf::from("/tmp/noteai_hf_hub")
}

pub async fn is_sidecar_alive(state: &AppState) -> bool {
    if SIDECAR_RESTARTING.load(Ordering::SeqCst) {
        return false;
    }
    state.python_stdin.lock().await.is_some()
}

async fn wait_for_sidecar(state: &AppState, max_ms: u64) -> bool {
    let steps = max_ms / 100;
    for _ in 0..steps {
        if is_sidecar_alive(state).await {
            return true;
        }
        if !SIDECAR_RESTARTING.load(Ordering::SeqCst) && state.python_stdin.lock().await.is_some() {
            return true;
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    is_sidecar_alive(state).await
}

/// Kill child and clear handles without notifying the UI (planned restart).
async fn stop_python_sidecar_quiet(state: &AppState) {
    SIDECAR_GEN.fetch_add(1, Ordering::SeqCst);
    if let Some(mut child) = state.python_child.lock().await.take() {
        let _ = child.kill().await;
    }
    *state.python_stdin.lock().await = None;
}

/// Unexpected exit: clear handles and notify UI.
async fn on_sidecar_process_exit(app: &AppHandle, reader_gen: u64) {
    if reader_gen != SIDECAR_GEN.load(Ordering::SeqCst) {
        return;
    }
    if SIDECAR_RESTARTING.load(Ordering::SeqCst) {
        return;
    }

    let state = app.state::<AppState>();
    *state.python_stdin.lock().await = None;
    if let Some(mut child) = state.python_child.lock().await.take() {
        let _ = child.kill().await;
    }

    eprintln!("[Rust] Python sidecar exited unexpectedly");
    let _ = app.emit(
        "python-event",
        serde_json::json!({
            "type": "sidecar_died",
            "message": "Python 后端意外退出，下次操作将自动恢复"
        }),
    );
}

pub async fn restart_python_sidecar(app: &AppHandle) -> Result<(), String> {
    if SIDECAR_RESTARTING.load(Ordering::SeqCst) {
        let state = app.state::<AppState>();
        if wait_for_sidecar(&state, 15_000).await {
            return Ok(());
        }
        return Err("Python 后端正在重启，请稍候".into());
    }

    SIDECAR_RESTARTING.store(true, Ordering::SeqCst);
    let state = app.state::<AppState>();
    stop_python_sidecar_quiet(&state).await;
    tokio::time::sleep(std::time::Duration::from_millis(400)).await;

    let result = start_python_sidecar(app.clone()).await;
    SIDECAR_RESTARTING.store(false, Ordering::SeqCst);
    if result.is_ok() {
        let _ = app.emit(
            "python-event",
            serde_json::json!({
                "type": "sidecar_ready",
                "message": "Python 后端已恢复"
            }),
        );
    }
    result
}

fn python_ok(candidate: &Path) -> bool {
    if !candidate.exists() {
        return false;
    }
    let Ok(output) = std::process::Command::new(candidate).arg("--version").output() else {
        return false;
    };
    let ver = String::from_utf8_lossy(&output.stdout);
    !ver.contains("Python 2")
}

pub fn find_python() -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var("NOTEAI_PYTHON") {
        let p = PathBuf::from(explicit);
        if python_ok(&p) {
            return Ok(p);
        }
    }

    let exe_dir = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("No parent dir")?
        .to_path_buf();

    let mut candidates: Vec<PathBuf> = vec![];

    let resources = exe_dir.join("../Resources");
    for name in ["sidecar-python/bin/python3", "sidecar-python/bin/python"] {
        candidates.push(resources.join(name));
    }

    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let base = PathBuf::from(manifest).join("resources/sidecar-python/bin");
        candidates.push(base.join("python3"));
        candidates.push(base.join("python"));
    }

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
        if python_ok(&candidate) {
            return Ok(candidate);
        }
    }

    Err(
        "Python not found. Install Python 3, set NOTEAI_PYTHON, or run scripts/bundle_sidecar_python.sh before release build.".into(),
    )
}

fn resolve_sidecar_script(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(path) = app.path().resolve("python/main.py", BaseDirectory::Resource) {
        if path.exists() {
            return Ok(path);
        }
    }

    let exe_dir = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("No parent dir")?
        .to_path_buf();

    let candidates = vec![
        exe_dir.join("../Resources/python/main.py"),
        exe_dir.join("..").join("python").join("main.py"),
        exe_dir.join("..").join("..").join("python").join("main.py"),
        exe_dir.join("..").join("..").join("..").join("python").join("main.py"),
        PathBuf::from("python/main.py"),
    ];

    for candidate in candidates {
        if let Some(path) = candidate.canonicalize().ok() {
            if path.exists() {
                return Ok(path);
            }
        }
    }

    Err("Python sidecar main.py not found".into())
}

pub async fn start_python_sidecar(app: tauri::AppHandle) -> Result<(), String> {
    let python_path = find_python()?;

    let script_path = resolve_sidecar_script(&app)?;

    let hf_cache = hf_cache_dir();
    let hf_cache_str = hf_cache.to_string_lossy().to_string();
    let reader_gen = SIDECAR_GEN.fetch_add(1, Ordering::SeqCst) + 1;

    let mut child = Command::new(&python_path)
        .arg(&script_path)
        .env(
            "HF_ENDPOINT",
            std::env::var("HF_ENDPOINT").unwrap_or_else(|_| "https://hf-mirror.com".to_string()),
        )
        .env(
            "NO_PROXY",
            std::env::var("NO_PROXY").unwrap_or_else(|_| "huggingface.co,hf-mirror.com".to_string()),
        )
        .env("HF_HOME", &hf_cache_str)
        .env("HUGGINGFACE_HUB_CACHE", &hf_cache_str)
        .env("TRANSFORMERS_CACHE", &hf_cache_str)
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        .env("KMP_DUPLICATE_LIB_OK", "TRUE")
        .env("OMP_NUM_THREADS", "4")
        .env("TERM", "dumb")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .process_group(0)
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
        on_sidecar_process_exit(&app_clone, reader_gen).await;
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
    if let Ok(mut slot) = state.app_handle.lock() {
        *slot = Some(app.clone());
    }

    Ok(())
}
