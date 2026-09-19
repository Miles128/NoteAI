/**
 * settings-components/index.ts —— 设置面板「组件」子模块出口。
 * 职责拆分：rag.ts（RAG 设置/组件安装/索引状态/存储清理/预设）、cli.ts（CLI Agent）、
 * merge.ts（入库自动化/合并阈值）、shared.ts（保存通道）。
 * 对外：window.SettingsComponents（供薄主入口 settings.ts 组装 SettingsModule）。
 */
import { initRagSettings, applyRagSettingsToForm, refreshStorageUsage } from './rag';
import { applyCliSettingsToForm, refreshCliAgentsSettings, persistCliAgentId, _syncCliAgentSelectors, initCliSettings } from './cli';
import { initIngestAutoSettings, initTopicAutoThresholdSettings, initMergePresetSettings, initMergeAdvancedSettings, applyMergeAdvancedToForm } from './merge';
import { saveAssistantUiConfig } from './shared';

(function() { 'use strict';

window.SettingsComponents = {
    initRagSettings,
    initIngestAutoSettings,
    initTopicAutoThresholdSettings,
    initMergePresetSettings,
    initMergeAdvancedSettings,
    applyMergeAdvancedToForm,
    initCliSettings,
    applyRagSettingsToForm,
    applyCliSettingsToForm,
    refreshCliAgentsSettings,
    persistCliAgentId,
    refreshStorageUsage,
    syncCliAgentSelectors: _syncCliAgentSelectors,
    // 共享保存通道（settings-semantic.js 等子模块复用，避免逐字重复实现）
    saveAssistantUiConfig,
    // backward-compatible aliases
    initAssistantSettings: initRagSettings,
    applyAssistantSettingsToForm: applyRagSettingsToForm,
};

})();