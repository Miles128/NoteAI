/**
 * webui 前端全局类型声明。
 * 渐进迁移：仅 .ts 文件参与 tsc 检查；.js 保持原有运行时契约（window.* 互调）。
 * 声明按已迁移模块的实际消费面收缩，随迁移推进补全。
 */

export {};

declare global {
    interface UiConfig {
        [key: string]: any;
    }

    interface ApiConfig {
        [key: string]: any;
    }

    interface WindowApi {
        getApiConfig(): Promise<ApiConfig>;
        getUiConfig(): Promise<UiConfig>;
        getThemePreference(): Promise<string>;
        saveApiConfig(config: Partial<ApiConfig>): Promise<any>;
        saveUiConfig(config: Partial<UiConfig>): Promise<any>;
        saveThemePreference(theme: string): Promise<any>;
    }

    interface StorageModule {
        KEYS: Record<string, string>;
        setRaw(key: string, value: unknown, opts?: Record<string, any>): void;
    }

    type StateSubscriber = (state: PersistedState) => void;

    interface PersistedState {
        apiConfig: ApiConfig | null;
        uiConfig: UiConfig | null;
        themePreference: string | null;
        workspacePath: string | null;
    }

    interface StateModule {
        get(): PersistedState;
        subscribe(cb: StateSubscriber): () => void;
        loadAllConfig(): Promise<PersistedState>;
        loadApiConfig(): Promise<ApiConfig | null>;
        loadUiConfig(force?: boolean): Promise<UiConfig | null>;
        loadThemePreference(force?: boolean): Promise<string | null>;
        saveApiConfig(config: Partial<ApiConfig>): Promise<any>;
        saveUiConfig(config: Partial<UiConfig>): Promise<any>;
        saveThemePreference(theme: string): Promise<void>;
        setWorkspacePath(path: string): void;
        getUi(key?: string): any;
        setUi(key: string, value: any): void;
    }

    interface Window {
        api: WindowApi;
        Storage: StorageModule;
        state: StateModule;
        apiConfig: ApiConfig | null;
        uiConfig: UiConfig | null;
        themePreference: string | null;
        AppState: Record<string, any>;
        subscribeToState: (callback: StateSubscriber) => () => void;
        notifyStateChange: () => void;
    }
}