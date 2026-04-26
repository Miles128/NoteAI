(function() {
    'use strict';

    const DEFAULT_TIMEOUT = 30000;
    const TREE_TIMEOUT = 5000;

    let _apiPort = null;

    function getApiPort() {
        if (_apiPort) return _apiPort;
        const params = new URLSearchParams(window.location.search);
        _apiPort = params.get('port');
        if (!_apiPort) {
            _apiPort = window.location.port;
        }
        return _apiPort;
    }

    async function invokeApi(methodName, args = [], timeout = DEFAULT_TIMEOUT) {
        const port = getApiPort();
        if (!port) {
            return Promise.reject(new Error('无法确定 API 端口'));
        }

        const url = `http://localhost:${port}/api/${methodName}`;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(args || []),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`API 请求失败: ${response.status}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('请求超时');
            }
            console.error('[NoteAI] API 调用失败:', methodName, error);
            throw error;
        }
    }

    async function openWorkspace() {
        return invokeApi('open_workspace', []);
    }

    async function getWorkspaceStatus() {
        return invokeApi('get_workspace_status', []);
    }

    async function getWorkspaceTree() {
        return invokeApi('get_workspace_tree', [], TREE_TIMEOUT);
    }

    async function getApiConfig() {
        return invokeApi('get_api_config', []);
    }

    async function saveApiConfig(config) {
        return invokeApi('save_api_config', [config]);
    }

    async function getUiConfig() {
        return invokeApi('get_ui_config', []);
    }

    async function saveUiConfig(config) {
        return invokeApi('save_ui_config', [config]);
    }

    async function getThemePreference() {
        return invokeApi('get_theme_preference', []);
    }

    async function saveThemePreference(theme) {
        return invokeApi('save_theme_preference', [theme]);
    }

    async function addFiles() {
        return invokeApi('add_files', []);
    }

    async function browseFolder() {
        return invokeApi('browse_folder', []);
    }

    async function startWebDownload(urls, aiAssist, includeImages) {
        return invokeApi('start_web_download', [urls, aiAssist, includeImages]);
    }

    async function startFileConversion(aiAssist) {
        return invokeApi('start_file_conversion', [aiAssist]);
    }

    async function extractTopics(topicCount) {
        return invokeApi('extract_topics', [topicCount]);
    }

    async function startNoteIntegration(autoTopic, topics) {
        return invokeApi('start_note_integration', [autoTopic, topics]);
    }

    async function refreshLog() {
        return invokeApi('refresh_log', []);
    }

    async function onFileSelected(path) {
        return invokeApi('on_file_selected', [path]);
    }

    async function getFilePreview(path) {
        return invokeApi('get_file_preview', [path]);
    }

    async function canPreviewFile(path) {
        return invokeApi('can_preview_file', [path]);
    }

    async function saveFileContent(path, content) {
        return invokeApi('save_file_content', [path, content]);
    }

    function moveWindow(dx, dy) {
        invokeApi('move_window', [dx, dy]);
    }

    function minimizeWindow() {
        invokeApi('minimize_window', []);
    }

    function maximizeWindow() {
        invokeApi('maximize_window', []);
    }

    function closeWindow() {
        invokeApi('close_window', []);
    }

    function updateStatus(text) {
        invokeApi('update_status', [text]);
    }

    function updateProgress(elementId, progress, message) {
        invokeApi('update_progress', [elementId, progress, message]);
    }

    function showMessage(title, message, msgType) {
        invokeApi('show_message', [title, message, msgType]);
    }

    window.api = {
        invoke: invokeApi,
        getApiPort,

        openWorkspace,
        getWorkspaceStatus,
        getWorkspaceTree,
        getApiConfig,
        saveApiConfig,
        getUiConfig,
        saveUiConfig,
        getThemePreference,
        saveThemePreference,
        addFiles,
        browseFolder,
        startWebDownload,
        startFileConversion,
        extractTopics,
        startNoteIntegration,
        refreshLog,
        onFileSelected,
        getFilePreview,
        canPreviewFile,
        saveFileContent,

        moveWindow,
        minimizeWindow,
        maximizeWindow,
        closeWindow,
        updateStatus,
        updateProgress,
        showMessage,

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
        update_status: updateStatus,
        update_progress: updateProgress,
        show_message: showMessage
    };

    window.openWorkspace = openWorkspace;
    window.minimizeWindow = minimizeWindow;
    window.maximizeWindow = maximizeWindow;
    window.closeWindow = closeWindow;
    window.moveWindow = moveWindow;
    window.updateStatus = updateStatus;
    window.updateProgress = updateProgress;
    window.showMessage = showMessage;

    window.pywebview = {
        api: {
            move_window: moveWindow,
            minimize_window: minimizeWindow,
            maximize_window: maximizeWindow,
            close_window: closeWindow,
            get_workspace_status: getWorkspaceStatus,
            check_workspace_path_valid: (...args) => invokeApi('check_workspace_path_valid', args),
            clear_saved_workspace: () => invokeApi('clear_saved_workspace', []),
            update_window_title: () => invokeApi('update_window_title', []),
            open_workspace: openWorkspace,
            get_api_config: getApiConfig,
            browse_folder: browseFolder,
            add_files: addFiles,
            update_status: updateStatus,
            update_progress: updateProgress,
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
            show_about: () => invokeApi('show_about', []),
            save_file_content: saveFileContent
        }
    };
})();
