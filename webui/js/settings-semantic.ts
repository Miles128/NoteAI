// ============================================================================
// settings-semantic.js —— 设置面板「语义关系工作台」子模块
// 职责：语义工作台启用开关、可见 tab、分析强度的读写与保存。
// 对外：window.SettingsSemantic（供薄主入口 settings.js 组装 SettingsModule）。
// 依赖：window.api / window.t / window.ToastModule / window.SemanticWorkbenchModule /
//       window.updateStatus(toast.js) /
//       window.SettingsComponents.saveAssistantUiConfig（共享保存通道，先于本模块加载）。
// ============================================================================
(function() { 'use strict';

var _SEMANTIC_TAB_VALUES = ['objects', 'quality', 'links', 'brief'];

var _SEMANTIC_DEFAULTS = {
    semantic_workbench_enabled: true,
    semantic_workbench_tabs: ['objects', 'quality', 'links', 'brief'],
    semantic_workbench_intensity: 'standard',
};

function readSemanticWorkbenchPrefs(): any {
    var fallback = {
        semantic_workbench_enabled: _SEMANTIC_DEFAULTS.semantic_workbench_enabled,
        semantic_workbench_tabs: _SEMANTIC_DEFAULTS.semantic_workbench_tabs.slice(),
        semantic_workbench_intensity: _SEMANTIC_DEFAULTS.semantic_workbench_intensity,
    };
    try {
        if (!window.Storage) return fallback;
        var stored = window.Storage.getItem(window.Storage.KEYS.SEMANTIC_WORKBENCH, null, { silent: true }) as any;
        if (!stored || typeof stored !== 'object') return fallback;
        return {
            semantic_workbench_enabled: stored.semantic_workbench_enabled !== false,
            semantic_workbench_tabs: Array.isArray(stored.semantic_workbench_tabs) && stored.semantic_workbench_tabs.length
                ? stored.semantic_workbench_tabs
                : fallback.semantic_workbench_tabs,
            semantic_workbench_intensity: ['light', 'standard', 'deep'].indexOf(stored.semantic_workbench_intensity) !== -1
                ? stored.semantic_workbench_intensity
                : fallback.semantic_workbench_intensity,
        };
    } catch (e) {
        return fallback;
    }
}

function persistSemanticWorkbenchPrefs(config: any): void {
    try {
        if (window.Storage) {
            window.Storage.setItem(window.Storage.KEYS.SEMANTIC_WORKBENCH, config, { silent: true });
        }
    } catch (e) { /* noop */ }
}

function applySemanticSettingsToForm(_uiConfig: any) {
    // 唯一数据源：localStorage（后端不再持久化这三个键）
    var prefs = readSemanticWorkbenchPrefs();
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled') as HTMLInputElement | null;
    if (enabledEl) {
        enabledEl.checked = prefs.semantic_workbench_enabled !== false;
    }
    var savedTabs = prefs.semantic_workbench_tabs;
    document.querySelectorAll('.settings-semantic-tab').forEach(function(input: any) {
        input.checked = savedTabs.indexOf(input.value) !== -1;
    });
    var intensity = prefs.semantic_workbench_intensity;
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio: any) {
        radio.checked = radio.value === intensity;
    });
    updateSemanticSettingsDisabledState();
}

function updateSemanticSettingsDisabledState() {
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled') as HTMLInputElement | null;
    var enabled = !enabledEl || enabledEl.checked;
    var tabsCard = document.getElementById('settings-semantic-tabs-card');
    var intensityCard = document.getElementById('settings-semantic-intensity-card');
    [tabsCard, intensityCard].forEach(function(card: any) {
        if (!card) return;
        card.style.opacity = enabled ? '' : '0.5';
        card.querySelectorAll('input, label').forEach(function(el: any) {
            if (el.classList.contains('switch-container')) return;
            el.disabled = !enabled;
        });
    });
}

function readSemanticWorkbenchConfig() {
    var enabled = true;
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled') as HTMLInputElement | null;
    if (enabledEl) enabled = enabledEl.checked;
    var tabs = _SEMANTIC_TAB_VALUES.filter(function(value: any) {
        var input = document.querySelector('.settings-semantic-tab[value="' + value + '"]') as HTMLInputElement | null;
        return input ? input.checked : true;
    });
    var intensity = 'standard';
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio: any) {
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
    persistSemanticWorkbenchPrefs(config);
    if (window.ToastModule) window.ToastModule.show(window.t ? window.t('settings.autoSaved') : '已保存');
    if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.applyVisibilityConfig) {
        window.SemanticWorkbenchModule.applyVisibilityConfig();
    }
    return Promise.resolve(config);
}

function initSemanticWorkbenchSettings() {
    var enabledEl = document.getElementById('settings-semantic-workbench-enabled') as HTMLInputElement | null;
    if (enabledEl && !enabledEl.dataset.bound) {
        enabledEl.dataset.bound = '1';
        enabledEl.addEventListener('change', function() {
            updateSemanticSettingsDisabledState();
            saveSemanticWorkbenchConfig();
        });
    }
    document.querySelectorAll('.settings-semantic-tab').forEach(function(input: any) {
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
    document.querySelectorAll('input[name="settings-semantic-intensity"]').forEach(function(radio: any) {
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
    readSemanticWorkbenchPrefs,
    persistSemanticWorkbenchPrefs,
};

})();
