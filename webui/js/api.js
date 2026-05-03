var _isTauri = typeof window !== 'undefined' && (window.__TAURI_INTERNALS__ || window.__TAURI__);

function getTauriInvoke() {
    if (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke) {
        return window.__TAURI__.core.invoke;
    }
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke) {
        return window.__TAURI_INTERNALS__.invoke;
    }
    return null;
}

async function pyCall(method, params) {
    if (_isTauri) {
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

async function openWorkspace() {
    if (_isTauri) {
        var invoke = getTauriInvoke();
        var folder = await invoke('open_folder_dialog');
        if (folder) {
            await invoke('set_workspace_path', { path: folder });
            await pyCall('set_workspace_path', { path: folder });
            return { success: true, workspace_path: folder };
        }
        return { success: false, message: '未选择文件夹' };
    }
    return pyCall('open_workspace');
}

async function getWorkspaceStatus() {
    var result = await pyCall('get_workspace_status');
    if (result && result.is_set && _isTauri) {
        var invoke = getTauriInvoke();
        await invoke('set_workspace_path', { path: result.workspace_path });
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

async function autoTagFiles() {
    return pyCall('auto_tag_files');
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

async function createTag(name) {
    return pyCall('create_tag', { name: name });
}

async function getPendingTopics() {
    return pyCall('get_pending_topics');
}

async function resolveTopic(filePath, topic) {
    return pyCall('resolve_topic', { file_path: filePath, topic: topic });
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
    if (_isTauri) {
        var invoke = getTauriInvoke();
        var files = await invoke('open_file_dialog');
        return files || [];
    }
    return pyCall('add_files');
}

async function importFilesToWorkspace() {
    if (_isTauri) {
        var invoke = getTauriInvoke();
        var files = await invoke('open_file_dialog');
        if (!files || files.length === 0) return { cancelled: true };
        return pyCall('import_files', { files: files });
    }
    return pyCall('import_files');
}

async function browseFolder() {
    if (_isTauri) {
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

async function startFileConversion(aiAssist) {
    return pyCall('start_file_conversion', { ai_assist: aiAssist });
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
    return pyCall('get_file_preview', { path: path });
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

async function getRelationGraph() {
    return pyCall('get_relation_graph', {});
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

function getTauriWindow() {
    if (window.__TAURI__ && window.__TAURI__.window && window.__TAURI__.window.getCurrent) {
        return window.__TAURI__.window.getCurrent();
    }
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.window && window.__TAURI_INTERNALS__.window.getCurrent) {
        return window.__TAURI_INTERNALS__.window.getCurrent();
    }
    return null;
}

function moveWindow(dx, dy) {}

function minimizeWindow() {
    if (_isTauri) {
        var win = getTauriWindow();
        if (win) win.minimize();
    }
}

function maximizeWindow() {
    if (_isTauri) {
        var win = getTauriWindow();
        if (win) win.toggleMaximize();
    }
}

function closeWindow() {
    if (_isTauri) {
        var win = getTauriWindow();
        if (win) win.close();
    }
}

async function openFileInNewWindow(path, name) {
    if (_isTauri) {
        var invoke = getTauriInvoke();
        if (invoke) {
            return invoke('open_file_in_new_window', { path: path, name: name || null });
        }
    }
    console.error('[API] Not running in Tauri');
    throw new Error('Not running in Tauri');
}

function apiUpdateStatus(text) {}

function apiUpdateProgress(elementId, progress, message) {}

function showMessage(title, message, msgType) {}

function showAbout() {}

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
    getPendingTopics: getPendingTopics,
    resolveTopic: resolveTopic,
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
    browseFolder: browseFolder,
    startWebDownload: startWebDownload,
    startFileConversion: startFileConversion,
    extractTopics: extractTopics,
    startNoteIntegration: startNoteIntegration,
    refreshLog: refreshLog,
    onFileSelected: onFileSelected,
    getFilePreview: getFilePreview,
    canPreviewFile: canPreviewFile,
    saveFileContent: saveFileContent,
    syncWikiWithFiles: syncWikiWithFiles,

    moveWindow: moveWindow,
    minimizeWindow: minimizeWindow,
    maximizeWindow: maximizeWindow,
    closeWindow: closeWindow,
    openFileInNewWindow: openFileInNewWindow,
    updateStatus: apiUpdateStatus,
    updateProgress: apiUpdateProgress,
    showMessage: showMessage,

    open_workspace: openWorkspace,
    get_workspace_status: getWorkspaceStatus,
    get_workspace_tree: getWorkspaceTree,
    get_all_tags: getAllTags,
    get_topic_tree: getTopicTree,
    auto_tag_files: autoTagFiles,
    save_tags_md: saveTagsMd,
    ensure_tags_md: ensureTagsMd,
    auto_assign_topic: autoAssignTopic,
    batch_auto_assign_topics: batchAutoAssignTopics,
    create_topic: createTopic,
    create_tag: createTag,
    get_pending_topics: getPendingTopics,
    resolve_topic: resolveTopic,
    rename_topic: renameTopic,
    delete_topic: deleteTopic,
    rename_tag: renameTag,
    delete_tag: deleteTag,
    move_file_to_topic: moveFileToTopic,
    move_file: moveFile,
    add_tag_to_file: addTagToFile,
    get_api_config: getApiConfig,
    save_api_config: saveApiConfig,
    get_ui_config: getUiConfig,
    save_ui_config: saveUiConfig,
    get_theme_preference: getThemePreference,
    save_theme_preference: saveThemePreference,
    add_files: addFiles,
    browse_folder: browseFolder,
    start_web_download: startWebDownload,
    start_file_conversion: startFileConversion,
    extract_topics: extractTopics,
    start_note_integration: startNoteIntegration,
    refresh_log: refreshLog,
    on_file_selected: onFileSelected,
    get_file_preview: getFilePreview,
    can_preview_file: canPreviewFile,
    save_file_content: saveFileContent,
    read_file_raw: readFileRaw,
    read_note_file: getFilePreview,
    save_note_file: saveFileContent,

    move_window: moveWindow,
    minimize_window: minimizeWindow,
    maximize_window: maximizeWindow,
    close_window: closeWindow,
    open_file_in_new_window: openFileInNewWindow,
    update_status: apiUpdateStatus,
    update_progress: apiUpdateProgress,
    show_message: showMessage,

    discover_links: discoverLinks,
    get_backlinks: getBacklinks,
    get_relation_graph: getRelationGraph,
    confirm_link: confirmLink,
    reject_link: rejectLink,
    confirm_all_links: confirmAllLinks,
    sync_wiki_with_files: syncWikiWithFiles
};
