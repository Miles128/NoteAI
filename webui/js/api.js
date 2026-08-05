(function() { 'use strict';

var _isTauri = null;
var _isTauriChecked = false;

function checkIsTauri() {
    if (_isTauriChecked) return _isTauri;
    _isTauriChecked = true;
    _isTauri = typeof window !== 'undefined' && !!(window.__TAURI_INTERNALS__ || window.__TAURI__);
    return _isTauri;
}

function getTauriInvoke() {
    if (window.__TAURI__) {
        if (typeof window.__TAURI__.invoke === 'function') return window.__TAURI__.invoke;
        if (window.__TAURI__.core && typeof window.__TAURI__.core.invoke === 'function') return window.__TAURI__.core.invoke;
        if (window.__TAURI__.ipc && typeof window.__TAURI__.ipc.invoke === 'function') return window.__TAURI__.ipc.invoke;
    }
    if (window.__TAURI_INTERNALS__) {
        if (typeof window.__TAURI_INTERNALS__.invoke === 'function') return window.__TAURI_INTERNALS__.invoke;
        if (window.__TAURI_INTERNALS__.ipc && typeof window.__TAURI_INTERNALS__.ipc.invoke === 'function') return window.__TAURI_INTERNALS__.ipc.invoke;
    }
    return null;
}

function getTauriEventAPI() {
    if (window.__TAURI__ && window.__TAURI__.event) return window.__TAURI__.event;
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event) return window.__TAURI_INTERNALS__.event;
    return null;
}

var _pyCallRetries = 2;
var _pyCallRetryDelayMs = 300;

function _isRetryableError(e) {
    if (!e) return false;
    var msg = String(e.message || e).toLowerCase();
    // 仅限明确的传输层错误；宽泛关键字（如 invoke）会把业务错误也纳入重试，
    // 叠加断管重发可能导致请求重复执行
    return msg.indexOf('aborted') !== -1 ||
        msg.indexOf('cancelled') !== -1 ||
        msg.indexOf('canceled') !== -1 ||
        msg.indexOf('broken pipe') !== -1 ||
        msg.indexOf('tauri invoke not available') !== -1 ||
        msg.indexOf('not running in tauri') !== -1 ||
        msg.indexOf('sidecar') !== -1;
}

function _translateError(e) {
    var msg = String(e && (e.message || e));
    var lower = msg.toLowerCase();
    if (msg.indexOf('Not running in Tauri') !== -1) {
        return new Error('应用未在 Tauri 环境中运行');
    }
    if (msg.indexOf('Tauri invoke not available') !== -1) {
        return new Error('Tauri 调用接口不可用，请重启应用');
    }
    if (lower.indexOf('timeout') !== -1 || lower.indexOf('timed out') !== -1) {
        return new Error('请求超时，请稍后重试');
    }
    if (lower.indexOf('sidecar') !== -1 || lower.indexOf('python') !== -1) {
        return new Error('后端服务暂时不可用，请重启应用');
    }
    return e;
}

async function pyCall(method, params, options) {
    if (!checkIsTauri()) {
        throw _translateError(new Error('Not running in Tauri'));
    }
    var invoke = getTauriInvoke();
    if (!invoke) throw _translateError(new Error('Tauri invoke not available'));

    var opts = options || {};
    var retries = opts.noRetry ? 0 : _pyCallRetries;
    var lastError = null;
    for (var attempt = 0; attempt <= retries; attempt++) {
        try {
            var result = await invoke('py_call', {
                method: method,
                params: params || {}
            });
            return result;
        } catch (e) {
            lastError = e;
            if (attempt < retries && _isRetryableError(e)) {
                console.warn('[API] pyCall retry:', method, attempt + 1, e);
                await new Promise(function(resolve) { setTimeout(resolve, _pyCallRetryDelayMs * (attempt + 1)); });
                continue;
            }
            console.error('[API] pyCall error:', method, e);
            throw _translateError(e);
        }
    }
    throw _translateError(lastError);
}

var PREVIEW_RAW_SLICE_CHUNK_BYTES = 384 * 1024;

function b64Utf8Decode(b64) {
    if (!b64) return '';
    var bin = typeof atob === 'function' ? atob(b64) : '';
    var out = new Uint8Array(bin.length);
    var i = 0;
    for (; i < bin.length; i++) {
        out[i] = bin.charCodeAt(i) & 0xff;
    }
    return new TextDecoder('utf-8').decode(out);
}

function concatUint8(chunks) {
    var len = 0;
    chunks.forEach(function(chunk) {
        len += chunk.length;
    });
    var out = new Uint8Array(len);
    var off = 0;
    chunks.forEach(function(chunk) {
        out.set(chunk, off);
        off += chunk.length;
    });
    return out;
}

function hydrateSemanticPreviewRpc(result) {
    if (!result || !result.success) return result;
    if (
        result.preview_delivery === 'semantic_b64'
        || (result.transport === 'base64_utf8' && result.content_b64)
    ) {
        result.content = b64Utf8Decode(result.content_b64);
        return result;
    }
    return result;
}

async function assembleRawSlicesAsUtf8Preview(path, totalByteSize) {
    var total = typeof totalByteSize === 'number' ? totalByteSize : 0;
    if (total < 1) return '';
    var parts = [];
    var off = 0;
    while (off < total) {
        var want = Math.min(PREVIEW_RAW_SLICE_CHUNK_BYTES, total - off);
        var slice = await pyCall('read_preview_raw_slice', {
            path: path,
            byte_offset: off,
            byte_limit: want
        });
        if (!slice || !slice.success) {
            throw new Error((slice && (slice.message || slice.error)) || '分页预览读取失败');
        }
        parts.push(sliceChunkToUint8(slice.chunk_b64 || ''));
        off = typeof slice.next_byte_offset === 'number' ? slice.next_byte_offset : off + parts[parts.length - 1].length;
        if (slice.done) break;
        if (off >= total) break;
    }
    var merged = concatUint8(parts);
    return new TextDecoder('utf-8').decode(merged);
}

function sliceChunkToUint8(b64) {
    if (!b64) return new Uint8Array(0);
    var bin = typeof atob === 'function' ? atob(b64) : '';
    var out = new Uint8Array(bin.length);
    var i = 0;
    for (; i < bin.length; i++) {
        out[i] = bin.charCodeAt(i) & 0xff;
    }
    return out;
}

// ---------------------------------------------------------------------------
// 特殊 API 函数：涉及 Tauri 原生对话框 / 多步逻辑 / 分页预览，无法配置化生成
// ---------------------------------------------------------------------------

async function openWorkspace() {
    if (!checkIsTauri()) {
        throw new Error('必须在 Tauri 环境中运行');
    }
    var invoke = getTauriInvoke();
    var folder = await invoke('open_folder_dialog');
    if (folder) {
        var pyResult = await pyCall('set_workspace_path', { path: folder });
        if (pyResult && pyResult.success) {
            await invoke('set_workspace_path', { path: folder });
        }
        return pyResult || { success: false, message: '设置工作区失败' };
    }
    return { success: false, message: '未选择文件夹' };
}

async function getWorkspaceStatus() {
    var result = await pyCall('get_workspace_status');
    if (result && result.is_set && checkIsTauri()) {
        var invoke = getTauriInvoke();
        await invoke('set_workspace_path', { path: result.workspace_path });
        pyCall('fix_survey_topics', {}).catch(function(err) { console.warn('[fix_survey_topics]', err); });
    }
    return result;
}

async function createSampleWorkspace() {
    var pyResult = await pyCall('create_sample_workspace', {}, { noRetry: true });
    if (pyResult && pyResult.success && checkIsTauri()) {
        var invoke = getTauriInvoke();
        if (invoke) await invoke('set_workspace_path', { path: pyResult.workspace_path });
    }
    return pyResult || { success: false, message: '创建示例库失败' };
}

async function addFiles() {
    if (!checkIsTauri()) {
        throw new Error('必须在 Tauri 环境中运行');
    }
    var invoke = getTauriInvoke();
    var files = await invoke('open_file_dialog');
    return files || [];
}

async function importFilesToWorkspace() {
    if (!checkIsTauri()) {
        throw new Error('必须在 Tauri 环境中运行');
    }
    var invoke = getTauriInvoke();
    var files = await invoke('open_file_dialog');
    if (!files || files.length === 0) return { cancelled: true };
    return pyCall('import_files', { files: files });
}

async function browseFolder() {
    if (!checkIsTauri()) {
        throw new Error('必须在 Tauri 环境中运行');
    }
    var invoke = getTauriInvoke();
    var folder = await invoke('open_folder_dialog');
    return folder || '';
}

async function openArchiveDialog() {
    if (!checkIsTauri()) {
        throw new Error('必须在 Tauri 环境中运行');
    }
    var invoke = getTauriInvoke();
    return await invoke('open_archive_dialog');
}

async function getFilePreview(path) {
    var raw = await pyCall('get_file_preview', { path: path });
    if (!raw || !raw.success) return raw;

    if (raw.preview_delivery === 'raw_slices') {
        try {
            var total = raw.total_byte_size != null ? raw.total_byte_size : raw.file_size;
            var text = await assembleRawSlicesAsUtf8Preview(path, total);
            return {
                success: true,
                type: raw.type || 'markdown',
                preview_delivery: 'semantic_b64',
                file_name: raw.file_name,
                file_size: typeof total === 'number' ? total : undefined,
                content: text
            };
        } catch (e) {
            console.error('[API] chunk preview failed, falling back:', e);
            var fallback = await pyCall('get_file_preview', { path: path, force_semantic_preview: true });
            return hydrateSemanticPreviewRpc(fallback);
        }
    }

    return hydrateSemanticPreviewRpc(raw);
}

// ---------------------------------------------------------------------------
// 窗口控制：直接调用 Tauri 窗口 API，不走 pyCall
// ---------------------------------------------------------------------------

function getTauriWindow() {
    if (window.__TAURI__ && window.__TAURI__.window) {
        if (typeof window.__TAURI__.window.getCurrentWindow === 'function') {
            return window.__TAURI__.window.getCurrentWindow();
        }
        if (typeof window.__TAURI__.window.getCurrent === 'function') {
            return window.__TAURI__.window.getCurrent();
        }
    }
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.window) {
        if (typeof window.__TAURI_INTERNALS__.window.getCurrentWindow === 'function') {
            return window.__TAURI_INTERNALS__.window.getCurrentWindow();
        }
        if (typeof window.__TAURI_INTERNALS__.window.getCurrent === 'function') {
            return window.__TAURI_INTERNALS__.window.getCurrent();
        }
    }
    return null;
}

function moveWindow(dx, dy) {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win && typeof win.startDragging === 'function') {
            win.startDragging();
        }
    }
}

function minimizeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.minimize();
    }
}

function maximizeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.toggleMaximize();
    }
}

function closeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.close();
    }
}

async function openFileInNewWindow(path, name) {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        if (invoke) {
            return invoke('open_file_in_new_window', { path: path, name: name || null });
        }
    }
    console.error('[API] Not running in Tauri');
    throw new Error('Not running in Tauri');
}

// ---------------------------------------------------------------------------
// 配置化 API 注册：消除重复的 "定义异步函数 → 调用 pyCall → 返回结果" 模式
//
// 每项定义：
//   name   —— 暴露到 window.api 上的方法名
//   method —— 对应的 Python sidecar RPC 方法名
//   params —— 可选，将函数入参映射为 pyCall 参数对象的函数；省略则传 {}
// ---------------------------------------------------------------------------

function createApiFunction(def) {
    return async function() {
        var params = def.params ? def.params.apply(null, arguments) : {};
        return pyCall(def.method, params, { noRetry: !!def.write });
    };
}

var API_DEFS = [
    // ---- 工作区 / 主题 / 标签 ----
    { name: 'getWorkspaceTree', method: 'get_workspace_tree' },
    { name: 'getTopicTree', method: 'get_topic_tree' },
    { name: 'getSurveyOverview', method: 'get_survey_overview' },
    { name: 'toggleSurvey', method: 'toggle_survey', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'getAllTags', method: 'get_all_tags' },
    { name: 'autoTagFiles', method: 'auto_tag_files', params: function(dryRun) { return { dry_run: !!dryRun }; }, write: true },
    { name: 'ensureTagsMd', method: 'ensure_tags_md', params: function() { return {}; }, write: true },
    { name: 'batchAutoAssignTopics', method: 'batch_auto_assign_topics', params: function() { return {}; }, write: true },
    { name: 'createTopic', method: 'create_topic', params: function(name, parent) { return { name: name, parent: parent || '' }; }, write: true },
    { name: 'createNoteFromDraft', method: 'create_note_from_draft', params: function(title, topic, content) { return { title: title, topic: topic || '', content: content || '' }; }, write: true },
    { name: 'createTag', method: 'create_tag', params: function(name) { return { name: name }; }, write: true },
    { name: 'getAllPending', method: 'get_all_pending' },
    { name: 'retryCascadeTopic', method: 'retry_cascade_topic', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'retryAllCascadeFailures', method: 'retry_all_cascade_failures', params: function() { return {}; }, write: true },
    { name: 'dismissCascadeFailure', method: 'dismiss_cascade_failure', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'retryConvertFile', method: 'retry_convert_file', params: function(file) { return { file: file }; }, write: true },
    { name: 'dismissConvertFailure', method: 'dismiss_convert_failure', params: function(file) { return { file: file }; }, write: true },
    { name: 'getDashboardStatus', method: 'get_dashboard_status' },
    { name: 'getActivityLog', method: 'get_activity_log', params: function(limit) { return { limit: limit || 50 }; } },
    { name: 'resolveTopic', method: 'resolve_topic', params: function(filePath, topic) { return { file_path: filePath, topic: topic }; }, write: true },
    { name: 'keepNoteInTopic', method: 'keep_note_in_topic', params: function(filePath, currentTopic, suggestedTopic) { return { file_path: filePath, current_topic: currentTopic, suggested_topic: suggestedTopic }; }, write: true },
    { name: 'applyTopicPlacementThreshold', method: 'apply_topic_placement_threshold', params: function() { return {}; }, write: true },
    { name: 'mergeDuplicateTopics', method: 'merge_duplicate_topics', params: function() { return {}; }, write: true },
    { name: 'renameTopic', method: 'rename_topic', params: function(oldTopic, newTopic) { return { old_topic: oldTopic, new_topic: newTopic }; }, write: true },
    { name: 'deleteTopic', method: 'delete_topic', params: function(topicName) { return { topic_name: topicName }; }, write: true },
    { name: 'renameTag', method: 'rename_tag', params: function(oldTag, newTag) { return { old_tag: oldTag, new_tag: newTag }; }, write: true },
    { name: 'deleteTag', method: 'delete_tag', params: function(tagName) { return { tag_name: tagName }; }, write: true },
    { name: 'moveFileToTopic', method: 'move_file_to_topic', params: function(filePath, newTopic) { return { file_path: filePath, new_topic: newTopic }; }, write: true },
    { name: 'moveFile', method: 'move_file', params: function(filePath, targetFolder) { return { file_path: filePath, target_folder: targetFolder }; }, write: true },
    { name: 'addTagToFile', method: 'add_tag_to_file', params: function(filePath, tag) { return { file_path: filePath, tag: tag }; }, write: true },

    // ---- 配置 ----
    { name: 'getApiConfig', method: 'get_api_config' },
    { name: 'saveApiConfig', method: 'save_api_config', params: function(cfg) { return cfg; }, write: true },
    { name: 'getUiConfig', method: 'get_ui_config' },
    { name: 'saveUiConfig', method: 'save_ui_config', params: function(cfg) { return cfg; }, write: true },
    { name: 'getComponentsStatus', method: 'get_components_status' },
    { name: 'installComponent', method: 'install_component', params: function(p) { return p; }, write: true },
    { name: 'uninstallComponent', method: 'uninstall_component', params: function(p) { return p; }, write: true },
    { name: 'getThemePreference', method: 'get_theme_preference' },
    { name: 'saveThemePreference', method: 'save_theme_preference', params: function(theme) { return { theme: theme }; }, write: true },

    // ---- 下载 / 转换 / 整合 ----
    { name: 'startWebDownload', method: 'start_web_download', params: function(urls, aiAssist, includeImages) { return { urls: urls, ai_assist: aiAssist, include_images: includeImages }; }, write: true },
    { name: 'startFileConversion', method: 'start_file_conversion', params: function(aiAssist) { return { ai_assist: aiAssist }; }, write: true },
    { name: 'autoConvertPending', method: 'auto_convert_pending', params: function() { return {}; }, write: true },
    { name: 'extractTopics', method: 'extract_topics', params: function(topicCount) { return { topic_count: topicCount }; }, write: true },
    { name: 'startNoteIntegration', method: 'start_note_integration', params: function(autoTopic, topics) { return { auto_topic: autoTopic, topics: topics }; }, write: true },
    { name: 'refreshLog', method: 'refresh_log' },
    { name: 'onFileSelected', method: 'on_file_selected', params: function(path) { return { path: path }; } },
    { name: 'saveFileContent', method: 'save_file_content', params: function(path, content) { return { path: path, content: content }; }, write: true },
    { name: 'readFileRaw', method: 'read_file_raw', params: function(path) { return { path: path }; } },
    { name: 'importFilesDirect', method: 'import_files', params: function(files) { return { files: files }; }, write: true },
    { name: 'importRssFeed', method: 'import_rss_feed', params: function(url, maxItems, fetchArticles) { return { feed_url: url, max_items: maxItems, fetch_articles: fetchArticles }; }, write: true },
    { name: 'listRssSubscriptions', method: 'list_rss_subscriptions', params: function() { return {}; } },
    { name: 'saveRssSubscription', method: 'save_rss_subscription', params: function(url, name) { return { url: url, name: name || '' }; }, write: true },
    { name: 'removeRssSubscription', method: 'remove_rss_subscription', params: function(url) { return { url: url }; }, write: true },
    { name: 'fetchAllRss', method: 'fetch_all_rss', params: function() { return {}; }, write: true },
    { name: 'importTranscript', method: 'import_transcript', params: function(title, content, source) { return { title: title, content: content, source: source }; }, write: true },
    { name: 'listWatchedFolders', method: 'list_watched_folders', params: function() { return {}; } },
    { name: 'addWatchedFolder', method: 'add_watched_folder', params: function(path, recursive) { return { path: path || '', recursive: !!recursive }; }, write: true },
    { name: 'removeWatchedFolder', method: 'remove_watched_folder', params: function(path) { return { path: path || '' }; }, write: true },
    { name: 'scanWatchedFolder', method: 'scan_watched_folder', params: function(path, recursive) { return { path: path || '', recursive: !!recursive }; }, write: true },

    // ---- 知识图谱 / 链接 ----
    { name: 'getBacklinks', method: 'get_backlinks', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'getLinkStats', method: 'get_link_stats', params: function() { return {}; } },
    { name: 'getGraphData', method: 'get_graph_data', params: function(filter) { return { filter: filter || 'topic' }; } },
    { name: 'confirmLink', method: 'confirm_link', params: function(fromPath, toPath) { return { from: fromPath, to: toPath }; }, write: true },
    { name: 'rejectLink', method: 'reject_link', params: function(fromPath, toPath) { return { from: fromPath, to: toPath }; }, write: true },
    { name: 'getSemanticWorkbench', method: 'get_semantic_workbench', params: function(options) { return options || {}; } },
    { name: 'getSemanticDetail', method: 'get_semantic_detail', params: function(kind, id) { return { kind: kind, id: id }; } },
    { name: 'getNoteSemanticContext', method: 'get_note_semantic_context', params: function(path) { return { path: path }; } },
    { name: 'getSemanticObjectWikiPage', method: 'get_semantic_object_wiki_page', params: function(kind, id) { return { kind: kind, id: id }; } },
    { name: 'publishSemanticObjectWikiPage', method: 'publish_semantic_object_wiki_page', params: function(kind, id) { return { kind: kind, id: id }; }, write: true },
    { name: 'getSemanticCompileStatus', method: 'get_semantic_compile_status', params: function() { return {}; } },
    { name: 'getSemanticChanges', method: 'get_semantic_changes', params: function(options) { return options || {}; } },
    { name: 'getTopicBrief', method: 'get_topic_brief', params: function(options) { return options || {}; } },
    { name: 'getIndexHealth', method: 'get_index_health', params: function() { return {}; } },
    { name: 'backupWorkspace', method: 'backup_workspace', params: function(options) { return options || {}; }, write: true },
    { name: 'exportNotes', method: 'export_notes', params: function(options) { return options || {}; }, write: true },
    { name: 'restoreWorkspaceBackup', method: 'restore_workspace_backup', params: function(options) { return options || {}; }, write: true },
    { name: 'startSemanticFullCompile', method: 'start_semantic_full_compile', params: function() { return {}; }, write: true },
    { name: 'startSemanticClaimsCompile', method: 'start_semantic_claims_compile', params: function() { return {}; }, write: true },
    { name: 'reviewSemanticConflict', method: 'review_semantic_conflict', params: function(id, status) { return { id: id, status: status || 'reviewed' }; }, write: true },
    { name: 'scanSemanticConflicts', method: 'scan_semantic_conflicts', params: function() { return {}; }, write: true },
    { name: 'reviewSemanticEntityQuality', method: 'review_semantic_entity_quality', params: function(id, status) { return { id: id, status: status || 'reviewed' }; }, write: true },
    { name: 'enqueueSemanticEntityQuality', method: 'enqueue_semantic_entity_quality', params: function(id) { return { id: id }; }, write: true },
    { name: 'getSemanticEntityMergePreview', method: 'get_semantic_entity_merge_preview', params: function(sourceId, targetId) { return { source_id: sourceId, target_id: targetId }; } },
    { name: 'mergeSemanticEntities', method: 'merge_semantic_entities', params: function(sourceId, targetId) { return { source_id: sourceId, target_id: targetId, confirmed: true }; }, write: true },
    { name: 'updateSemanticClaim', method: 'update_semantic_claim', params: function(id, statement, scope, claimType) { return { id: id, statement: statement, scope: scope || '', claim_type: claimType }; }, write: true },
    { name: 'verifySemanticClaim', method: 'verify_semantic_claim', params: function(id, agent) { return { id: id, agent: agent }; }, write: true },
    { name: 'setSemanticClaimStatus', method: 'set_semantic_claim_status', params: function(id, status) { return { id: id, status: status }; }, write: true },
    { name: 'setSemanticEvidenceStatus', method: 'set_semantic_evidence_status', params: function(id, status) { return { id: id, status: status }; }, write: true },
    { name: 'getSemanticTopicWikiPage', method: 'get_semantic_topic_wiki_page', params: function(topic) { return { topic: topic }; } },
    { name: 'publishSemanticTopicWikiPage', method: 'publish_semantic_topic_wiki_page', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'addSemanticEntityAlias', method: 'add_semantic_entity_alias', params: function(id, alias) { return { id: id, alias: alias }; }, write: true },
    { name: 'confirmAllLinks', method: 'confirm_all_links', params: function() { return {}; }, write: true },
    { name: 'syncWikiWithFiles', method: 'sync_wiki_with_files', params: function() { return {}; }, write: true },

    // ---- LLM 改写 ----
    { name: 'llmRewriteStream', method: 'llm_rewrite_stream', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'llmRewriteApply', method: 'llm_rewrite_apply', params: function(filePath, rewrittenText) { return { file_path: filePath, rewritten_text: rewrittenText }; }, write: true },

    // ---- AI 主题 ----
    { name: 'aiTopicAnalyze', method: 'ai_topic_analyze', params: function() { return {}; }, write: true },
    { name: 'aiTopicSurvey', method: 'ai_topic_survey', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'applyTopicSuggestion', method: 'apply_topic_suggestion', params: function(suggestion) { return { suggestion: suggestion }; }, write: true },

    // ---- RAG ----
    { name: 'ragChat', method: 'rag_chat', params: function(question, topics, tags, currentFile, options) { var opts = options || {}; return { question: question, topics: topics || null, tags: tags || null, current_file: currentFile || null, history: opts.history || [], force_intent: opts.forceIntent || null, selection_lookup: !!opts.selectionLookup, selection_route: opts.selectionRoute || 'auto', selection_context: opts.selectionContext || '' }; } },
    { name: 'ragRebuildIndex', method: 'rag_rebuild_index', params: function() { return {}; }, write: true },
    { name: 'ragIndexStatus', method: 'rag_index_status', params: function() { return {}; } },
    { name: 'archiveChatAnswer', method: 'archive_chat_answer', params: function(payload) { return payload || {}; }, write: true },
    { name: 'runKbLint', method: 'run_kb_lint', params: function() { return {}; }, write: true },
    { name: 'getDuplicateReview', method: 'get_duplicate_review', params: function(filePath, relatedFile) { return { file_path: filePath, related_file: relatedFile }; } },
    { name: 'mergeDuplicateNotes', method: 'merge_duplicate_notes', params: function(filePath, relatedFile, title) { return { file_path: filePath, related_file: relatedFile, title: title || '' }; }, write: true },
    { name: 'mergeNoteGroup', method: 'merge_note_group', params: function(filePaths, title, deleteAuthorized) { return { file_paths: filePaths || [], title: title || '', delete_authorized: deleteAuthorized === true }; }, write: true },
    { name: 'scanMergeCandidates', method: 'scan_merge_candidates', params: function(preset, overrides) { return { preset: preset || 'balanced', overrides: overrides || {} }; }, write: true },
    { name: 'suggestTopicMergeNames', method: 'suggest_topic_merge_names', params: function(topics) { return { topics: topics || [] }; }, write: true },
    { name: 'previewTopicMerge', method: 'preview_topic_merge', params: function(topics, newTopic) { return { topics: topics || [], new_topic: newTopic || '' }; } },
    { name: 'mergeSimilarTopics', method: 'merge_similar_topics', params: function(topics, newTopic) { return { topics: topics || [], new_topic: newTopic || '' }; }, write: true },

    // ---- CLI Agent 桥接（claude/opencode/codex/gemini）----
    { name: 'listCliAgents', method: 'list_cli_agents', params: function() { return {}; } },
    { name: 'runCliAgent', method: 'run_cli_agent', params: function(agentId, prompt, workspacePath, options) { var opts = options || {}; return { agent_id: agentId, prompt: prompt, workspace_path: workspacePath || '', new_session: !!opts.newSession }; }, write: true },
    { name: 'stopCliAgent', method: 'stop_cli_agent', params: function() { return {}; }, write: true },
    { name: 'clearCliAgentSession', method: 'clear_cli_agent_session', params: function(agentId, workspacePath) { return { agent_id: agentId || '', workspace_path: workspacePath || '' }; }, write: true },
    { name: 'generateVaultAgentsMd', method: 'generate_vault_agents_md', params: function() { return {}; }, write: true },

    // ---- 规则 ----
    { name: 'getProjectRules', method: 'get_project_rules', params: function() { return {}; } },
    { name: 'saveProjectRules', method: 'save_project_rules', params: function(rules) { return { rules: rules }; }, write: true },

    // ---- Workspace rules / Ingest ----
    { name: 'getWorkspaceRules', method: 'get_workspace_rules', params: function() { return {}; } },
    { name: 'saveWorkspaceRules', method: 'save_workspace_rules', params: function(opts) { return opts || {}; }, write: true },
    { name: 'needsWorkspaceRulesSetup', method: 'needs_workspace_rules_setup', params: function() { return {}; } },
    { name: 'startIngest', method: 'start_ingest', params: function(options) { var opts = options || {}; return { mode: opts.mode || 'full', file_paths: opts.file_paths || [], resume: !!opts.resume }; }, write: true },
    { name: 'cancelIngest', method: 'cancel_ingest', params: function() { return {}; }, write: true },
    { name: 'retryIngest', method: 'retry_ingest', params: function(options) { var opts = options || {}; return { mode: opts.mode || 'full', file_paths: opts.file_paths || [] }; }, write: true },
    { name: 'getIngestStatus', method: 'get_ingest_status', params: function() { return {}; } },
    { name: 'checkIngestUpdates', method: 'check_ingest_updates', params: function(options) { var opts = options || {}; return { file_paths: opts.file_paths || [] }; } },
    { name: 'ensureIngest', method: 'ensure_ingest', params: function(options) { var opts = options || {}; return { file_paths: opts.file_paths || [] }; }, write: true },
    { name: 'getJobs', method: 'get_jobs', params: function(options) { var opts = options || {}; return { include_finished: opts.include_finished !== false, limit: opts.limit || 50 }; } },

    // ---- 搜索 ----
    { name: 'searchFiles', method: 'search_files', params: function(query) { return { query: query }; } },

    // ---- 文件操作 ----
    { name: 'deleteFile', method: 'delete_file', params: function(path) { return { path: path }; }, write: true },
    { name: 'revealInFinder', method: 'reveal_in_finder', params: function(path) { return { path: path }; } }
];

var generatedApi = {};
API_DEFS.forEach(function(def) {
    generatedApi[def.name] = createApiFunction(def);
});

window.api = Object.assign({}, generatedApi, {
    invoke: pyCall,

    // 特殊 API（涉及 Tauri 原生对话框 / 多步逻辑 / 分页预览）
    openWorkspace: openWorkspace,
    createSampleWorkspace: createSampleWorkspace,
    getWorkspaceStatus: getWorkspaceStatus,
    addFiles: addFiles,
    importFilesToWorkspace: importFilesToWorkspace,
    browseFolder: browseFolder,
    openArchiveDialog: openArchiveDialog,
    getFilePreview: getFilePreview,

    // 窗口控制
    moveWindow: moveWindow,
    minimizeWindow: minimizeWindow,
    maximizeWindow: maximizeWindow,
    closeWindow: closeWindow,
    openFileInNewWindow: openFileInNewWindow
});

window.getTauriEventAPI = getTauriEventAPI;
window.checkIsTauri = checkIsTauri;
window.getTauriInvoke = getTauriInvoke;

})();
