async function loadModules() {
    await Promise.all([
        import('./utils.ts'),
        import('./api.ts'),
        import('./state.ts'),
    ]);

    await import('./i18n.ts');
    await import('./theme.ts');
    // 启动 RPC 并行化：i18n（含 uiConfig）与主题（含 themePreference）互不依赖，
    // 与 state 门面预热共享同一 in-flight promise（各只发一次 RPC）
    await Promise.all([
        window.I18nModule.initI18n(),
        (async function() {
            window.ThemeModule.initSystemThemeListener();
            await window.ThemeModule.applyThemeBootstrap();
        })(),
        window.state.loadUiConfig().catch(function() {}),
        window.state.loadThemePreference().catch(function() {}),
    ]);

    await import('./assistant.ts');

    await import('./icons.js');
    const { IconsModule } = window;
    window.IconsModule = IconsModule;

    // 顺序契约：graph-layout-params.js 顶层读取 window.Storage.KEYS，依赖 index.html 末尾经典脚本
    // storage.js 先行——经典脚本在 HTML 解析期执行，必早于本模块脚本，顺序恒成立。
    // G3.js 顶层读取 window.GraphLayoutParams，须在其之前加载。
    await import('./graph-layout-params.js');
    await import('./G3.js');

    await import('./toast.js');

    // settings 子模块须先于薄主入口 settings.js 加载（主入口组装 window.SettingsModule）
    await import('./settings-general.js');
    await import('./settings-components.js');
    await import('./settings-semantic.js');
    await import('./settings.js');
    const {
        SettingsModule, saveApiConfig, refreshLog, closeSettingsPanel,
        closeLogPanel, resetApiConfig,
    } = window;
    window.SettingsModule = SettingsModule;
    window.saveApiConfig = saveApiConfig;
    window.refreshLog = refreshLog;
    window.closeSettingsPanel = closeSettingsPanel;
    window.closeLogPanel = closeLogPanel;
    window.resetApiConfig = resetApiConfig;

    await import('./workspace.js');
    const {
        WorkspaceModule, openWorkspace,
        showProjectRulesModal, closeProjectRulesModal, saveProjectRulesModal,
    } = window;
    window.WorkspaceModule = WorkspaceModule;
    window.openWorkspace = openWorkspace;
    window.showProjectRulesModal = showProjectRulesModal;
    window.closeProjectRulesModal = closeProjectRulesModal;
    window.saveProjectRulesModal = saveProjectRulesModal;

    await import('./tree.ts');
    const { TreeModule } = window;
    window.TreeModule = TreeModule;

    await import('./note-list.js');
    window.NoteListModule = window.NoteListModule || {};
    if (window.NoteListModule.init) window.NoteListModule.init();

    await import('./inspector.js');
    window.InspectorModule = window.InspectorModule || {};
    if (window.InspectorModule.init) window.InspectorModule.init();

    await import('./cli-tool-summary.js');
    await import('./cli-agent.ts');
    window.CliAgentModule = window.CliAgentModule || {};
    if (window.CliAgentModule.init) window.CliAgentModule.init();

    await import('./statusbar.js');
    window.StatusbarModule = window.StatusbarModule || {};

    await import('./sidebar.js');
    window.switchSidebarView = window.switchSidebarView;
    window.updateSidebarStats = window.updateSidebarStats;
    window.setSidebarStatus = window.setSidebarStatus;
    window.showGraphHomeView = window.showGraphHomeView;
    window.updateHomeStats = window.updateHomeStats;
    // toggleSidebar 的真实实现在 sidebar.js；模块加载前由 index.html 内联脚本与
    // utils.js 的 _earlyGlobals 提供 noop 占位，此处不再重复兜底。

    await import('./tags.js');

    await import('./tiptap-editor.js');
    const { TiptapEditorModule, TiptapEditor } = window;
    window.TiptapEditorModule = TiptapEditorModule;
    window.TiptapEditor = TiptapEditor;

    await import('./preview.ts');
    const { PreviewModule, closePreview, closePreviewPanel, backToContent } = window;
    window.PreviewModule = PreviewModule;
    window.closePreview = closePreview;
    window.closePreviewPanel = closePreviewPanel;
    window.backToContent = backToContent;

    await import('./selection-tools.js');
    window.SelectionToolsModule = window.SelectionToolsModule || {};
    if (window.SelectionToolsModule.init) window.SelectionToolsModule.init();

    await import('./editor.js');

    await import('./rewrite.js');
    if (window.RewriteManager) {
        window.onLLMRewrite = window.RewriteManager.onLLMRewrite;
    }

    await import('./converter.js');
    const { ConverterModule } = window;
    window.ConverterModule = ConverterModule;

    await import('./downloader.ts');
    const { DownloaderModule } = window;
    window.DownloaderModule = DownloaderModule;

    await import('./integrator.js');
    const { IntegratorModule } = window;
    window.IntegratorModule = IntegratorModule;

    await import('./topic.ts');
    const {
        loadTopicTree, loadTopicView, loadTopicPendingPanel,
        onBatchAutoAssignTopics, onAITopicAnalyze, onAITopicSurvey,
        onShowTopicInput, onHideTopicInput, onConfirmTopic,
        closeAISuggestionPanel, onCandidateClick, onInputChange,
        onTopicSelectChange, onInputEnter, onConfirmBtnClick,
        hasTopicPending,
    } = window;
    window.loadTopicTree = loadTopicTree;
    window.loadTopicView = loadTopicView;
    window.loadTopicPendingPanel = loadTopicPendingPanel;
    window.onBatchAutoAssignTopics = onBatchAutoAssignTopics;
    window.onAITopicAnalyze = onAITopicAnalyze;
    window.onAITopicSurvey = onAITopicSurvey;
    window.onShowTopicInput = onShowTopicInput;
    window.onHideTopicInput = onHideTopicInput;
    window.onConfirmTopic = onConfirmTopic;
    window.closeAISuggestionPanel = closeAISuggestionPanel;
    window.onCandidateClick = onCandidateClick;
    window.onInputChange = onInputChange;
    window.onTopicSelectChange = onTopicSelectChange;
    window.onInputEnter = onInputEnter;
    window.onConfirmBtnClick = onConfirmBtnClick;
    window.hasTopicPending = hasTopicPending;

    await import('./search.js');
    window.SearchModule = window.SearchModule || {};

    await import('./pending.ts');
    const {
        togglePendingView, refreshPendingBtnState, loadPendingItems,
    } = window;
    window.togglePendingView = togglePendingView;
    window.refreshPendingBtnState = refreshPendingBtnState;
    window.loadPendingItems = loadPendingItems;

    await import('./semantic-workbench.ts');
    window.SemanticWorkbenchModule = window.SemanticWorkbenchModule || {};
    window.toggleSemanticWorkbench = window.SemanticWorkbenchModule.toggle;
    if (window.SemanticWorkbenchModule.init) window.SemanticWorkbenchModule.init();

    await import('./semantic-graph.js');
    window.SemanticGraphModule = window.SemanticGraphModule || {};

    await import('./tabs.js');
    const { TabsModule } = window;
    window.TabsModule = TabsModule;

    await import('./workspace-rules.js');
    if (window.OrganizeRulesModule && window.OrganizeRulesModule.init) {
        window.OrganizeRulesModule.init();
    }

    await import('./ingest.js');
    const { IngestModule } = window;
    window.IngestModule = IngestModule;
    if (IngestModule.initIngestUi) IngestModule.initIngestUi();

    await import('./job-center.js');
    window.JobCenterModule = window.JobCenterModule || {};
    if (window.JobCenterModule.refresh) {
        window.JobCenterModule.refresh({ include_finished: true, limit: 50 }).catch(function(err) {
            console.warn('[JobCenter] initial refresh failed:', err);
        });
    }

    await import('./home.js');
    window.HomeDashboardModule = window.HomeDashboardModule || {};
    if (window.HomeDashboardModule.init) window.HomeDashboardModule.init();

    await import('./note-draft.js');
    window.NoteDraftModule = window.NoteDraftModule || {};

    await import('./quick-create.js');
    if (window.QuickCreateModule && window.QuickCreateModule.init) {
        window.QuickCreateModule.init();
    }

    await import('./event-listeners.js');
    const { EventListeners } = window;
    window.EventListeners = EventListeners;

    await import('./app.js');
    const { App, importFiles } = window;
    window.App = App;
    window.importFiles = importFiles;

    await import('./onboarding.js');

    // 显式调用应用初始化，取代旧的“重放 DOMContentLoaded”做法：
    // app.js 已改为导出 init()；其余模块的初始化均已改为 import 时直接执行
    // （或由 main.mjs 显式调用 init），不再依赖事件重放。
    await App.init();

    // 首启引导 wizard：workspace 未设置且未完成引导时打开（检查在 App.init 末尾）
    if (window.OnboardingModule && window.OnboardingModule.maybeStart) {
        window.OnboardingModule.maybeStart().catch(function(err) {
            console.warn('[Onboarding] maybeStart failed:', err);
        });
    }
}

loadModules();
