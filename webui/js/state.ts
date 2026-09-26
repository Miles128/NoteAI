/**
 * state.ts —— 状态双轨门面（从 state.js 渐进迁移到 TS）。
 * - window.state：配置持久化门面（apiConfig / uiConfig / themePreference / workspacePath），
 *   读写均伴随后端持久化。
 * - window.AppState：UI 运行时状态（普通对象），可任意增删键；
 *   仅用于会话内 UI 状态，不做持久化。
 */
(function() {
    'use strict';

    var _state: PersistedState = {
        apiConfig: null,
        uiConfig: null,
        themePreference: null,
        workspacePath: null
    };

    var _ui: AppUiState = {
        selectedFilePath: null,
        selectedFileName: null,
        activeTreeItem: null,
        treeExpandedState: {},
        currentSidebarView: 'tree',
        linkFilter: 'all',
        graphFilter: 'all',
        graphMode: 'notes',
        lastFileTreeData: null,
        lastTopicData: null
    };

    function getState(): PersistedState {
        var snapshot: PersistedState = {
            apiConfig: _state.apiConfig,
            uiConfig: _state.uiConfig,
            themePreference: _state.themePreference,
            workspacePath: _state.workspacePath
        };
        return JSON.parse(JSON.stringify(snapshot));
    }

    function getUi(key?: string): any {
        if (key === undefined) return Object.assign({}, _ui);
        return _ui[key];
    }

    function setUi(key: string, value: any): void {
        _ui[key] = value;
    }

    var _uiConfigPromise: Promise<UiConfig | null> | null = null;
    var _themePreferencePromise: Promise<string | null> | null = null;

    async function loadApiConfig(): Promise<ApiConfig | null> {
        try {
            _state.apiConfig = await window.api.getApiConfig();
            return _state.apiConfig;
        } catch (e) {
            console.error('加载 API 配置失败:', e);
            return null;
        }
    }

    async function loadUiConfig(force?: boolean): Promise<UiConfig | null> {
        // in-flight 合并：启动期多路消费（i18n/语义工作台/cli-agent/settings）
        // 共享同一次 RPC，避免 getUiConfig 被重复拉取
        if (!force && _state.uiConfig) return _state.uiConfig;
        if (!force && _uiConfigPromise) return _uiConfigPromise;
        _uiConfigPromise = (async function() {
            try {
                _state.uiConfig = await window.api.getUiConfig();
                return _state.uiConfig;
            } catch (e) {
                console.error('加载 UI 配置失败:', e);
                return null;
            } finally {
                _uiConfigPromise = null;
            }
        })();
        return _uiConfigPromise;
    }

    async function loadThemePreference(force?: boolean): Promise<string | null> {
        if (!force && _state.themePreference) return _state.themePreference;
        if (!force && _themePreferencePromise) return _themePreferencePromise;
        _themePreferencePromise = (async function() {
            try {
                _state.themePreference = await window.api.getThemePreference();
                return _state.themePreference;
            } catch (e) {
                console.error('加载主题偏好失败:', e);
                return null;
            } finally {
                _themePreferencePromise = null;
            }
        })();
        return _themePreferencePromise;
    }

    async function loadAllConfig(): Promise<PersistedState> {
        var results = await Promise.allSettled([
            loadApiConfig(),
            loadUiConfig(),
            loadThemePreference()
        ]);
        return {
            apiConfig: results[0].status === 'fulfilled' ? results[0].value : null,
            uiConfig: results[1].status === 'fulfilled' ? results[1].value : null,
            themePreference: results[2].status === 'fulfilled' ? results[2].value : null,
            workspacePath: _state.workspacePath
        };
    }

    async function saveApiConfig(config: Partial<ApiConfig>): Promise<any> {
        try {
            var result = await window.api.saveApiConfig(config);
            _state.apiConfig = Object.assign({}, _state.apiConfig, config);
            return result;
        } catch (e) {
            console.error('保存 API 配置失败:', e);
            throw e;
        }
    }

    async function saveUiConfig(config: Partial<UiConfig>): Promise<any> {
        try {
            var result = await window.api.saveUiConfig(config);
            _state.uiConfig = Object.assign({}, _state.uiConfig, config);
            return result;
        } catch (e) {
            console.error('保存 UI 配置失败:', e);
            throw e;
        }
    }

    async function saveThemePreference(theme: string): Promise<void> {
        try {
            await window.api.saveThemePreference(theme);
            _state.themePreference = theme;
            try {
                window.Storage.setRaw(window.Storage.KEYS.THEME, theme, { silent: true });
            } catch (_e) { /* noop */ }
        } catch (e) {
            console.error('保存主题偏好失败:', e);
            throw e;
        }
    }

    function setWorkspacePath(path: string): void {
        _state.workspacePath = path;
    }

    window.state = {
        get: getState,
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

    window.AppState = _ui;
})();