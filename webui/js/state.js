(function() {
    'use strict';

    var _state = {
        apiConfig: null,
        uiConfig: null,
        themePreference: null,
        workspacePath: null,
        _subscribers: []
    };

    var _ui = {
        selectedFilePath: null,
        selectedFileName: null,
        activeTreeItem: null,
        treeExpandedState: {},
        currentSidebarView: 'tree',
        linkFilter: 'all',
        graphFilter: 'all',
        lastFileTreeData: null,
        lastTagsData: null,
        lastTopicData: null
    };

    function subscribe(callback) {
        if (typeof callback === 'function') {
            _state._subscribers.push(callback);
        }
        return function() {
            _state._subscribers = _state._subscribers.filter(function(s) { return s !== callback; });
        };
    }

    function notify() {
        _state._subscribers.forEach(function(fn) {
            try {
                fn(_state);
            } catch (e) {
                console.error('State subscriber error:', e);
            }
        });
    }

    function getState() {
        var snapshot = {
            apiConfig: _state.apiConfig,
            uiConfig: _state.uiConfig,
            themePreference: _state.themePreference,
            workspacePath: _state.workspacePath
        };
        return JSON.parse(JSON.stringify(snapshot));
    }

    function getUi(key) {
        if (key === undefined) return Object.assign({}, _ui);
        return _ui[key];
    }

    function setUi(key, value) {
        if (_ui.hasOwnProperty(key)) {
            _ui[key] = value;
            notify();
        }
    }

    async function loadApiConfig() {
        try {
            _state.apiConfig = await window.api.getApiConfig();
            notify();
            return _state.apiConfig;
        } catch (e) {
            console.error('加载 API 配置失败:', e);
            return null;
        }
    }

    async function loadUiConfig() {
        try {
            _state.uiConfig = await window.api.getUiConfig();
            notify();
            return _state.uiConfig;
        } catch (e) {
            console.error('加载 UI 配置失败:', e);
            return null;
        }
    }

    async function loadThemePreference() {
        try {
            _state.themePreference = await window.api.getThemePreference();
            notify();
            return _state.themePreference;
        } catch (e) {
            console.error('加载主题偏好失败:', e);
            return null;
        }
    }

    async function loadAllConfig() {
        var results = await Promise.allSettled([
            loadApiConfig(),
            loadUiConfig(),
            loadThemePreference()
        ]);
        return {
            apiConfig: results[0].status === 'fulfilled' ? results[0].value : null,
            uiConfig: results[1].status === 'fulfilled' ? results[1].value : null,
            themePreference: results[2].status === 'fulfilled' ? results[2].value : null
        };
    }

    async function saveApiConfig(config) {
        try {
            var result = await window.api.saveApiConfig(config);
            _state.apiConfig = Object.assign({}, _state.apiConfig, config);
            notify();
            return result;
        } catch (e) {
            console.error('保存 API 配置失败:', e);
            throw e;
        }
    }

    async function saveUiConfig(config) {
        try {
            var result = await window.api.saveUiConfig(config);
            _state.uiConfig = Object.assign({}, _state.uiConfig, config);
            notify();
            return result;
        } catch (e) {
            console.error('保存 UI 配置失败:', e);
            throw e;
        }
    }

    async function saveThemePreference(theme) {
        try {
            await window.api.saveThemePreference(theme);
            _state.themePreference = theme;
            try {
                localStorage.setItem('noteai_theme', theme);
            } catch (_e) { /* noop */ }
            notify();
        } catch (e) {
            console.error('保存主题偏好失败:', e);
            throw e;
        }
    }

    function setWorkspacePath(path) {
        _state.workspacePath = path;
        notify();
    }

    window.state = {
        get: getState,
        subscribe: subscribe,
        loadAllConfig: loadAllConfig,
        loadApiConfig: loadApiConfig,
        loadUiConfig: loadUiConfig,
        loadThemePreference: loadThemePreference,
        saveApiConfig: saveApiConfig,
        saveUiConfig: saveUiConfig,
        saveThemePreference: saveThemePreference,
        setWorkspacePath: setWorkspacePath,
        getUi: getUi,
        setUi: setUi
    };

    Object.defineProperty(window, 'apiConfig', {
        get: function() { return _state.apiConfig; },
        enumerable: true,
        configurable: true
    });

    Object.defineProperty(window, 'uiConfig', {
        get: function() { return _state.uiConfig; },
        enumerable: true,
        configurable: true
    });

    Object.defineProperty(window, 'themePreference', {
        get: function() { return _state.themePreference; },
        enumerable: true,
        configurable: true
    });

    window.AppState = new Proxy(_ui, {
        set: function(target, property, value) {
            target[property] = value;
            notify();
            return true;
        }
    });

    window.subscribeToState = subscribe;
    window.notifyStateChange = notify;
})();
