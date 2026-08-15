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

    interface StorageKeys {
        GRAPH_LAYOUT: string;
        GRAPH_LAYOUT_MODE: string;
        THEME: string;
        ACCENT_COLOR: string;
        DOWNLOADER_CONFIG: string;
        CONVERTER_CONFIG: string;
        TREE_STATE: string;
        TREE_SHOW_FILE_COUNT: string;
        SIDEBAR_WIDTH: string;
        FONT_SIZE: string;
    }

    interface StorageModule {
        KEYS: StorageKeys;
        setItem(key: string, value: unknown, opts?: Record<string, any>): boolean;
        getItem(key: string, fallback?: unknown, opts?: Record<string, any>): unknown;
        setRaw(key: string, value: unknown, opts?: Record<string, any>): boolean;
        getRaw(key: string, fallback?: unknown, opts?: Record<string, any>): unknown;
        removeItem(key: string, opts?: Record<string, any>): boolean;
    }

    interface TypographyRow {
        family: string;
        style: string;
    }

    interface ThemeModule {
        toggleTheme(): void;
        setTheme(theme: string): void;
        applySystemTheme(): void;
        initSystemThemeListener(): void;
        applyTheme(theme: string): void;
        syncThemeRadioInputs(theme: string): void;
        applyAccentColor(accent: string): void;
        setAccentColor(accent: string): void;
        applyAccentBootstrap(): void;
        persistThemeLocal(theme: string): void;
        applyThemeBootstrap(): Promise<void>;
        setFontSize(size: string): void;
        restoreFontSize(): void;
        applyContentFonts(sidebarFont: string, previewFont: string): void;
        applyTypography(settings: Record<string, any>): Record<string, TypographyRow>;
        restoreTypography(): Record<string, TypographyRow>;
        normalizeTypography(input: any): Record<string, TypographyRow>;
        restoreSidebarWidth(): void;
        initResizer(): void;
        initPreviewResizer(): void;
        showAboutPanel(): void;
        hideAboutPanel(): void;
    }

    interface I18nModule {
        t(key: string, params?: Record<string, string | number>): string;
        loadLocale(locale: string): Promise<void>;
        setLocale(locale: string): Promise<void>;
        applyDomI18n(root?: ParentNode): void;
        initI18n(): Promise<any>;
        whenReady(fn: () => void): void;
        getLocale(): string;
        isReady(): boolean;
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
        t: (key: string, params?: Record<string, string | number>) => string;
        I18nModule: I18nModule;
        ThemeModule: ThemeModule;
        setTheme(theme: string): void;
        setAccentColor(accent: string): void;
        setFontSize(size: string): void;
        escapeHtml(text: unknown): string;
        escapeAttr(str: unknown): string;
        safeUrl(url: string): string;
        formatFileSize(bytes: number | null | undefined): string;
        formatModifiedTime(timestamp: number | null | undefined): string;
        Path_stem(p: string): string;
        b64ToUint8(b64: string): Uint8Array;
        b64DecodeUtf8(b64: string): string;
        loadLazyScript(src: string): Promise<boolean>;
        toggleSidebar(): void;
        toggleFileListSidebar(): void;
        toggleNoteList(): void;
        openWorkspace(): void;
        showSettings(): void;
        importFiles(): void;
        switchTab(index: number): void;
        closePreviewPanel(): void;
        togglePendingView(): void;
        toggleEditMode(): void;
        toggleGraphPanel(): void;
        toggleSearchModal(): void;
        toggleAIPanel(): void;
        closeSettingsPanel(): void;
        saveApiConfig(config?: Partial<ApiConfig>): void;
        EditorModule: { updateEditorTheme?(): void } | undefined;
        Graph3Tier: { pauseResize?(): void; resumeResize?(): void } | undefined;
        SettingsModule: { saveFontSize?(size: string): void } | undefined;
    }
}