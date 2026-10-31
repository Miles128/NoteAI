/**
 * ai-gate.ts —— AI 功能开关（总开关 + 分项）与界面精简的统一应用层。
 *
 * 数据来源：uiConfig（ai_enabled / ai_chat_enabled / ai_writing_enabled /
 * ai_compile_enabled / semantic_compile_enabled / ui_hide_statusbar /
 * ui_hide_home_stats）。
 *
 * 生效方式：
 * - 给 body 打 data-ai-* 属性，CSS 负责隐藏对应入口（见 css/ai-gate.css）；
 * - 对外暴露 isOn(feature) / guard(feature)，供事件处理做兜底拦截；
 * - 界面精简通过 body class 生效。
 */
(function () { 'use strict';

type AIFeature = 'chat' | 'writing' | 'compile' | 'semantic';

var FEATURE_FLAGS: Record<AIFeature, string> = {
    chat: 'ai_chat_enabled',
    writing: 'ai_writing_enabled',
    compile: 'ai_compile_enabled',
    semantic: 'semantic_compile_enabled',
};

var FEATURE_LABELS: Record<AIFeature, string> = {
    chat: 'AI 问答与检索',
    writing: 'AI 改写与划词解释',
    compile: 'AI 编译与主题分类',
    semantic: '语义抽取',
};

var _config: any = null;

function featureEnabled(cfg: any, feature: AIFeature): boolean {
    if (!cfg) return true;
    if (cfg.ai_enabled === false) return false;
    var flag = FEATURE_FLAGS[feature];
    if (!(flag in cfg)) return true;
    return cfg[flag] !== false;
}

function datasetKey(feature: AIFeature): string {
    return 'ai' + feature.charAt(0).toUpperCase() + feature.slice(1);
}

function applyUiPrefs(cfg: any) {
    var body = document.body;
    body.classList.toggle('ui-hide-statusbar', cfg.ui_hide_statusbar === true);
    body.classList.toggle('ui-hide-home-stats', cfg.ui_hide_home_stats === true);
}

function ensureVisibleInspectorTab() {
    if (!window.InspectorModule || !window.InspectorModule.getCurrentTab) return;
    var current = window.InspectorModule.getCurrentTab();
    if (current === 'ai' && !featureEnabled(_config, 'chat')) {
        window.InspectorModule.switchTab?.('properties');
    } else if (current === 'semantic' && !featureEnabled(_config, 'semantic')) {
        window.InspectorModule.switchTab?.('properties');
    }
}

function apply(cfg: any) {
    _config = cfg || {};
    var body = document.body;
    body.setAttribute('data-ai-master', _config.ai_enabled === false ? 'off' : 'on');

    (Object.keys(FEATURE_FLAGS) as AIFeature[]).forEach(function (feature) {
        body.setAttribute('data-' + datasetKey(feature).replace(/[A-Z]/g, function (c) {
            return '-' + c.toLowerCase();
        }), featureEnabled(_config, feature) ? 'on' : 'off');
    });

    applyUiPrefs(_config);

    if (!featureEnabled(_config, 'chat') && window.AssistantModule && window.AssistantModule.close) {
        try { window.AssistantModule.close(); } catch (_e) { /* noop */ }
    }
    ensureVisibleInspectorTab();
}

function isOn(feature: AIFeature): boolean {
    return featureEnabled(_config || window.uiConfig || {}, feature);
}

function guard(feature: AIFeature): boolean {
    if (isOn(feature)) return true;
    var message = window.t
        ? window.t('settings.aiBlocked', { feature: FEATURE_LABELS[feature] })
        : FEATURE_LABELS[feature] + ' 已关闭';
    if (window.ToastModule && window.ToastModule.show) {
        window.ToastModule.show(message, 'info');
    } else if (window.updateStatus) {
        window.updateStatus(message);
    }
    return false;
}

function refresh(): Promise<any> {
    if (!window.state || !window.state.loadUiConfig) {
        apply(window.uiConfig);
        return Promise.resolve(window.uiConfig);
    }
    return window.state.loadUiConfig(true).then(function (cfg: any) {
        apply(cfg);
        return cfg;
    }).catch(function () {
        apply(window.uiConfig);
    });
}

window.AIGate = {
    apply: apply,
    refresh: refresh,
    isOn: isOn,
    guard: guard,
};

})();
