use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex as StdMutex};
use tauri::AppHandle;
use tokio::process::{Child, ChildStdin};
use tokio::sync::oneshot;
use tokio::sync::Mutex as AsyncMutex;

pub struct AppState {
    pub python_stdin: Arc<AsyncMutex<Option<ChildStdin>>>,
    pub pending_requests: StdMutex<HashMap<String, oneshot::Sender<serde_json::Value>>>,
    pub workspace_path: StdMutex<Option<String>>,
    pub python_child: Arc<AsyncMutex<Option<Child>>>,
    pub app_handle: StdMutex<Option<AppHandle>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            python_stdin: Arc::new(AsyncMutex::new(None)),
            pending_requests: StdMutex::new(HashMap::new()),
            workspace_path: StdMutex::new(None),
            python_child: Arc::new(AsyncMutex::new(None)),
            app_handle: StdMutex::new(None),
        }
    }
}

impl AppState {
    pub fn app_handle(&self) -> Option<AppHandle> {
        self.app_handle.lock().ok().and_then(|g| g.clone())
    }
}

#[derive(Debug, Serialize)]
pub struct PyRequestRef<'a> {
    pub id: &'a str,
    pub method: &'a str,
    pub params: &'a serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PyResponse {
    pub id: String,
    pub result: Option<serde_json::Value>,
    /// Python 侧错误为 `{"code", "message", "details"}` dict；
    /// 反序列化时保留完整载荷，由调用方提取 message。
    pub error: Option<serde_json::Value>,
}
