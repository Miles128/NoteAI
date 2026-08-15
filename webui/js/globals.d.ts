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
        invoke(method: string, params?: Record<string, any>): Promise<any>;
        getApiConfig(): Promise<ApiConfig>;
        getUiConfig(): Promise<UiConfig>;
        getThemePreference(): Promise<string>;
        saveApiConfig(config: Partial<ApiConfig>): Promise<any>;
        saveUiConfig(config: Partial<UiConfig>): Promise<any>;
        saveThemePreference(theme: string): Promise<any>;

        // 工作区 / 主题 / 标签
        getWorkspaceTree(): Promise<any>;
        getTopicTree(): Promise<any>;
        topicMeta(topic: string): Promise<any>;
        getSurveyOverview(): Promise<any>;
        toggleSurvey(topic: string): Promise<any>;
        getAllTags(): Promise<any>;
        autoTagFiles(dryRun?: boolean): Promise<any>;
        ensureTagsMd(): Promise<any>;
        batchAutoAssignTopics(): Promise<any>;
        createTopic(name: string, parent?: string): Promise<any>;
        createNoteFromDraft(title: string, topic?: string, content?: string): Promise<any>;
        createTag(name: string): Promise<any>;
        getAllPending(): Promise<any>;
        retryCascadeTopic(topic: string): Promise<any>;
        retryAllCascadeFailures(): Promise<any>;
        dismissCascadeFailure(topic: string): Promise<any>;
        retryConvertFile(file: string): Promise<any>;
        dismissConvertFailure(file: string): Promise<any>;
        getDashboardStatus(): Promise<any>;
        getActivityLog(limit?: number): Promise<any>;
        resolveTopic(filePath: string, topic: string): Promise<any>;
        keepNoteInTopic(filePath: string, currentTopic: string, suggestedTopic: string): Promise<any>;
        applyTopicPlacementThreshold(): Promise<any>;
        mergeDuplicateTopics(): Promise<any>;
        renameTopic(oldTopic: string, newTopic: string): Promise<any>;
        deleteTopic(topicName: string): Promise<any>;
        renameTag(oldTag: string, newTag: string): Promise<any>;
        deleteTag(tagName: string): Promise<any>;
        moveFileToTopic(filePath: string, newTopic: string): Promise<any>;
        moveFile(filePath: string, targetFolder: string): Promise<any>;
        addTagToFile(filePath: string, tag: string): Promise<any>;

        // 配置
        testApiConfig(cfg?: Partial<ApiConfig>): Promise<any>;
        getOnboardingStatus(): Promise<any>;
        markOnboardingDone(): Promise<any>;
        getComponentsStatus(): Promise<any>;
        installComponent(p: any): Promise<any>;
        uninstallComponent(p: any): Promise<any>;

        // 下载 / 转换 / 整合
        startWebDownload(urls: string[], aiAssist: boolean, includeImages: boolean): Promise<any>;
        startFileConversion(aiAssist: boolean): Promise<any>;
        autoConvertPending(): Promise<any>;
        extractTopics(topicCount: number): Promise<any>;
        startNoteIntegration(autoTopic: boolean, topics: string[]): Promise<any>;
        refreshLog(): Promise<any>;
        onFileSelected(path: string): Promise<any>;
        saveFileContent(path: string, content: string): Promise<any>;
        readFileRaw(path: string): Promise<any>;
        importFilesDirect(files: string[]): Promise<any>;
        importRssFeed(url: string, maxItems: number, fetchArticles: boolean): Promise<any>;
        listRssSubscriptions(): Promise<any>;
        saveRssSubscription(url: string, name?: string): Promise<any>;
        removeRssSubscription(url: string): Promise<any>;
        fetchAllRss(): Promise<any>;
        discoverRssSources(): Promise<any>;
        importTranscript(title: string, content: string, source: string): Promise<any>;
        listWatchedFolders(): Promise<any>;
        addWatchedFolder(path: string, recursive?: boolean): Promise<any>;
        removeWatchedFolder(path: string): Promise<any>;
        scanWatchedFolder(path: string, recursive?: boolean): Promise<any>;

        // 知识图谱 / 链接 / 语义
        getBacklinks(filePath: string): Promise<any>;
        getLinkStats(): Promise<any>;
        getGraphData(filter?: string): Promise<any>;
        getSemanticGraphData(options?: any): Promise<any>;
        confirmLink(fromPath: string, toPath: string): Promise<any>;
        rejectLink(fromPath: string, toPath: string): Promise<any>;
        getSemanticWorkbench(options?: any): Promise<any>;
        getSemanticDetail(kind: string, id: string): Promise<any>;
        getNoteSemanticContext(path: string): Promise<any>;
        getSemanticObjectWikiPage(kind: string, id: string): Promise<any>;
        publishSemanticObjectWikiPage(kind: string, id: string): Promise<any>;
        getSemanticCompileStatus(): Promise<any>;
        getSemanticChanges(options?: any): Promise<any>;
        getTopicBrief(options?: any): Promise<any>;
        generateWeeklyBrief(options?: any): Promise<any>;
        getIndexHealth(): Promise<any>;
        backupWorkspace(options?: any): Promise<any>;
        exportNotes(options?: any): Promise<any>;
        restoreWorkspaceBackup(options?: any): Promise<any>;
        startSemanticFullCompile(): Promise<any>;
        reviewSemanticConflict(id: string, status?: string): Promise<any>;
        scanSemanticConflicts(): Promise<any>;
        reviewSemanticEntityQuality(id: string, status?: string): Promise<any>;
        enqueueSemanticEntityQuality(id: string): Promise<any>;
        enqueueCrossKindSemanticMerges(): Promise<any>;
        resolveCrossKindMerges(dryRun?: boolean): Promise<any>;
        getSemanticEntityMergePreview(sourceId: string, targetId: string): Promise<any>;
        mergeSemanticEntities(sourceId: string, targetId: string): Promise<any>;
        updateSemanticClaim(id: string, statement: string, scope?: string, claimType?: string): Promise<any>;
        verifySemanticClaim(id: string, agent: string, method?: string): Promise<any>;
        setSemanticClaimStatus(id: string, status: string): Promise<any>;
        setSemanticEvidenceStatus(id: string, status: string): Promise<any>;
        getSemanticTopicWikiPage(topic: string): Promise<any>;
        publishSemanticTopicWikiPage(topic: string): Promise<any>;
        addSemanticEntityAlias(id: string, alias: string): Promise<any>;
        confirmAllLinks(): Promise<any>;
        syncWikiWithFiles(): Promise<any>;

        // LLM 改写 / AI 主题
        llmRewriteStream(filePath: string): Promise<any>;
        llmRewriteApply(filePath: string, rewrittenText: string): Promise<any>;
        aiTopicAnalyze(): Promise<any>;
        aiTopicSurvey(topic: string): Promise<any>;
        applyTopicSuggestion(suggestion: any): Promise<any>;

        // RAG
        ragChat(question: string, topics?: any, tags?: any, currentFile?: string, options?: any): Promise<any>;
        ragRebuildIndex(): Promise<any>;
        ragIndexStatus(): Promise<any>;
        runKbLint(): Promise<any>;
        getDuplicateReview(filePath: string, relatedFile?: string): Promise<any>;
        mergeDuplicateNotes(filePath: string, relatedFile: string, title?: string): Promise<any>;
        mergeNoteGroup(filePaths: string[], title?: string, deleteAuthorized?: boolean): Promise<any>;
        scanMergeCandidates(preset?: string, overrides?: any): Promise<any>;
        suggestTopicMergeNames(topics: string[]): Promise<any>;
        previewTopicMerge(topics: string[], newTopic?: string): Promise<any>;
        mergeSimilarTopics(topics: string[], newTopic?: string): Promise<any>;

        // CLI Agent 桥接
        listCliAgents(): Promise<any>;
        runCliAgent(agentId: string, prompt: string, workspacePath?: string, options?: any): Promise<any>;
        stopCliAgent(): Promise<any>;
        clearCliAgentSession(agentId?: string, workspacePath?: string): Promise<any>;
        generateVaultAgentsMd(): Promise<any>;

        // 规则 / Ingest / 任务
        getProjectRules(): Promise<any>;
        saveProjectRules(rules: any): Promise<any>;
        getWorkspaceRules(): Promise<any>;
        saveWorkspaceRules(opts?: any): Promise<any>;
        needsWorkspaceRulesSetup(): Promise<any>;
        startIngest(options?: any): Promise<any>;
        cancelIngest(): Promise<any>;
        retryIngest(options?: any): Promise<any>;
        getIngestStatus(): Promise<any>;
        checkIngestUpdates(options?: any): Promise<any>;
        ensureIngest(options?: any): Promise<any>;
        getJobs(options?: any): Promise<any>;

        // 搜索 / 文件操作
        searchFiles(query: string): Promise<any>;
        deleteFile(path: string): Promise<any>;
        revealInFinder(path: string): Promise<any>;

        // 特殊 API（对话框 / 多步逻辑 / 分页预览）
        openWorkspace(): Promise<any>;
        createSampleWorkspace(): Promise<any>;
        getWorkspaceStatus(): Promise<any>;
        addFiles(): Promise<string[]>;
        importFilesToWorkspace(): Promise<any>;
        browseFolder(): Promise<string>;
        openArchiveDialog(): Promise<any>;
        getFilePreview(path: string): Promise<any>;

        // 窗口控制
        moveWindow(dx?: number, dy?: number): void;
        minimizeWindow(): void;
        maximizeWindow(): void;
        closeWindow(): void;
        openFileInNewWindow(path: string, name?: string): Promise<any>;
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
        clearAppStorage(opts?: Record<string, any>): boolean;
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
        getState?(): PersistedState;
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
        __TAURI__: any;
        __TAURI_INTERNALS__: any;
        checkIsTauri: () => boolean | null;
        getTauriInvoke: () => any;
        getTauriEventAPI: () => any;
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
        AssistantModule: {
            init(): void;
            handleEvent(evt: any): void;
            rebuildIndex(): void;
            toggle(): void;
            ensureOpen(): void;
            ask(question: any): void;
            askSelection(selection: any, options?: any): void;
        } | undefined;
        closeSettingsPanel(): void;
        saveApiConfig(config?: Partial<ApiConfig>): void;
        EditorModule: {
            updateEditorTheme?(): void;
            renderMarkdownPreview?(content: string): string;
            destroyCodeMirrorEditor?(): void;
            isActive?: boolean;
            exitEditMode?(): void;
        } | undefined;
        Graph3Tier: { pauseResize?(): void; resumeResize?(): void; load?(data?: any): void; stopSimulation?(): void; zoomIn?(): void; zoomOut?(): void; zoomReset?(): void } | undefined;
        Graph: { refresh?(): void; applyLayout?(): void; setSelected?(): void } | undefined;
        HomeDashboardModule: { refresh?(): void } | undefined;
        InspectorModule: { onFileSelected?(path: string): void } | undefined;
        NoteListModule: {
            showTopicNotes?(path: string, name?: string): void;
            showAllNotes?(): void;
            setActiveFile?(path: string): void;
            refresh?(): void;
            getCurrentTopic?(): any;
        } | undefined;
        SemanticGraphModule: {
            setModeActive?(active: boolean): void;
            refresh?(): void;
            zoomIn?(): void;
            zoomOut?(): void;
            zoomReset?(): void;
        } | undefined;
        StatusbarModule: {
            setRewriting?(active: boolean, message?: string): void;
            onFileSelected?(path: string): void;
            setMetadataToggleVisible?(visible: boolean): void;
            updateCursor?(line: number, col: number): void;
            updateFromContent?(path: string, content: string): void;
            updateSaveStatus?(status: string, message?: string): void;
        } | undefined;
        NoteDraftModule: {
            clearActiveDraft?(): void;
            refreshDraftChrome?(): void;
            setActiveDraft?(draft: any): void;
            updateDraft?(draft: any): void;
        } | undefined;
        OnboardingModule: {
            maybeStart(): Promise<void>;
            open(): void;
            skip(): void;
        } | undefined;
        WorkspaceModule: {
            checkWorkspaceStatus(): Promise<any>;
        } | undefined;
        _rewritingFilePath: string | null;
        _pendingSectionLocate: string;
        loadPendingItems(): void;
        __componentInstallBound?: boolean;
        __ragIndexProgressBound?: boolean;
        SettingsComponents: {
            initRagSettings(): void;
            initIngestAutoSettings(): void;
            initAssistantSettings(): void;
            initTopicAutoThresholdSettings(): void;
            initMergePresetSettings(): void;
            initMergeAdvancedSettings(): void;
            applyMergeAdvancedToForm(overrides: any): void;
            initCliSettings(): void;
            applyRagSettingsToForm(uiConfig: any): void;
            applyAssistantSettingsToForm(uiConfig: any): void;
            applyCliSettingsToForm(uiConfig: any): void;
            refreshCliAgentsSettings(): Promise<any>;
            persistCliAgentId(agentId: string): void;
            syncCliAgentSelectors(agentId: any): void;
            saveAssistantUiConfig(partial: any): Promise<any>;
        } | undefined;
        DownloaderModule: {
            startWebDownload(): Promise<any>;
            updateWebImageStatus(): void;
            autoSaveConfig(): void;
            loadSavedConfig(): void;
            clearUrls(): void;
            openDownloadModal(): void;
            closeDownloadModal(): void;
            autoSaveModalConfig(): void;
            startDownloadFromModal(): Promise<any>;
            loadRssSubscriptions(): Promise<any>;
            loadWatchedFolders(): Promise<any>;
            getDownloadState(): any;
        } | undefined;
        closeDownloadModal(): void;
        startDownloadFromModal(): Promise<any>;
        SettingsModule: { saveFontSize?(size: string): void; persistCliAgentId?(id: string): void } | undefined;
        Icons: { get(name: string, size?: number): string } | undefined;
        _deactivatePendingBtn?: (() => void) | undefined;
        updateHomeStats?: (() => void) | undefined;
        _pdfKeyHandler: ((e: KeyboardEvent) => void) | null;
        switchSidebarView(view: string): void;
        showTagsView(): void;
        closePreview(): void;
        backToContent(): void;
        showPreview(options: { path: string; name?: string }): void;
        mdEditor: { isActive?: boolean } | undefined;
        TiptapEditorModule: {
            hideEditorUI?(): Promise<any> | void;
            openMarkdownInEditor?(content: string, path: string, draftMeta?: any): Promise<boolean>;
            preloadModules?(): Promise<any>;
            flushSave?(): Promise<any>;
        } | undefined;
        TiptapModules: any;
        TiptapEditor: {
            whenModulesReady?(timeoutMs?: number): Promise<boolean>;
            isActive?: boolean;
            instance?: {
                commands: { setContent(html: string, emitUpdate?: boolean): void };
                setEditable(editable: boolean): void;
            };
        } | undefined;
        SemanticWorkbenchModule: {
            init(): void;
            toggle(): void;
            show(category?: string): void;
            hide(): void;
            deactivate(): void;
            load(): void;
            openObject(kind: 'entity' | 'concept', id: string): void;
            isVisible(): boolean;
            applyVisibilityConfig(): void;
            isEnabled(): boolean;
            enabledCategories(): string[];
        } | undefined;
        toggleSemanticWorkbench(): void;
        TreeModule: {
            loadTreeState(): void;
            saveTreeState(): void;
            toggleTreeFolder(element: HTMLElement): void;
            renderFileTree(treeData: any, container: HTMLElement): void;
            loadFileTree(force?: boolean): Promise<void>;
            selectFile(path: string, fileName?: string): void;
            setSelectedFile(path: string, name?: string): void;
            isTreeFileCountEnabled(): boolean;
            setTreeFileCountEnabled(enabled: boolean): void;
            refreshTreeDisplay(): void;
            initTreeFileCountSetting(): void;
            hasTopicPending(): boolean;
            updateWebAIStatus?: () => void;
            updateConvAIStatus?: () => void;
        } | undefined;
        graphZoomIn(): void;
        graphZoomOut(): void;
        graphZoomReset(): void;
        loadRelationGraphData(): void;
        onAddTopicFromFileTree(): void;
        onConfirmLink(f: string, t: string): void;
        onRejectLink(f: string, t: string): void;
        refreshPendingBtnState(): void;
        semanticGraphRefresh(): void;
        showTreeContextMenu(e: MouseEvent, itemEl: HTMLElement): void;
        togglePendingLinksPanel(force?: boolean): void;
        switchGraphMode(mode: string): void;
        ToastModule: {
            error(message: string): void;
            success(message: string): void;
            show(message: string, type?: string): void;
        } | undefined;
        CliToolSummary: {
            clip(text: string, max?: number): string;
            normalizeToolName(name: string): string;
            describeCall(toolName: string, input: any): string;
            describeResult(toolName: string, input: any, result: any, success?: boolean): string;
            describeRunning(toolName: string, input: any): string;
        } | undefined;
        CliAgentModule: {
            init(): void;
            loadAgents(): Promise<any>;
            renderAgentSelector(): void;
            sendMessage(prompt: string, options?: any): Promise<any>;
            stopMessage(): void;
            startNewSession(): Promise<any>;
            handleEvent(evt: any): void;
            applySavedAgentId?(agentId: string): void;
            getSelectedAgent(): any;
            isRunning(): boolean;
            isCliAgentMode(): boolean;
        } | undefined;
        PreviewModule: PreviewModule;
        marked: any;
        setSidebarStatus(status: string, message: string, spinner?: boolean): void;
        updateSidebarStats(): void;
        updateStatus(message: string): void;
        updateProgress(elementId: string, progress: number, message: string): void;
        _customConfirm(message: string): Promise<boolean>;
        hideTreeContextMenu(): void;
        revealInFinder(path: string): void;
        _surveyOverviewMap?: Record<string, any>;
        _topicStaleMap?: Record<string, boolean>;
        _surveyStreamText: string;
        _surveyBuffer: string;
        _surveyDisplayText: string;
        _surveyFlushTimer: number | null;
        _surveyStreamUnlisten: (() => void) | null;
        loadTopicTree(silent?: boolean, forceRefresh?: boolean): Promise<void>;
        loadTopicView(): Promise<void>;
        loadTopicPendingPanel(pending: any[], topicNames?: string[]): void;
        onBatchAutoAssignTopics(): Promise<void>;
        onAITopicAnalyze(): Promise<void>;
        onAITopicSurvey(prefillTopic?: string): Promise<void>;
        topicRowClick(rowEl: HTMLElement): void;
        previewTopicSurvey(topic: string): void;
        previewSemanticWikiPage(topic: string): void;
        toggleTopicSurvey(topic: string): Promise<void>;
        updateTopicSurvey(topic: string): void;
        onShowTopicInput(): void;
        onHideTopicInput(): void;
        onTopicInputChange(): void;
        onConfirmTopic(): Promise<void>;
        closeAISuggestionPanel(): void;
        onCandidateClick(btnEl: HTMLElement): void;
        onInputChange(inputEl: HTMLInputElement): void;
        onTopicSelectChange(selectEl: HTMLSelectElement): void;
        onInputEnter(inputEl: HTMLInputElement): void;
        onConfirmBtnClick(btnEl: HTMLButtonElement): void;
        hasTopicPending(): boolean;
    }

    interface PreviewModule {
        readonly currentPreviewData: any;
        readonly isPreviewActive: boolean;
        showContentView(): void;
        showPreviewView(): void;
        loadFilePreview(path: string, fileName: string): Promise<void>;
        renderPreviewContent(previewData: any): void;
        showPreviewError(title: string, message: string): void;
        closePreview(): void;
        backToContent(): void;
        updateTitlebarFileName(fileName: string, isMarkdown: boolean): void;
        showEditButton(show: boolean): void;
    }

    declare var pdfjsLib: any;
    declare var hljs: any;
    declare var DOMPurify: any;
}