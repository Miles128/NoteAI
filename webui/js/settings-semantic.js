// ============================================================================
// settings-semantic.js —— 设置面板「语义关系工作台」子模块
// 职责：语义工作台启用开关、可见 tab、分析强度的读写与保存。
// 对外：window.SettingsSemantic（供薄主入口 settings.js 组装 SettingsModule）。
// 依赖：window.api / window.t / window.ToastModule / window.SemanticWorkbenchModule /
//       window.updateStatus(toast.js) /
//       window.SettingsComponents.saveAssistantUiConfig（共享保存通道，先于本模块加载）。
// ============================================================================
(function() { 'use strict';

var _SEMANTIC_TAB_VALUES = ['objects', 'claims', 'quality', 'conflicts', 'links', 'brief'];

function applySemanticSettingsToForm(uiConfig) {
    if (!uiConfig) return;
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled');
    if (enabledEl) {
        enabledEl.checked = uiConfig.semantic_workbench_enabled !== false;
    }
    var savedTabs = Array.isArray(uiConfig.semantic_workbench_tabs)
        ? uiConfig.semantic_workbench_tabs
        : _SEMANTIC_TAB_VALUES;
    document.querySelectorAll('.settings-semantic-tab').forEach(function(input) {
        input.checked = savedTabs.indexOf(input.value) !== -1;
    });
    var intensity = ['light', 'standard', 'deep'].indexOf(uiConfig.semantic_workbench_intensity) !== -1
        ? uiConfig.semantic_workbench_intensity
        : 'standard';
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio) {
        radio.checked = radio.value === intensity;
    });
    updateSemanticSettingsDisabledState();
}

function updateSemanticSettingsDisabledState() {
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled');
    var enabled = !enabledEl || enabledEl.checked;
    var tabsCard = document.getElementById('settings-semantic-tabs-card');
    var intensityCard = document.getElementById('settings-semantic-intensity-card');
    [tabsCard, intensityCard].forEach(function(card) {
        if (!card) return;
        card.style.opacity = enabled ? '' : '0.5';
        card.querySelectorAll('input, label').forEach(function(el) {
            if (el.classList.contains('switch-container')) return;
            el.disabled = !enabled;
        });
    });
}

function readSemanticWorkbenchConfig() {
    var enabled = true;
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled');
    if (enabledEl) enabled = enabledEl.checked;
    var tabs = _SEMANTIC_TAB_VALUES.filter(function(value) {
        var input = document.querySelector('.settings-semantic-tab[value="' + value + '"]');
        return input ? input.checked : true;
    });
    var intensity = 'standard';
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio) {
        if (radio.checked) intensity = radio.value;
    });
    return {
        semantic_workbench_enabled: enabled,
        semantic_workbench_tabs: tabs,
        semantic_workbench_intensity: intensity
    };
}

function saveSemanticWorkbenchConfig() {
    var config = readSemanticWorkbenchConfig();
    return window.SettingsComponents.saveAssistantUiConfig(config).then(function(result) {
        if (result && result.success && window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.applyVisibilityConfig) {
            window.SemanticWorkbenchModule.applyVisibilityConfig();
        }
        return result;
    });
}

function initSemanticWorkbenchSettings() {
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled');
    if (enabledEl && !enabledEl.dataset.bound) {
        enabledEl.dataset.bound = '1';
        enabledEl.addEventListener('change', function() {
            updateSemanticSettingsDisabledState();
            saveSemanticWorkbenchConfig();
        });
    }
    document.querySelectorAll('.settings-semantic-tab').forEach(function(input) {
        if (input.dataset.bound) return;
        input.dataset.bound = '1';
        input.addEventListener('change', function() {
            var tabs = readSemanticWorkbenchConfig().semantic_workbench_tabs;
            if (!tabs.length) {
                input.checked = true;
                window.ToastModule && window.ToastModule.error(window.t('settings.semanticAtLeastOneTab'));
                return;
            }
            saveSemanticWorkbenchConfig();
        });
    });
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio) {
        if (radio.dataset.bound) return;
        radio.dataset.bound = '1';
        radio.addEventListener('change', function() {
            if (radio.checked) saveSemanticWorkbenchConfig();
        });
    });
}

window.SettingsSemantic = {
    applySemanticSettingsToForm,
    initSemanticWorkbenchSettings,
    saveSemanticWorkbenchConfig,
};

})();
