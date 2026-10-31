/**
 * settings-ai.ts —— 设置面板「AI 功能」总开关/分项开关 + 界面精简开关。
 *
 * 保存走 saveAssistantUiConfig（window.state.saveUiConfig 门面），
 * 保存成功后立即调用 window.AIGate.apply(window.uiConfig) 让入口消失/恢复。
 */
import { saveAssistantUiConfig } from './settings-components/shared';

type FeatureInput = {
    inputId: string;
    configKey: string;
};

var FEATURE_INPUTS: FeatureInput[] = [
    { inputId: 'settings-ai-chat-enabled', configKey: 'ai_chat_enabled' },
    { inputId: 'settings-ai-writing-enabled', configKey: 'ai_writing_enabled' },
    { inputId: 'settings-ai-compile-enabled', configKey: 'ai_compile_enabled' },
    { inputId: 'settings-ai-semantic-enabled', configKey: 'semantic_compile_enabled' },
];

function _el(id: string): HTMLInputElement | null {
    return document.getElementById(id) as HTMLInputElement | null;
}

function _syncFeatureDisabledState(masterEnabled: boolean) {
    var list = document.getElementById('settings-ai-feature-list');
    if (!list) return;
    list.style.opacity = masterEnabled ? '' : '0.5';
    FEATURE_INPUTS.forEach(function (item) {
        var input = _el(item.inputId);
        if (input) input.disabled = !masterEnabled;
    });
}

function applyToForm(cfg: any) {
    cfg = cfg || {};
    var master = _el('settings-ai-enabled');
    if (master) master.checked = cfg.ai_enabled !== false;

    var saved: Record<string, boolean> = {
        ai_chat_enabled: cfg.ai_chat_enabled !== false,
        ai_writing_enabled: cfg.ai_writing_enabled !== false,
        ai_compile_enabled: cfg.ai_compile_enabled !== false,
        semantic_compile_enabled: cfg.semantic_compile_enabled !== false,
    };
    FEATURE_INPUTS.forEach(function (item) {
        var input = _el(item.inputId);
        if (input) input.checked = saved[item.configKey] !== false;
    });
    _syncFeatureDisabledState(master ? master.checked : true);

    var hideStatusbar = _el('settings-ui-hide-statusbar');
    if (hideStatusbar) hideStatusbar.checked = cfg.ui_hide_statusbar === true;
    var hideHomeStats = _el('settings-ui-hide-home-stats');
    if (hideHomeStats) hideHomeStats.checked = cfg.ui_hide_home_stats === true;
    var startupLint = _el('settings-ui-startup-lint');
    if (startupLint) startupLint.checked = cfg.startup_lint_enabled === true;
}

async function _save(partial: Record<string, any>) {
    var result = await saveAssistantUiConfig(partial);
    if (window.AIGate) window.AIGate.apply(window.uiConfig);
    return result;
}

function init() {
    const master = _el('settings-ai-enabled');
    if (master) {
        master.addEventListener('change', function () {
            _syncFeatureDisabledState(master.checked);
            _save({ ai_enabled: master.checked });
        });
    }

    FEATURE_INPUTS.forEach(function (item) {
        const input = _el(item.inputId);
        if (!input) return;
        input.addEventListener('change', function () {
            var partial: Record<string, any> = {};
            partial[item.configKey] = input.checked;
            _save(partial);
        });
    });

    const hideStatusbar = _el('settings-ui-hide-statusbar');
    if (hideStatusbar) {
        hideStatusbar.addEventListener('change', function () {
            _save({ ui_hide_statusbar: hideStatusbar.checked });
        });
    }

    const hideHomeStats = _el('settings-ui-hide-home-stats');
    if (hideHomeStats) {
        hideHomeStats.addEventListener('change', function () {
            _save({ ui_hide_home_stats: hideHomeStats.checked });
        });
    }

    const startupLint = _el('settings-ui-startup-lint');
    if (startupLint) {
        startupLint.addEventListener('change', function () {
            _save({ startup_lint_enabled: startupLint.checked });
        });
    }
}

window.SettingsAI = {
    init: init,
    applyToForm: applyToForm,
};

export {};
