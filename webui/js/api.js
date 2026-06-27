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
    var msg = String(e.message || e);
    return msg.indexOf('timeout') !== -1 ||
        msg.indexOf('aborted') !== -1 ||
        msg.indexOf('cancelled') !== -1 ||
        msg.indexOf('invoke') !== -1 ||
        msg.indexOf('sidecar') !== -1;
}

function _translateError(e) {
    var msg = String(e && (e.message || e));
    if (msg.indexOf('Not running in Tauri') !== -1) {
        return new Error('应用未在 Tauri 环境中运行');
    }
    if (msg.indexOf('Tauri invoke not available') !== -1) {
        return new Error('Tauri 调用接口不可用，请重启应用');
    }
    if (msg.indexOf('timeout') !== -1) {
        return new Error('请求超时，请稍后重试');
    }
    if (msg.indexOf('sidecar') !== -1 || msg.indexOf('python') !== -1) {
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
    { name: 'getAllTags', method: 'get_all_tags' },
    { name: 'autoTagFiles', method: 'auto_tag_files', params: function(dryRun) { return { dry_run: !!dryRun }; } },
    { name: 'saveTagsMd', method: 'save_tags_md' },
    { name: 'ensureTagsMd', method: 'ensure_tags_md' },
    { name: 'autoAssignTopic', method: 'auto_assign_topic', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'batchAutoAssignTopics', method: 'batch_auto_assign_topics', params: function() { return {}; } },
    { name: 'createTopic', method: 'create_topic', params: function(name) { return { name: name }; } },
    { name: 'createTopicFolder', method: 'create_topic_folder', params: function(name, parentPath, level) { return { name: name, parent_path: parentPath || '', level: level || 0 }; } },
    { name: 'createTag', method: 'create_tag', params: function(name) { return { name: name }; } },
    { name: 'getPendingTopics', method: 'get_pending_topics' },
    { name: 'getAllPending', method: 'get_all_pending' },
    { name: 'getActivityLog', method: 'get_activity_log', params: function(limit) { return { limit: limit || 50 }; } },
    { name: 'resolveTopic', method: 'resolve_topic', params: function(filePath, topic) { return { file_path: filePath, topic: topic }; } },
    { name: 'mergeDuplicateTopics', method: 'merge_duplicate_topics', params: function() { return {}; } },
    { name: 'renameTopic', method: 'rename_topic', params: function(oldTopic, newTopic) { return { old_topic: oldTopic, new_topic: newTopic }; } },
    { name: 'deleteTopic', method: 'delete_topic', params: function(topicName) { return { topic_name: topicName }; } },
    { name: 'renameTag', method: 'rename_tag', params: function(oldTag, newTag) { return { old_tag: oldTag, new_tag: newTag }; } },
    { name: 'deleteTag', method: 'delete_tag', params: function(tagName) { return { tag_name: tagName }; } },
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
    { name: 'startWebDownload', method: 'start_web_download', params: function(urls, aiAssist, includeImages) { return { urls: urls, ai_assist: aiAssist, include_images: includeImages }; } },
    { name: 'startFileConversion', method: 'start_file_conversion', params: function(aiAssist) { return { ai_assist: aiAssist }; } },
    { name: 'autoConvertPending', method: 'auto_convert_pending', params: function() { return {}; } },
    { name: 'extractTopics', method: 'extract_topics', params: function(topicCount) { return { topic_count: topicCount }; } },
    { name: 'startNoteIntegration', method: 'start_note_integration', params: function(autoTopic, topics) { return { auto_topic: autoTopic, topics: topics }; } },
    { name: 'refreshLog', method: 'refresh_log' },
    { name: 'onFileSelected', method: 'on_file_selected', params: function(path) { return { path: path }; } },
    { name: 'canPreviewFile', method: 'can_preview_file', params: function(path) { return { path: path }; } },
    { name: 'saveFileContent', method: 'save_file_content', params: function(path, content) { return { path: path, content: content }; }, write: true },
    { name: 'readFileRaw', method: 'read_file_raw', params: function(path) { return { path: path }; } },
    { name: 'importFilesDirect', method: 'import_files', params: function(files) { return { files: files }; }, write: true },
    { name: 'importRssFeed', method: 'import_rss_feed', params: function(url, maxItems, fetchArticles) { return { feed_url: url, max_items: maxItems, fetch_articles: fetchArticles }; }, write: true },
    { name: 'listRssSubscriptions', method: 'list_rss_subscriptions', params: function() { return {}; } },
    { name: 'saveRssSubscription', method: 'save_rss_subscription', params: function(url, name) { return { url: url, name: name || '' }; }, write: true },
    { name: 'removeRssSubscription', method: 'remove_rss_subscription', params: function(url) { return { url: url }; }, write: true },
    { name: 'fetchAllRss', method: 'fetch_all_rss', params: function() { return {}; }, write: true },
    { name: 'importTranscript', method: 'import_transcript', params: function(title, content, source) { return { title: title, content: content, source: source }; }, write: true },

    // ---- 知识图谱 / 链接 ----
    { name: 'discoverLinks', method: 'discover_links', params: function() { return {}; } },
    { name: 'getBacklinks', method: 'get_backlinks', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'getLinkStats', method: 'get_link_stats', params: function() { return {}; } },
    { name: 'getGraphData', method: 'get_graph_data', params: function(filter) { return { filter: filter || 'topic' }; } },
    { name: 'confirmLink', method: 'confirm_link', params: function(fromPath, toPath) { return { from: fromPath, to: toPath }; }, write: true },
    { name: 'rejectLink', method: 'reject_link', params: function(fromPath, toPath) { return { from: fromPath, to: toPath }; }, write: true },
    { name: 'confirmAllLinks', method: 'confirm_all_links', params: function() { return {}; }, write: true },
    { name: 'syncWikiWithFiles', method: 'sync_wiki_with_files', params: function() { return {}; }, write: true },
    { name: 'getTopicFiles', method: 'get_topic_files', params: function(topicName, level) { return { topic_name: topicName, level: level }; } },
    { name: 'generateAbstract', method: 'generate_abstract', params: function(topicName, level) { return { topic_name: topicName, level: level }; }, write: true },

    // ---- LLM 改写 ----
    { name: 'llmRewrite', method: 'llm_rewrite', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'llmRewriteStream', method: 'llm_rewrite_stream', params: function(filePath) { return { file_path: filePath }; } },
    { name: 'llmRewriteApply', method: 'llm_rewrite_apply', params: function(filePath, rewrittenText) { return { file_path: filePath, rewritten_text: rewrittenText }; }, write: true },

    // ---- AI 主题 ----
    { name: 'aiTopicAnalyze', method: 'ai_topic_analyze', params: function() { return {}; } },
    { name: 'aiTopicSurvey', method: 'ai_topic_survey', params: function(topic) { return { topic: topic }; }, write: true },
    { name: 'applyTopicSuggestion', method: 'apply_topic_suggestion', params: function(suggestion) { return { suggestion: suggestion }; }, write: true },

    // ---- RAG ----
    { name: 'ragChat', method: 'rag_chat', params: function(question, topics, tags, currentFile) { return { question: question, topics: topics || null, tags: tags || null, current_file: currentFile || null }; } },
    { name: 'ragRebuildIndex', method: 'rag_rebuild_index', params: function() { return {}; }, write: true },
    { name: 'ragIndexStatus', method: 'rag_index_status', params: function() { return {}; } },
    { name: 'archiveChatAnswer', method: 'archive_chat_answer', params: function(payload) { return payload || {}; }, write: true },
    { name: 'runKbLint', method: 'run_kb_lint', params: function() { return {}; }, write: true },
    { name: 'getChangelog', method: 'get_changelog', params: function(limit) { return { limit: limit || 50 }; } },
    { name: 'checkAndGenerateSurveys', method: 'check_and_generate_surveys', params: function() { return {}; }, write: true },

    // ---- CLI Agent 桥接（claude/opencode/codex/gemini）----
    { name: 'listCliAgents', method: 'list_cli_agents', params: function() { return {}; } },
    { name: 'runCliAgent', method: 'run_cli_agent', params: function(agentId, prompt, workspacePath) { return { agent_id: agentId, prompt: prompt, workspace_path: workspacePath || '' }; }, write: true },
    { name: 'generateVaultAgentsMd', method: 'generate_vault_agents_md', params: function() { return {}; }, write: true },

    // ---- 用户画像 / 规则 ----
    { name: 'getUserProfile', method: 'get_user_profile', params: function() { return {}; } },
    { name: 'saveUserProfile', method: 'save_user_profile', params: function(data) { return data; }, write: true },
    { name: 'getProjectRules', method: 'get_project_rules', params: function() { return {}; } },
    { name: 'saveProjectRules', method: 'save_project_rules', params: function(rules) { return { rules: rules }; }, write: true },

    // ---- Schema / Ingest ----
    { name: 'ensureSchema', method: 'ensure_schema', params: function() { return {}; } },
    { name: 'getSchema', method: 'get_schema', params: function() { return {}; } },
    { name: 'needsSchemaSetup', method: 'needs_schema_setup', params: function() { return {}; } },
    { name: 'getSchemaTemplate', method: 'get_schema_template', params: function() { return {}; } },
    { name: 'saveSchema', method: 'save_schema', params: function(content) { return { content: content }; }, write: true },
    { name: 'startIngest', method: 'start_ingest', params: function(options) { var opts = options || {}; return { mode: opts.mode || 'full', file_paths: opts.file_paths || [] }; }, write: true },
    { name: 'cancelIngest', method: 'cancel_ingest', params: function() { return {}; }, write: true },
    { name: 'retryIngest', method: 'retry_ingest', params: function(options) { var opts = options || {}; return { mode: opts.mode || 'full', file_paths: opts.file_paths || [] }; }, write: true },
    { name: 'getIngestStatus', method: 'get_ingest_status', params: function() { return {}; } },
    { name: 'ensureIngest', method: 'ensure_ingest', params: function(options) { var opts = options || {}; return { file_paths: opts.file_paths || [] }; }, write: true },

    // ---- 搜索 ----
    { name: 'searchFiles', method: 'search_files', params: function(query) { return { query: query }; } },

    // ---- 云同步 ----
    { name: 'cloudSyncListProviders', method: 'cloud_sync_list_providers' },
    { name: 'cloudSyncAuth', method: 'cloud_sync_auth', params: function(provider, credentials) { return { provider_name: provider, credentials: credentials }; }, write: true },
    { name: 'cloudSyncPush', method: 'cloud_sync_push', params: function(provider) { return { provider_name: provider }; }, write: true },
    { name: 'cloudSyncPull', method: 'cloud_sync_pull', params: function(provider) { return { provider_name: provider }; }, write: true },
    { name: 'cloudSyncStatus', method: 'cloud_sync_status', params: function(provider) { return { provider_name: provider }; } },
    { name: 'cloudSyncSaveConfig', method: 'cloud_sync_save_config', params: function(provider, config) { return { provider_name: provider, config: config }; }, write: true },
    { name: 'cloudSyncLoadConfig', method: 'cloud_sync_load_config', params: function(provider) { return { provider_name: provider }; } },
    { name: 'cloudSyncDisconnect', method: 'cloud_sync_disconnect', params: function(provider) { return { provider_name: provider }; }, write: true }
];

var generatedApi = {};
API_DEFS.forEach(function(def) {
    generatedApi[def.name] = createApiFunction(def);
});

window.api = Object.assign({}, generatedApi, {
    invoke: pyCall,
    getApiPort: function() { return 0; },

    // 特殊 API（涉及 Tauri 原生对话框 / 多步逻辑 / 分页预览）
    openWorkspace: openWorkspace,
    getWorkspaceStatus: getWorkspaceStatus,
    addFiles: addFiles,
    importFilesToWorkspace: importFilesToWorkspace,
    browseFolder: browseFolder,
    getFilePreview: getFilePreview,

    // 窗口控制
    moveWindow: moveWindow,
    minimizeWindow: minimizeWindow,
    maximizeWindow: maximizeWindow,
    closeWindow: closeWindow,
    openFileInNewWindow: openFileInNewWindow
});

window.getTauriEventAPI = getTauriEventAPI;

})();

const api = window.api;
