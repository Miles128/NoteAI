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

async function pyCall(method, params) {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        if (!invoke) throw new Error('Tauri invoke not available');
        try {
            var result = await invoke('py_call', {
                method: method,
                params: params || {}
            });
            return result;
        } catch (e) {
            console.error('[API] pyCall error:', method, e);
            throw e;
        }
    }
    console.error('[API] Not running in Tauri');
    throw new Error('Not running in Tauri');
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

async function openWorkspace() {
    if (checkIsTauri()) {
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
    return pyCall('open_workspace');
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

async function getWorkspaceTree() {
    return pyCall('get_workspace_tree');
}

async function getAllTags() {
    return pyCall('get_all_tags');
}

async function getTopicTree() {
    return pyCall('get_topic_tree');
}

async function autoTagFiles(dryRun) {
    return pyCall('auto_tag_files', { dry_run: !!dryRun });
}

async function saveTagsMd() {
    return pyCall('save_tags_md');
}

async function autoAssignTopic(filePath) {
    return pyCall('auto_assign_topic', { file_path: filePath });
}

async function batchAutoAssignTopics() {
    return pyCall('batch_auto_assign_topics', {});
}

async function createTopic(name) {
    return pyCall('create_topic', { name: name });
}

async function createTopicFolder(name, parentPath, level) {
    return pyCall('create_topic_folder', { name: name, parent_path: parentPath || '', level: level || 0 });
}

async function createTag(name) {
    return pyCall('create_tag', { name: name });
}

async function getPendingTopics() {
    return pyCall('get_pending_topics');
}

async function getAllPending() {
    return pyCall('get_all_pending');
}

async function getActivityLog(limit) {
    return pyCall('get_activity_log', { limit: limit || 50 });
}

async function resolveTopic(filePath, topic) {
    return pyCall('resolve_topic', { file_path: filePath, topic: topic });
}

async function mergeDuplicateTopics() {
    return pyCall('merge_duplicate_topics', {});
}

async function renameTopic(oldTopic, newTopic) {
    return pyCall('rename_topic', { old_topic: oldTopic, new_topic: newTopic });
}

async function deleteTopic(topicName) {
    return pyCall('delete_topic', { topic_name: topicName });
}

async function renameTag(oldTag, newTag) {
    return pyCall('rename_tag', { old_tag: oldTag, new_tag: newTag });
}

async function deleteTag(tagName) {
    return pyCall('delete_tag', { tag_name: tagName });
}

async function moveFileToTopic(filePath, newTopic) {
    return pyCall('move_file_to_topic', { file_path: filePath, new_topic: newTopic });
}

async function moveFile(filePath, targetFolder) {
    return pyCall('move_file', { file_path: filePath, target_folder: targetFolder });
}

async function addTagToFile(filePath, tag) {
    return pyCall('add_tag_to_file', { file_path: filePath, tag: tag });
}

async function ensureTagsMd() {
    return pyCall('ensure_tags_md');
}

async function getApiConfig() {
    return pyCall('get_api_config');
}

async function saveApiConfig(cfg) {
    return pyCall('save_api_config', cfg);
}

async function getUiConfig() {
    return pyCall('get_ui_config');
}

async function saveUiConfig(cfg) {
    return pyCall('save_ui_config', cfg);
}

async function getThemePreference() {
    return pyCall('get_theme_preference');
}

async function saveThemePreference(theme) {
    return pyCall('save_theme_preference', { theme: theme });
}

async function addFiles() {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        var files = await invoke('open_file_dialog');
        return files || [];
    }
    return pyCall('add_files');
}

async function importFilesToWorkspace() {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        var files = await invoke('open_file_dialog');
        if (!files || files.length === 0) return { cancelled: true };
        return pyCall('import_files', { files: files });
    }
    return pyCall('import_files');
}

async function importFilesDirect(files) {
    return pyCall('import_files', { files: files });
}

async function browseFolder() {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        var folder = await invoke('open_folder_dialog');
        return folder || '';
    }
    return pyCall('browse_folder');
}

async function startWebDownload(urls, aiAssist, includeImages) {
    return pyCall('start_web_download', {
        urls: urls,
        ai_assist: aiAssist,
        include_images: includeImages
    });
}

async function importRssFeed(url, maxItems, fetchArticles) {
    return pyCall('import_rss_feed', { feed_url: url, max_items: maxItems, fetch_articles: fetchArticles });
}

async function importTranscript(title, content, source) {
    return pyCall('import_transcript', { title: title, content: content, source: source });
}

async function saveRssSubscriptionApi(url, name) {
    return pyCall('save_rss_subscription', { url: url, name: name });
}

async function removeRssSubscriptionApi(url) {
    return pyCall('remove_rss_subscription', { url: url });
}

async function listRssSubscriptions() {
    return pyCall('list_rss_subscriptions', {});
}

async function fetchAllRss() {
    return pyCall('fetch_all_rss', {});
}

async function startFileConversion(aiAssist) {
    return pyCall('start_file_conversion', { ai_assist: aiAssist });
}

async function autoConvertPending() {
    return pyCall('auto_convert_pending', {});
}

async function ensureSchema() {
    return pyCall('ensure_schema', {});
}

async function getSchema() {
    return pyCall('get_schema', {});
}

async function needsSchemaSetup() {
    return pyCall('needs_schema_setup', {});
}

async function getSchemaTemplate() {
    return pyCall('get_schema_template', {});
}

async function saveSchema(content) {
    return pyCall('save_schema', { content: content });
}

async function startIngest(options) {
    var opts = options || {};
    return pyCall('start_ingest', {
        mode: opts.mode || 'full',
        file_paths: opts.file_paths || []
    });
}

async function ensureIngest(options) {
    var opts = options || {};
    return pyCall('ensure_ingest', {
        file_paths: opts.file_paths || []
    });
}

async function cancelIngest() {
    return pyCall('cancel_ingest', {});
}

async function retryIngest(options) {
    var opts = options || {};
    return pyCall('retry_ingest', {
        mode: opts.mode || 'full',
        file_paths: opts.file_paths || []
    });
}

async function getIngestStatus() {
    return pyCall('get_ingest_status', {});
}

async function extractTopics(topicCount) {
    return pyCall('extract_topics', { topic_count: topicCount });
}

async function startNoteIntegration(autoTopic, topics) {
    return pyCall('start_note_integration', {
        auto_topic: autoTopic,
        topics: topics
    });
}

async function refreshLog() {
    return pyCall('refresh_log');
}

async function onFileSelected(path) {
    return pyCall('on_file_selected', { path: path });
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

async function canPreviewFile(path) {
    return pyCall('can_preview_file', { path: path });
}

async function saveFileContent(path, content) {
    return pyCall('save_file_content', { path: path, content: content });
}

async function readFileRaw(path) {
    return pyCall('read_file_raw', { path: path });
}

async function discoverLinks() {
    return pyCall('discover_links', {});
}

async function getBacklinks(filePath) {
    return pyCall('get_backlinks', { file_path: filePath });
}

async function getLinkStats() {
    return pyCall('get_link_stats', {});
}

async function getGraphData(filter) {
    return pyCall('get_graph_data', { filter: filter || 'topic' });
}

async function confirmLink(fromPath, toPath) {
    return pyCall('confirm_link', { from: fromPath, to: toPath });
}

async function rejectLink(fromPath, toPath) {
    return pyCall('reject_link', { from: fromPath, to: toPath });
}

async function confirmAllLinks() {
    return pyCall('confirm_all_links', {});
}

async function syncWikiWithFiles() {
    return pyCall('sync_wiki_with_files', {});
}

async function getTopicFiles(topicName, level) {
    return pyCall('get_topic_files', { topic_name: topicName, level: level });
}

async function generateAbstract(topicName, level) {
    return pyCall('generate_abstract', { topic_name: topicName, level: level });
}

async function llmRewrite(filePath) {
    return pyCall('llm_rewrite', { file_path: filePath });
}

async function llmRewriteStream(filePath) {
    return pyCall('llm_rewrite_stream', { file_path: filePath });
}

async function llmRewriteApply(filePath, rewrittenText) {
    return pyCall('llm_rewrite_apply', { file_path: filePath, rewritten_text: rewrittenText });
}

async function aiTopicAnalyze() {
    return pyCall('ai_topic_analyze', {});
}

async function aiTopicSurvey(topic) {
    return pyCall('ai_topic_survey', { topic: topic });
}

async function applyTopicSuggestion(suggestion) {
    return pyCall('apply_topic_suggestion', { suggestion: suggestion });
}

async function ragChat(question, topics, tags, currentFile) {
    return pyCall('rag_chat', { question, topics: topics || null, tags: tags || null, current_file: currentFile || null });
}

async function ragRebuildIndex() {
    return pyCall('rag_rebuild_index', {});
}

async function archiveChatAnswer(payload) {
    return pyCall('archive_chat_answer', payload || {});
}

async function runKbLint() {
    return pyCall('run_kb_lint', {});
}

async function getChangelog(limit) {
    return pyCall('get_changelog', { limit: limit || 50 });
}

async function checkAndGenerateSurveys() {
    return pyCall('check_and_generate_surveys', {});
}

async function getUserProfile() {
    return pyCall('get_user_profile', {});
}

async function saveUserProfile(data) {
    return pyCall('save_user_profile', data);
}

async function getProjectRules() {
    return pyCall('get_project_rules', {});
}

async function saveProjectRules(rules) {
    return pyCall('save_project_rules', { rules: rules });
}

async function cloudSyncListProviders() { return pyCall('cloud_sync_list_providers'); }
async function cloudSyncAuth(provider, credentials) { return pyCall('cloud_sync_auth', { provider_name: provider, credentials: credentials }); }
async function cloudSyncPush(provider) { return pyCall('cloud_sync_push', { provider_name: provider }); }
async function cloudSyncPull(provider) { return pyCall('cloud_sync_pull', { provider_name: provider }); }
async function cloudSyncStatus(provider) { return pyCall('cloud_sync_status', { provider_name: provider }); }
async function cloudSyncSaveConfig(provider, config) { return pyCall('cloud_sync_save_config', { provider_name: provider, config: config }); }
async function cloudSyncLoadConfig(provider) { return pyCall('cloud_sync_load_config', { provider_name: provider }); }
async function cloudSyncDisconnect(provider) { return pyCall('cloud_sync_disconnect', { provider_name: provider }); }

window.api = {
    invoke: pyCall,
    getApiPort: function() { return 0; },

    openWorkspace: openWorkspace,
    getWorkspaceStatus: getWorkspaceStatus,
    getWorkspaceTree: getWorkspaceTree,
    getAllTags: getAllTags,
    getTopicTree: getTopicTree,
    autoTagFiles: autoTagFiles,
    saveTagsMd: saveTagsMd,
    ensureTagsMd: ensureTagsMd,
    autoAssignTopic: autoAssignTopic,
    batchAutoAssignTopics: batchAutoAssignTopics,
    createTopic: createTopic,
    createTopicFolder: createTopicFolder,
    createTag: createTag,
    getPendingTopics: getPendingTopics,
    getAllPending: getAllPending,
    getActivityLog: getActivityLog,
    resolveTopic: resolveTopic,
    mergeDuplicateTopics: mergeDuplicateTopics,
    renameTopic: renameTopic,
    deleteTopic: deleteTopic,
    renameTag: renameTag,
    deleteTag: deleteTag,
    moveFileToTopic: moveFileToTopic,
    moveFile: moveFile,
    addTagToFile: addTagToFile,
    getApiConfig: getApiConfig,
    saveApiConfig: saveApiConfig,
    getUiConfig: getUiConfig,
    saveUiConfig: saveUiConfig,
    getThemePreference: getThemePreference,
    saveThemePreference: saveThemePreference,
    addFiles: addFiles,
    importFilesToWorkspace: importFilesToWorkspace,
    importFilesDirect: importFilesDirect,
    browseFolder: browseFolder,
    startWebDownload: startWebDownload,
    importRssFeed: importRssFeed,
    importTranscript: importTranscript,
    saveRssSubscriptionApi: saveRssSubscriptionApi,
    removeRssSubscriptionApi: removeRssSubscriptionApi,
    listRssSubscriptions: listRssSubscriptions,
    fetchAllRss: fetchAllRss,
    startFileConversion: startFileConversion,
    autoConvertPending: autoConvertPending,
    extractTopics: extractTopics,
    startNoteIntegration: startNoteIntegration,
    refreshLog: refreshLog,
    onFileSelected: onFileSelected,
    getFilePreview: getFilePreview,
    canPreviewFile: canPreviewFile,
    saveFileContent: saveFileContent,
    readFileRaw: readFileRaw,
    syncWikiWithFiles: syncWikiWithFiles,
    getTopicFiles: getTopicFiles,
    generateAbstract: generateAbstract,

    moveWindow: function() { return window.WindowManager && window.WindowManager.moveWindow.apply(window.WindowManager, arguments); },
    minimizeWindow: function() { return window.WindowManager && window.WindowManager.minimizeWindow(); },
    maximizeWindow: function() { return window.WindowManager && window.WindowManager.maximizeWindow(); },
    closeWindow: function() { return window.WindowManager && window.WindowManager.closeWindow(); },
    openFileInNewWindow: function(path, name) { return window.WindowManager && window.WindowManager.openFileInNewWindow(path, name); },

    discoverLinks: discoverLinks,
    getBacklinks: getBacklinks,
    getLinkStats: getLinkStats,
    getGraphData: getGraphData,
    confirmLink: confirmLink,
    rejectLink: rejectLink,
    confirmAllLinks: confirmAllLinks,
    llmRewrite: llmRewrite,
    llmRewriteStream: llmRewriteStream,
    llmRewriteApply: llmRewriteApply,
    aiTopicAnalyze: aiTopicAnalyze,
    aiTopicSurvey: aiTopicSurvey,
    applyTopicSuggestion: applyTopicSuggestion,
    ragChat: ragChat,
    ragRebuildIndex: ragRebuildIndex,
    archiveChatAnswer: archiveChatAnswer,
    runKbLint: runKbLint,
    getChangelog: getChangelog,
    checkAndGenerateSurveys: checkAndGenerateSurveys,
    getUserProfile: getUserProfile,
    saveUserProfile: saveUserProfile,
    getProjectRules: getProjectRules,
    saveProjectRules: saveProjectRules,

    cloudSyncListProviders: cloudSyncListProviders,
    cloudSyncAuth: cloudSyncAuth,
    cloudSyncPush: cloudSyncPush,
    cloudSyncPull: cloudSyncPull,
    cloudSyncStatus: cloudSyncStatus,
    cloudSyncSaveConfig: cloudSyncSaveConfig,
    cloudSyncLoadConfig: cloudSyncLoadConfig,
    cloudSyncDisconnect: cloudSyncDisconnect,

    ensureSchema: ensureSchema,
    getSchema: getSchema,
    saveSchema: saveSchema,
    needsSchemaSetup: needsSchemaSetup,
    getSchemaTemplate: getSchemaTemplate,
    startIngest: startIngest,
    ensureIngest: ensureIngest,
    cancelIngest: cancelIngest,
    retryIngest: retryIngest,
    getIngestStatus: getIngestStatus
};

})();

const api = window.api;
