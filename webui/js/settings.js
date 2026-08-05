// ============================================================================
// settings.js —— 设置面板薄主入口
// 职责：tab 切换协调、设置面板/导航的全局事件绑定、子模块初始化编排、
//       组装对外 window.SettingsModule（公开方法签名与拆分前完全一致）。
// 子模块（须先于本文件加载，见 main.mjs 顺序契约）：
//   settings-general.js    -> window.SettingsGeneral（API 配置/排版/语言/可靠性）
//   settings-components.js -> window.SettingsComponents（RAG/组件/CLI/合并阈值）
//   settings-semantic.js   -> window.SettingsSemantic（语义工作台设置）
// ============================================================================
(function() { 'use strict';

function switchSettingsTab(tabName) {
    document.querySelectorAll('.settings-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.classList.toggle('active', tab.id === 'tab-' + tabName);
    });
    if (tabName === 'cli') {
        window.SettingsComponents.initCliSettings();
        window.SettingsComponents.refreshCliAgentsSettings();
    }
    if (tabName === 'organize-rules' && window.OrganizeRulesModule && window.OrganizeRulesModule.load) {
        window.OrganizeRulesModule.load();
    }
    if (tabName === 'reliability') {
        window.SettingsGeneral.initReliabilitySettings();
    }
}

// 本模块由 main.mjs 动态 import，执行时 DOM 已解析完成，直接初始化（不再依赖 DOMContentLoaded 重放）
(function() {
    var settingsPanel = document.getElementById('settings-panel');
    if (settingsPanel) {
        settingsPanel.addEventListener('click', function(e) {
            if (e.target === settingsPanel) window.SettingsGeneral.closeSettingsPanel();
        });
    }

    var settingsNav = document.getElementById('settings-nav');
    if (settingsNav) {
        settingsNav.addEventListener('click', function(e) {
            var btn = e.target.closest('.settings-nav-btn');
            if (btn && btn.dataset.tab) {
                switchSettingsTab(btn.dataset.tab);
            }
        });
    }

    window.SettingsComponents.initRagSettings();
    window.SettingsComponents.initCliSettings();
    window.SettingsComponents.initIngestAutoSettings();
    window.SettingsComponents.initTopicAutoThresholdSettings();
    window.SettingsComponents.initMergePresetSettings();
    window.SettingsComponents.initMergeAdvancedSettings();
    window.SettingsSemantic.initSemanticWorkbenchSettings();
})();

// ---------------------------------------------------------------------------
// 对外接口：window.SettingsModule（签名与拆分前保持一致）
// ---------------------------------------------------------------------------

window.SettingsModule = {
    saveApiConfig: window.SettingsGeneral.saveApiConfig,
    loadApiConfigToForm: window.SettingsGeneral.loadApiConfigToForm,
    refreshLog: window.SettingsGeneral.refreshLog,
    closeSettingsPanel: window.SettingsGeneral.closeSettingsPanel,
    closeLogPanel: window.SettingsGeneral.closeLogPanel,
    switchSettingsTab,
    autoSaveConfig: window.SettingsGeneral.autoSaveConfig,
    resetApiConfig: window.SettingsGeneral.resetApiConfig,
    saveFontSize: window.SettingsGeneral.saveFontSize,
    saveFontFamily: window.SettingsGeneral.saveFontFamily,
    saveTypographySettings: window.SettingsGeneral.saveTypographySettings,
    applyTypographyToForm: window.SettingsGeneral.applyTypographyToForm,
    loadUiConfigToForm: window.SettingsGeneral.loadUiConfigToForm,
    setLocale: window.SettingsGeneral.setLocale,
    initRagSettings: window.SettingsComponents.initRagSettings,
    initIngestAutoSettings: window.SettingsComponents.initIngestAutoSettings,
    initTopicAutoThresholdSettings: window.SettingsComponents.initTopicAutoThresholdSettings,
    initMergePresetSettings: window.SettingsComponents.initMergePresetSettings,
    initMergeAdvancedSettings: window.SettingsComponents.initMergeAdvancedSettings,
    applyMergeAdvancedToForm: window.SettingsComponents.applyMergeAdvancedToForm,
    initCliSettings: window.SettingsComponents.initCliSettings,
    applyRagSettingsToForm: window.SettingsComponents.applyRagSettingsToForm,
    applyCliSettingsToForm: window.SettingsComponents.applyCliSettingsToForm,
    refreshCliAgentsSettings: window.SettingsComponents.refreshCliAgentsSettings,
    persistCliAgentId: window.SettingsComponents.persistCliAgentId,
    syncCliAgentSelectors: window.SettingsComponents.syncCliAgentSelectors,
    applySemanticSettingsToForm: window.SettingsSemantic.applySemanticSettingsToForm,
    initSemanticWorkbenchSettings: window.SettingsSemantic.initSemanticWorkbenchSettings,
    saveSemanticWorkbenchConfig: window.SettingsSemantic.saveSemanticWorkbenchConfig,
    // backward-compatible aliases
    initAssistantSettings: window.SettingsComponents.initAssistantSettings,
    applyAssistantSettingsToForm: window.SettingsComponents.applyAssistantSettingsToForm,
};

window.saveApiConfig = window.SettingsGeneral.saveApiConfig;
window.refreshLog = window.SettingsGeneral.refreshLog;
window.closeSettingsPanel = window.SettingsGeneral.closeSettingsPanel;
window.closeLogPanel = window.SettingsGeneral.closeLogPanel;
window.resetApiConfig = window.SettingsGeneral.resetApiConfig;

})();
