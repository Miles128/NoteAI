use crate::sidecar;
use crate::state::{AppState, PyRequest};

pub(crate) fn fail_pending_requests(state: &AppState, message: &str) {
    let mut pending = state
        .pending_requests
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    let value = serde_json::json!({"success": false, "message": message});
    for (_, sender) in pending.drain() {
        let _ = sender.send(value.clone());
    }
}

static ALLOWED_PYTHON_METHODS: &[&str] = &[
    "add_tag_to_file",
    "ai_topic_analyze",
    "ai_topic_survey",
    "append_chat_to_survey",
    "apply_topic_placement_threshold",
    "apply_topic_suggestion",
    "archive_chat_answer",
    "auto_assign_topic",
    "auto_convert_pending",
    "auto_tag_files",
    "backup_workspace",
    "batch_auto_assign_topics",
    "can_preview_file",
    "cancel_ingest",
    "check_ingest_updates",
    "check_workspace_path_valid",
    "clear_saved_workspace",
    "confirm_all_links",
    "confirm_link",
    "convert_raw_archive",
    "create_note",
    "create_note_from_draft",
    "create_sample_workspace",
    "create_tag",
    "create_topic",
    "create_topic_folder",
    "delete_file",
    "delete_tag",
    "delete_topic",
    "delete_topic_safe",
    "discover_cross_refs_for_file",
    "discover_links",
    "dismiss_cascade_failure",
    "dismiss_convert_failure",
    "ensure_ingest",
    "ensure_schema",
    "ensure_tags_md",
    "export_notes",
    "extract_topics",
    "fix_survey_topics",
    "get_activity_log",
    "get_all_pending",
    "get_all_tags",
    "get_all_topic_names",
    "get_api_config",
    "get_backlinks",
    "get_cascade_failures",
    "get_convert_failures",
    "get_components_status",
    "get_chunk_merge_candidates",
    "get_dashboard_status",
    "get_file_preview",
    "get_file_topics",
    "get_graph_data",
    "get_index_health",
    "get_ingest_status",
    "get_job",
    "get_jobs",
    "get_kb_health",
    "generate_vault_agents_md",
    "get_link_stats",
    "get_semantic_workbench",
    "get_semantic_detail",
    "get_note_semantic_context",
    "get_semantic_object_wiki_page",
    "get_semantic_changes",
    "get_semantic_compile_status",
    "get_semantic_topic_wiki_page",
    "get_semantic_entity_merge_preview",
    "get_topic_brief",
    "restore_workspace_backup",
    "review_semantic_entity_quality",
    "enqueue_semantic_entity_quality",
    "merge_semantic_entities",
    "get_mcp_status",
    "get_duplicate_review",
    "get_lint_report",
    "get_project_rules",
    "get_workspace_rules",
    "get_schema",
    "get_schema_options",
    "get_schema_rules",
    "get_schema_template",
    "get_survey_status",
    "get_theme_preference",
    "get_topic_files",
    "get_topic_tree",
    "get_topic_tree_3tier",
    "get_ui_config",
    "get_workspace_status",
    "get_workspace_tree",
    "import_files",
    "import_rss_feed",
    "import_transcript",
    "init_rag_index",
    "install_component",
    "keep_note_in_topic",
    "llm_rewrite",
    "llm_rewrite_apply",
    "llm_rewrite_stream",
    "merge_duplicate_topics",
    "move_file",
    "move_file_to_topic",
    "needs_schema_setup",
    "needs_workspace_rules_setup",
    "on_file_selected",
    "rag_add_chunks",
    "rag_chat",
    "rag_clear_memory",
    "rag_index_status",
    "rag_rebuild_index",
    "rag_remove_chunks",
    "read_file_raw",
    "read_preview_raw_slice",
    "refresh_log",
    "reject_link",
    "remove_file_from_topic",
    "rename_tag",
    "rename_topic",
    "request_full_ingest",
    "resolve_topic",
    "retry_all_cascade_failures",
    "retry_all_convert_failures",
    "retry_cascade_topic",
    "retry_convert_file",
    "retry_ingest",
    "review_semantic_conflict",
    "update_semantic_claim",
    "set_semantic_claim_status",
    "set_semantic_evidence_status",
    "add_semantic_entity_alias",
    "start_semantic_full_compile",
    "verify_semantic_claim",
    "publish_semantic_topic_wiki_page",
    "publish_semantic_object_wiki_page",
    "reveal_in_finder",
    "register_mcp_server",
    "run_kb_lint",
    "merge_duplicate_notes",
    "merge_note_group",
    "merge_similar_topics",
    "preview_topic_merge",
    "run_cli_agent",
    "stop_cli_agent",
    "suggest_topic_merge_names",
    "clear_cli_agent_session",
    "save_api_config",
    "save_file_content",
    "save_project_rules",
    "save_workspace_rules",
    "save_schema",
    "save_schema_options",
    "save_tags_md",
    "save_theme_preference",
    "save_ui_config",
    "scan_merge_candidates",
    "search_files",
    "set_abstract_config",
    "set_workspace_path",
    "start_file_conversion",
    "start_ingest",
    "start_note_integration",
    "start_web_download",
    "sync_wiki_with_files",
    "test_api_connection",
    "toggle_survey",
    "save_rss_subscription",
    "remove_rss_subscription",
    "list_cli_agents",
    "list_rss_subscriptions",
    "unregister_mcp_server",
    "uninstall_component",
    "fetch_all_rss",
    "add_watched_folder",
    "list_watched_folders",
    "remove_watched_folder",
    "scan_watched_folder",
];

/// RPC ack timeout. Long work (RAG chat, ingest) returns immediately and streams via python-event.
fn rpc_timeout_secs(method: &str) -> u64 {
    match method {
        "rag_chat" => 60,
        "verify_semantic_claim" => 360,
        "start_ingest" | "ensure_ingest" | "retry_ingest" | "init_rag_index"
        | "rag_rebuild_index" | "cancel_ingest" => 120,
        _ => 60,
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
    let mut json_line = serde_json::to_string(&request).map_err(|e| e.to_string())?;
    json_line.push('\n');

    let (tx, rx) = tokio::sync::oneshot::channel();
    {
        let mut pending = state
            .pending_requests
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        pending.insert(id.clone(), tx);
    }

    let write_result: Result<(), String> = {
        let mut stdin_guard = state.python_stdin.lock().await;
        match stdin_guard.as_mut() {
            Some(stdin) => {
                use tokio::io::AsyncWriteExt;
                if let Err(error) = stdin.write_all(json_line.as_bytes()).await {
                    Err(format!("Write failed: {}", error))
                } else {
                    stdin
                        .flush()
                        .await
                        .map_err(|e| format!("Flush failed: {}", e))
                }
            }
            None => Err("Python process not running".into()),
        }
    };
    if let Err(error) = write_result {
        state
            .pending_requests
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .remove(&id);
        return Err(error);
    }

    let timeout_secs = rpc_timeout_secs(method);
    match tokio::time::timeout(std::time::Duration::from_secs(timeout_secs), rx).await {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(_)) => Err("Python response channel closed".into()),
        Err(_) => {
            let mut pending = state
                .pending_requests
                .lock()
                .unwrap_or_else(|e| e.into_inner());
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
            let app = state.inner().app_handle().ok_or_else(|| e.clone())?;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failing_pending_requests_notifies_and_drains_waiters() {
        let state = AppState::default();
        let (sender, mut receiver) = tokio::sync::oneshot::channel();
        state
            .pending_requests
            .lock()
            .unwrap()
            .insert("request-1".to_string(), sender);

        fail_pending_requests(&state, "sidecar stopped");

        let response = receiver.try_recv().unwrap();
        assert_eq!(response["success"], false);
        assert_eq!(response["message"], "sidecar stopped");
        assert!(state.pending_requests.lock().unwrap().is_empty());
    }
}
