(function() {
    'use strict';

    const _state = {
        apiConfig: null,
        uiConfig: null,
        themePreference: null,
        workspacePath: null,
        _subscribers: []
    };

    function subscribe(callback) {
        if (typeof callback === 'function') {
            _state._subscribers.push(callback);
        }
        return () => {
            _state._subscribers = _state._subscribers.filter(s => s !== callback);
        };
    }

    function notify() {
        _state._subscribers.forEach(fn => {
            try {
                fn(_state);
            } catch (e) {
                console.error('State subscriber error:', e);
            }
        });
    }

    function getState() {
        return {
            apiConfig: _state.apiConfig ? { ..._state.apiConfig } : null,
            uiConfig: _state.uiConfig ? { ..._state.uiConfig } : null,
            themePreference: _state.themePreference,
            workspacePath: _state.workspacePath
        };
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
        const results = await Promise.allSettled([
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
            const result = await window.api.saveApiConfig(config);
            _state.apiConfig = { ..._state.apiConfig, ...config };
            notify();
            return result;
        } catch (e) {
            console.error('保存 API 配置失败:', e);
            throw e;
        }
    }

    async function saveUiConfig(config) {
        try {
            const result = await window.api.saveUiConfig(config);
            _state.uiConfig = { ..._state.uiConfig, ...config };
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
        subscribe,
        loadAllConfig,
        loadApiConfig,
        loadUiConfig,
        loadThemePreference,
        saveApiConfig,
        saveUiConfig,
        saveThemePreference,
        setWorkspacePath
    };

    Object.defineProperty(window, 'apiConfig', {
        get: () => _state.apiConfig,
        enumerable: true,
        configurable: true
    });

    Object.defineProperty(window, 'uiConfig', {
        get: () => _state.uiConfig,
        enumerable: true,
        configurable: true
    });

    Object.defineProperty(window, 'themePreference', {
        get: () => _state.themePreference,
        enumerable: true,
        configurable: true
    });

    window.subscribeToState = subscribe;
    window.notifyStateChange = notify;
})();
