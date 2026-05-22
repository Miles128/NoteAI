use crate::sidecar;
use crate::state::{AppState, PyRequest};

static ALLOWED_PYTHON_METHODS: &[&str] = &[
    "set_workspace_path", "get_workspace_status", "get_workspace_tree", "on_file_selected",
    "read_file_raw", "delete_file", "move_file", "search_files", "auto_assign_topic",
    "batch_auto_assign_topics", "add_tag_to_file",
    "resolve_topic", "get_link_stats", "discover_links", "llm_rewrite", "llm_rewrite_stream", "llm_rewrite_apply",
    "start_note_integration",
    "save_api_config", "test_api_connection",
    "ai_topic_analyze", "ai_topic_survey", "apply_topic_suggestion",
    "auto_tag_files",
    "get_file_preview", "read_preview_raw_slice", "can_preview_file", "save_file_content",
    "get_all_tags", "get_topic_tree", "save_tags_md", "ensure_tags_md",
    "create_topic", "create_tag", "get_pending_topics", "rename_topic",
    "delete_topic", "rename_tag", "delete_tag", "move_file_to_topic",
    "get_api_config", "get_ui_config", "save_ui_config",
    "get_theme_preference", "save_theme_preference",
    "import_files",
    "start_web_download", "start_file_conversion", "auto_convert_pending", "extract_topics",
    "refresh_log", "get_backlinks", "confirm_link", "reject_link",
    "confirm_all_links", "sync_wiki_with_files",
    "check_workspace_path_valid", "clear_saved_workspace", "reveal_in_finder",
    "rag_chat", "rag_rebuild_index", "rag_incremental_update",
    "get_changelog",
    "get_user_profile", "save_user_profile",
    "get_project_rules", "save_project_rules",
    "get_all_pending",
    "get_activity_log",
    "check_and_generate_surveys",
    "fix_survey_topics",
    "init_rag_index", "rag_add_chunks", "rag_remove_chunks",
    "rag_chat_with_actions", "rag_clear_memory",
    "get_all_topic_names", "get_file_topics", "get_topic_files", "remove_file_from_topic",
    "get_graph_data", "create_topic_folder", "set_abstract_config", "delete_topic_safe",
    "merge_duplicate_topics",
    "cloud_sync_list_providers", "cloud_sync_auth", "cloud_sync_push", "cloud_sync_pull",
    "cloud_sync_status", "cloud_sync_save_config", "cloud_sync_load_config", "cloud_sync_disconnect",
    "ensure_schema", "get_schema", "save_schema", "get_schema_rules",
    "needs_schema_setup", "get_schema_template",
    "start_ingest", "cancel_ingest", "retry_ingest", "get_ingest_status",
    "run_kb_lint", "archive_chat_answer",
];

/// RPC ack timeout. Long work (RAG chat, ingest) returns immediately and streams via python-event.
fn rpc_timeout_secs(method: &str) -> u64 {
    match method {
        "rag_chat" | "rag_chat_with_actions" | "start_ingest" | "retry_ingest"
        | "init_rag_index" | "rag_rebuild_index" | "cancel_ingest" => 30,
        _ => 300,
    }
}

fn is_pipe_broken(err: &str) -> bool {
    err.contains("Broken pipe") || err.contains("os error 32")
}

async fn ensure_sidecar(state: &AppState) -> Result<(), String> {
    if sidecar::is_sidecar_alive(state).await {
        return Ok(());
    }
    let app = state
        .app_handle()
        .ok_or_else(|| "Python 后端未运行".to_string())?;
    sidecar::restart_python_sidecar(&app).await?;
    for _ in 0..50 {
        if sidecar::is_sidecar_alive(state).await {
            return Ok(());
        }
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    }
    Err("Python 后端重启失败".into())
}

async fn call_python_once(
    state: &AppState,
    method: &str,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let id = uuid::Uuid::new_v4().to_string();

    let request = PyRequest {
        id: id.clone(),
        method: method.to_string(),
        params,
    };

    let (tx, rx) = tokio::sync::oneshot::channel();
    {
        let mut pending = state.pending_requests.lock().unwrap_or_else(|e| e.into_inner());
        pending.insert(id.clone(), tx);
    }

    {
        let mut stdin_guard = state.python_stdin.lock().await;
        match stdin_guard.as_mut() {
            Some(stdin) => {
                let mut json_line = serde_json::to_string(&request).map_err(|e| e.to_string())?;
                json_line.push('\n');
                use tokio::io::AsyncWriteExt;
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

    let timeout_secs = rpc_timeout_secs(method);
    match tokio::time::timeout(std::time::Duration::from_secs(timeout_secs), rx).await {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(_)) => Err("Python response channel closed".into()),
        Err(_) => {
            let mut pending = state.pending_requests.lock().unwrap_or_else(|e| e.into_inner());
            pending.remove(&id);
            Err("Python request timed out".into())
        }
    }
}

pub async fn call_python(
    state: &tauri::State<'_, AppState>,
    method: &str,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    ensure_sidecar(state.inner()).await?;

    match call_python_once(state.inner(), method, params.clone()).await {
        Ok(v) => Ok(v),
        Err(e) if is_pipe_broken(&e) || e.contains("not running") => {
            let app = state
                .inner()
                .app_handle()
                .ok_or_else(|| e.clone())?;
            sidecar::restart_python_sidecar(&app).await?;
            for _ in 0..50 {
                if sidecar::is_sidecar_alive(state.inner()).await {
                    break;
                }
                tokio::time::sleep(std::time::Duration::from_millis(200)).await;
            }
            call_python_once(state.inner(), method, params)
                .await
                .map_err(|e2| format!("Python 后端已重启，请再试一次。详情: {}", e2))
        }
        Err(e) => Err(e),
    }
}

#[tauri::command]
pub async fn py_call(
    state: tauri::State<'_, AppState>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if !ALLOWED_PYTHON_METHODS.contains(&method.as_str()) {
        return Err(format!("Method not allowed: {}", method));
    }
    call_python(&state, &method, params).await
}