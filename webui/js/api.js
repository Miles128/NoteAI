var _isTauri = typeof window !== 'undefined' && window.__TAURI_INTERNALS__;

async function pyCall(method, params) {
    if (_isTauri) {
        var invoke = window.__TAURI_INTERNALS__.invoke;
        return await invoke('py_call', {
            method: method,
            params: params || {}
        });
    }
    throw new Error('Not running in Tauri');
}

async function openWorkspace() {
    if (_isTauri) {
        var invoke = window.__TAURI_INTERNALS__.invoke;
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
        var invoke = window.__TAURI_INTERNALS__.invoke;
        await invoke('set_workspace_path', { path: result.workspace_path });
    }
    return result;
}

async function getWorkspaceTree() {
    return pyCall('get_workspace_tree');
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
        var invoke = window.__TAURI_INTERNALS__.invoke;
        var files = await invoke('open_file_dialog');
        return files || [];
    }
    return pyCall('add_files');
}

async function browseFolder() {
    if (_isTauri) {
        var invoke = window.__TAURI_INTERNALS__.invoke;
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
    if (_isTauri) {
        var invoke = window.__TAURI_INTERNALS__.invoke;
        await invoke('write_file', { path: path, content: content });
        return { success: true, message: '文件已保存' };
    }
    return pyCall('save_file_content', { path: path, content: content });
}

function moveWindow(dx, dy) {}

function minimizeWindow() {
    if (_isTauri) {
        var win = window.__TAURI_INTERNALS__.window.getCurrent();
        win.minimize();
    }
}

function maximizeWindow() {
    if (_isTauri) {
        var win = window.__TAURI_INTERNALS__.window.getCurrent();
        win.toggleMaximize();
    }
}

function closeWindow() {
    if (_isTauri) {
        var win = window.__TAURI_INTERNALS__.window.getCurrent();
        win.close();
    }
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
    getApiConfig: getApiConfig,
    saveApiConfig: saveApiConfig,
    getUiConfig: getUiConfig,
    saveUiConfig: saveUiConfig,
    getThemePreference: getThemePreference,
    saveThemePreference: saveThemePreference,
    addFiles: addFiles,
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

    moveWindow: moveWindow,
    minimizeWindow: minimizeWindow,
    maximizeWindow: maximizeWindow,
    closeWindow: closeWindow,
    updateStatus: apiUpdateStatus,
    updateProgress: apiUpdateProgress,
    showMessage: showMessage,

    open_workspace: openWorkspace,
    get_workspace_status: getWorkspaceStatus,
    get_workspace_tree: getWorkspaceTree,
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
    read_note_file: getFilePreview,
    save_note_file: saveFileContent,

    move_window: moveWindow,
    minimize_window: minimizeWindow,
    maximize_window: maximizeWindow,
    close_window: closeWindow,
    update_status: apiUpdateStatus,
    update_progress: apiUpdateProgress,
    show_message: showMessage
};

window.pywebview = {
    api: {
        move_window: moveWindow,
        minimize_window: minimizeWindow,
        maximize_window: maximizeWindow,
        close_window: closeWindow,
        get_workspace_status: getWorkspaceStatus,
        check_workspace_path_valid: function() { return pyCall('check_workspace_path_valid'); },
        clear_saved_workspace: function() { return pyCall('clear_saved_workspace'); },
        update_window_title: function() {},
        open_workspace: openWorkspace,
        get_api_config: getApiConfig,
        browse_folder: browseFolder,
        add_files: addFiles,
        update_status: apiUpdateStatus,
        update_progress: apiUpdateProgress,
        show_message: showMessage,
        start_web_download: startWebDownload,
        start_file_conversion: startFileConversion,
        extract_topics: extractTopics,
        start_note_integration: startNoteIntegration,
        save_api_config: saveApiConfig,
        get_ui_config: getUiConfig,
        save_ui_config: saveUiConfig,
        refresh_log: refreshLog,
        get_theme_preference: getThemePreference,
        save_theme_preference: saveThemePreference,
        get_workspace_tree: getWorkspaceTree,
        on_file_selected: onFileSelected,
        get_file_preview: getFilePreview,
        can_preview_file: canPreviewFile,
        show_about: showAbout,
        save_file_content: saveFileContent
    }
};
