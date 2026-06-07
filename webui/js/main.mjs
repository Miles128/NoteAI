async function loadModules() {
    await Promise.all([
        import('./utils.js'),
        import('./window.js'),
        import('./api.js'),
        import('./state.js'),
    ]);

    await import('./i18n.js');
    await window.I18nModule.initI18n();

    await import('./assistant.js');

    await import('./theme.js');
    const ThemeModule = window.ThemeModule;
    ThemeModule.initSystemThemeListener();
    await ThemeModule.applyThemeBootstrap();

    await import('./icons.js');
    const { IconsModule } = window;
    window.IconsModule = IconsModule;

    await import('./toast.js');
    const { ToastModule } = window;
    window.ToastModule = ToastModule;

    await import('./settings.js');
    const {
        SettingsModule, saveApiConfig, refreshLog, closeSettingsPanel,
        closeLogPanel, resetApiConfig, saveUserProfile,
    } = window;
    window.SettingsModule = SettingsModule;
    window.saveApiConfig = saveApiConfig;
    window.refreshLog = refreshLog;
    window.closeSettingsPanel = closeSettingsPanel;
    window.closeLogPanel = closeLogPanel;
    window.resetApiConfig = resetApiConfig;
    window.saveUserProfile = saveUserProfile;

    await import('./cloud-sync.js');
    const { CloudSyncModule } = window;
    window.CloudSyncModule = CloudSyncModule;
    CloudSyncModule.init();

    await import('./workspace.js');
    const {
        WorkspaceModule, updateStatus, updateProgress, openWorkspace,
        showProjectRulesModal, closeProjectRulesModal, saveProjectRulesModal,
    } = window;
    window.WorkspaceModule = WorkspaceModule;
    window.updateStatus = updateStatus;
    window.updateProgress = updateProgress;
    window.openWorkspace = openWorkspace;
    window.showProjectRulesModal = showProjectRulesModal;
    window.closeProjectRulesModal = closeProjectRulesModal;
    window.saveProjectRulesModal = saveProjectRulesModal;

    await import('./tree.js');
    const { TreeModule } = window;
    window.TreeModule = TreeModule;

    await import('./sidebar.js');
    window.switchSidebarView = window.switchSidebarView;
    window.updateSidebarStats = window.updateSidebarStats;
    window.setSidebarStatus = window.setSidebarStatus;
    window.showGraphHomeView = window.showGraphHomeView;
    window.updateHomeStats = window.updateHomeStats;
    if (typeof window.toggleSidebar !== 'function') {
        window.toggleSidebar = function _toggleSidebarMissing() {};
    }

    await import('./links.js');
    const { LinksModule } = window;
    window.LinksModule = LinksModule;

    await import('./tiptap-editor.js');
    const { TiptapEditorModule, TiptapEditor } = window;
    window.TiptapEditorModule = TiptapEditorModule;
    window.TiptapEditor = TiptapEditor;

    await import('./preview.js');
    const { PreviewModule, closePreview, closePreviewPanel, backToContent } = window;
    window.PreviewModule = PreviewModule;
    window.closePreview = closePreview;
    window.closePreviewPanel = closePreviewPanel;
    window.backToContent = backToContent;

    await import('./editor.js');

    await import('./converter.js');
    const { ConverterModule } = window;
    window.ConverterModule = ConverterModule;

    await import('./downloader.js');
    const { DownloaderModule } = window;
    window.DownloaderModule = DownloaderModule;

    await import('./integrator.js');
    const { IntegratorModule } = window;
    window.IntegratorModule = IntegratorModule;

    await import('./topic.js');
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

    await import('./tags.js');
    const { doAutoTag, onShowAddTagInput, loadTagsView } = window;
    window.doAutoTag = doAutoTag;
    window.onShowAddTagInput = onShowAddTagInput;
    window.loadTagsView = loadTagsView;

    await import('./search.js');
    window.SearchModule = window.SearchModule || {};

    await import('./pending.js');
    const {
        togglePendingView, refreshPendingBtnState, loadPendingItems,
    } = window;
    window.togglePendingView = togglePendingView;
    window.refreshPendingBtnState = refreshPendingBtnState;
    window.loadPendingItems = loadPendingItems;

    await import('./tabs.js');
    const { TabsModule } = window;
    window.TabsModule = TabsModule;

    await import('./schema-wizard.js');
    if (window.SchemaWizard && window.SchemaWizard.init) {
        window.SchemaWizard.init();
    }

    await import('./ingest.js');
    const { IngestModule } = window;
    window.IngestModule = IngestModule;
    if (IngestModule.initIngestUi) IngestModule.initIngestUi();

    await import('./rewrite.js');
    const { RewriteManager } = window;
    window.RewriteManager = RewriteManager;
    window.onLLMRewrite = RewriteManager.onLLMRewrite;
    window.onRewriteConfirm = RewriteManager.onRewriteConfirm;
    window.onRewriteCancel = RewriteManager.onRewriteCancel;

    await import('./event-listeners.js');
    const { EventListeners } = window;
    window.EventListeners = EventListeners;

    await import('./app.js');
    const { App, importFiles } = window;
    window.App = App;
    window.importFiles = importFiles;

    document.dispatchEvent(new Event('DOMContentLoaded'));
}

loadModules();
