// ============================================================================
// graph-layout-params.js —— 图谱布局参数面板模块（自 G3.js 拆出）
// 职责：布局参数默认值/Schema、参数配置持久化（Storage 读写）、
//       布局模式持久化、参数面板 UI（表单构建/打开/关闭/读取/应用调度）、
//       graphOpenLayoutSettings 等全局函数（index.html onclick 使用）。
// 对外：window.GraphLayoutParams
//   数据:  defaults / schema / load / save / resetStorage / loadMode / saveMode
//   面板:  buildForm / open / close / readForm / scheduleApply / reset
// 依赖（均为调用时动态读取，无加载期耦合）：
//   window.Storage（index.html 经典脚本 storage.js）
//   window.Graph3Tier（G3.js，面板 open/close/reset 时回调其 layoutConfig /
//   applyLayoutSettings / reloadGraphLayout / resize）
// 加载顺序（main.mjs）：storage.js 经典脚本 -> 本模块 -> G3.js。
// ============================================================================
(function() { 'use strict';

const GRAPH_LAYOUT_STORAGE_KEY = window.Storage.KEYS.GRAPH_LAYOUT;
const GRAPH_LAYOUT_MODE_STORAGE_KEY = window.Storage.KEYS.GRAPH_LAYOUT_MODE;
const GRAPH_LAYOUT_MODE_DEFAULT = 'tree';

/** @type {Record<string, number>} */
const GRAPH_LAYOUT_DEFAULTS = {
    l1PackRatio: 0.3,
    orphanRadiusRatio: 0.12,
    l1NoteMaxRingRatio: 0.28,
    l2AnnulusGap: 9,
    l2InnerFallbackRatio: 0.3,
    l2OuterRingRatio: 0.92,
    annulusMinSpan: 12,
    annulusSingleTopicRatio: 0.55,
    annulusAngleOffset: 0.9,
    l3InnerRatio: 0.4,
    l3InnerMinGap: 6,
    noteDiskMin: 6,
    noteDiskMax: 30,
    noteDiskBase: 3.5,
    noteDiskSqrtCoef: 2.2,
    noteSingleRadiusRatio: 0.16,
    l2RingMin: 32,
    l2RingMax: 88,
    l2RingBase: 16,
    l2RingSqrtL2: 7.5,
    l2RingSqrtNotes: 1.5,
    l3RingMin: 10,
    l3RingMax: 32,
    l3RingBase: 7,
    l3RingSqrtL3: 4.5,
    topicCollidePad: 13,
    fileCollidePad: 4,
    chargeL1: -18,
    chargeTopic: -14,
    chargeFile: -5,
    targetStrengthTopic: 0.88,
    targetStrengthFile: 0.8,
    clusterRepelDist: 150,
    clusterRepelForce: 520,
    collideIterations: 5,
    simAlpha: 0.55,
    simAlphaDecay: 0.12,
    simVelocityDecay: 0.72,
    radiusL1: 5,
    radiusOther: 4,
    fitPad: 60,
    fitMaxScale: 1.5,
    clampSideRatio: 0.12,
    boundsMargin: 52,
    replayRevealMinMs: 800,
    replayRevealMaxMs: 3000,
    replayRevealBudgetMs: 24000,
};

/** @type {{ key: string, groupKey: string, min: number, max: number, step: number }[]} */
const GRAPH_LAYOUT_SCHEMA = [
    { key: 'l1PackRatio', groupKey: 'l1Global', min: 0.08, max: 0.5, step: 0.01 },
    { key: 'orphanRadiusRatio', groupKey: 'l1Global', min: 0.04, max: 0.25, step: 0.01 },
    { key: 'l1NoteMaxRingRatio', groupKey: 'l2Layout', min: 0.1, max: 0.5, step: 0.01 },
    { key: 'l2AnnulusGap', groupKey: 'l2Layout', min: 0, max: 40, step: 1 },
    { key: 'l2InnerFallbackRatio', groupKey: 'l2Layout', min: 0.1, max: 0.6, step: 0.01 },
    { key: 'l2OuterRingRatio', groupKey: 'l2Layout', min: 0.7, max: 1, step: 0.01 },
    { key: 'annulusMinSpan', groupKey: 'l2Layout', min: 4, max: 40, step: 1 },
    { key: 'annulusSingleTopicRatio', groupKey: 'l2Layout', min: 0.3, max: 0.8, step: 0.01 },
    { key: 'annulusAngleOffset', groupKey: 'l2Layout', min: 0, max: 3.14, step: 0.05 },
    { key: 'l3InnerRatio', groupKey: 'l3Layout', min: 0.2, max: 0.7, step: 0.01 },
    { key: 'l3InnerMinGap', groupKey: 'l3Layout', min: 0, max: 20, step: 1 },
    { key: 'noteDiskMin', groupKey: 'noteScatter', min: 3, max: 30, step: 1 },
    { key: 'noteDiskMax', groupKey: 'noteScatter', min: 15, max: 80, step: 1 },
    { key: 'noteDiskBase', groupKey: 'noteScatter', min: 0, max: 20, step: 0.5 },
    { key: 'noteDiskSqrtCoef', groupKey: 'noteScatter', min: 0.5, max: 8, step: 0.1 },
    { key: 'noteSingleRadiusRatio', groupKey: 'noteScatter', min: 0.05, max: 0.4, step: 0.01 },
    { key: 'l2RingMin', groupKey: 'l2RingFormula', min: 16, max: 80, step: 1 },
    { key: 'l2RingMax', groupKey: 'l2RingFormula', min: 40, max: 160, step: 1 },
    { key: 'l2RingBase', groupKey: 'l2RingFormula', min: 0, max: 40, step: 1 },
    { key: 'l2RingSqrtL2', groupKey: 'l2RingFormula', min: 0, max: 20, step: 0.5 },
    { key: 'l2RingSqrtNotes', groupKey: 'l2RingFormula', min: 0, max: 5, step: 0.1 },
    { key: 'l3RingMin', groupKey: 'l3RingFormula', min: 6, max: 40, step: 1 },
    { key: 'l3RingMax', groupKey: 'l3RingFormula', min: 16, max: 80, step: 1 },
    { key: 'l3RingBase', groupKey: 'l3RingFormula', min: 0, max: 30, step: 1 },
    { key: 'l3RingSqrtL3', groupKey: 'l3RingFormula', min: 0, max: 12, step: 0.5 },
    { key: 'topicCollidePad', groupKey: 'simulation', min: 0, max: 30, step: 1 },
    { key: 'fileCollidePad', groupKey: 'simulation', min: 0, max: 20, step: 1 },
    { key: 'chargeL1', groupKey: 'simulation', min: -80, max: -1, step: 1 },
    { key: 'chargeTopic', groupKey: 'simulation', min: -60, max: -1, step: 1 },
    { key: 'chargeFile', groupKey: 'simulation', min: -40, max: 0, step: 1 },
    { key: 'targetStrengthTopic', groupKey: 'simulation', min: 0.3, max: 1, step: 0.01 },
    { key: 'targetStrengthFile', groupKey: 'simulation', min: 0.3, max: 1, step: 0.01 },
    { key: 'clusterRepelDist', groupKey: 'simulation', min: 40, max: 300, step: 5 },
    { key: 'clusterRepelForce', groupKey: 'simulation', min: 50, max: 1200, step: 10 },
    { key: 'collideIterations', groupKey: 'simulation', min: 1, max: 12, step: 1 },
    { key: 'simAlpha', groupKey: 'simulation', min: 0.1, max: 1, step: 0.05 },
    { key: 'simAlphaDecay', groupKey: 'simulation', min: 0.02, max: 0.3, step: 0.01 },
    { key: 'simVelocityDecay', groupKey: 'simulation', min: 0.3, max: 0.95, step: 0.01 },
    { key: 'radiusL1', groupKey: 'nodeDisplay', min: 3, max: 16, step: 1 },
    { key: 'radiusOther', groupKey: 'nodeDisplay', min: 2, max: 14, step: 1 },
    { key: 'fitPad', groupKey: 'view', min: 20, max: 120, step: 5 },
    { key: 'fitMaxScale', groupKey: 'view', min: 0.5, max: 3, step: 0.1 },
    { key: 'clampSideRatio', groupKey: 'view', min: 0.05, max: 0.25, step: 0.01 },
    { key: 'boundsMargin', groupKey: 'view', min: 20, max: 120, step: 4 },
    { key: 'replayRevealMinMs', groupKey: 'replay', min: 200, max: 3000, step: 50 },
    { key: 'replayRevealMaxMs', groupKey: 'replay', min: 500, max: 8000, step: 100 },
    { key: 'replayRevealBudgetMs', groupKey: 'replay', min: 5000, max: 60000, step: 500 },
];

function _graphLayoutSchemaByKey() {
    const map: Record<string, any> = {};
    GRAPH_LAYOUT_SCHEMA.forEach(function(p) { map[p.key] = p; });
    return map;
}

function _formatGraphLayoutValue(v: any, step: any) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '';
    if (step >= 1) return String(Math.round(n));
    if (step >= 0.1) return n.toFixed(1);
    return n.toFixed(2);
}

function _snapGraphLayoutValue(v: any, param: any) {
    const n = Number(v);
    if (!Number.isFinite(n)) return param.min;
    const steps = Math.round((n - param.min) / param.step);
    const snapped = param.min + steps * param.step;
    return Math.min(param.max, Math.max(param.min, snapped));
}

function loadGraphLayoutConfig() {
    const cfg: Record<string, any> = Object.assign({}, GRAPH_LAYOUT_DEFAULTS);
    const saved: any = window.Storage.getItem(GRAPH_LAYOUT_STORAGE_KEY, null, { silent: true });
    if (saved) {
        const schema = _graphLayoutSchemaByKey();
        Object.keys(saved).forEach(function(key: any) {
            if (!schema[key]) return;
            const v = Number(saved[key]);
            if (!Number.isFinite(v)) return;
            const p = schema[key];
            cfg[key] = Math.min(p.max, Math.max(p.min, v));
        });
    }
    return cfg;
}

function saveGraphLayoutConfig(cfg: any) {
    window.Storage.setItem(GRAPH_LAYOUT_STORAGE_KEY, cfg);
}

function resetGraphLayoutConfigStorage() {
    window.Storage.removeItem(GRAPH_LAYOUT_STORAGE_KEY);
}

function loadGraphLayoutMode() {
    const saved: any = window.Storage.getItem(
        GRAPH_LAYOUT_MODE_STORAGE_KEY,
        GRAPH_LAYOUT_MODE_DEFAULT,
        { silent: true }
    );
    return saved === 'constellation' || saved === 'tree' ? saved : GRAPH_LAYOUT_MODE_DEFAULT;
}

function saveGraphLayoutMode(mode: any) {
    window.Storage.setItem(GRAPH_LAYOUT_MODE_STORAGE_KEY, mode, { silent: true });
}

function _graph() {
    return window.Graph3Tier as any;
}

// ---------------------------------------------------------------------------
// 面板 UI
// ---------------------------------------------------------------------------

let _layoutApplyTimer: any = null;

function buildForm(cfg: any) {
    const form = document.getElementById('graph-settings-form');
    if (!form) return;
    form.innerHTML = '';
    let lastGroup = '';
    GRAPH_LAYOUT_SCHEMA.forEach(function(param) {
        if (param.groupKey !== lastGroup) {
            lastGroup = param.groupKey;
            const title = document.createElement('div');
            title.className = 'graph-settings-group-title';
            title.textContent = window.t('graph.paramGroup.' + param.groupKey);
            form.appendChild(title);
        }
        const value = _snapGraphLayoutValue(cfg[param.key], param);
        const row = document.createElement('div');
        row.className = 'graph-settings-row';
        const head = document.createElement('div');
        head.className = 'graph-settings-row-head';
        const label = document.createElement('span');
        label.className = 'graph-settings-label';
        label.textContent = window.t('graph.param.' + param.key);
        const valueEl = document.createElement('span');
        valueEl.className = 'graph-settings-value';
        valueEl.textContent = _formatGraphLayoutValue(value, param.step);
        const input = document.createElement('input');
        input.type = 'range';
        input.className = 'graph-settings-range';
        input.dataset.key = param.key;
        input.min = String(param.min);
        input.max = String(param.max);
        input.step = String(param.step);
        input.value = String(value);
        input.addEventListener('input', function() {
            valueEl.textContent = _formatGraphLayoutValue(input.value, param.step);
            scheduleApply();
        });
        input.addEventListener('change', function() {
            valueEl.textContent = _formatGraphLayoutValue(input.value, param.step);
            if (_layoutApplyTimer) {
                clearTimeout(_layoutApplyTimer);
                _layoutApplyTimer = null;
            }
            const g = _graph();
            if (g) g.applyLayoutSettings(readForm());
        });
        head.appendChild(label);
        head.appendChild(valueEl);
        row.appendChild(head);
        row.appendChild(input);
        form.appendChild(row);
    });
}

function open() {
    const g = _graph();
    if (!g) return;
    const panel = document.getElementById('graph-panel');
    const sidebar = document.getElementById('graph-settings-sidebar');
    const btn = document.getElementById('graph-layout-settings-btn');
    if (!panel || !sidebar) return;
    if (!sidebar.hidden && panel.classList.contains('graph-settings-open')) {
        close();
        return;
    }
    buildForm(g.layoutConfig);
    sidebar.hidden = false;
    panel.classList.add('graph-settings-open');
    if (btn) btn.classList.add('active');
    requestAnimationFrame(function() { g.resize(); });
}

function close() {
    const g = _graph();
    const panel = document.getElementById('graph-panel');
    const sidebar = document.getElementById('graph-settings-sidebar');
    const btn = document.getElementById('graph-layout-settings-btn');
    if (_layoutApplyTimer) {
        clearTimeout(_layoutApplyTimer);
        _layoutApplyTimer = null;
    }
    if (sidebar) sidebar.hidden = true;
    if (panel) panel.classList.remove('graph-settings-open');
    if (btn) btn.classList.remove('active');
    if (!g) return;
    requestAnimationFrame(function() {
        requestAnimationFrame(function() {
            if (g.data && g.data.nodes && g.data.nodes.length) {
                g.reloadGraphLayout();
            } else {
                g.resize();
            }
        });
    });
}

function readForm() {
    const g = _graph();
    const cfg: Record<string, any> = Object.assign({}, g ? g.layoutConfig : GRAPH_LAYOUT_DEFAULTS);
    const schema = _graphLayoutSchemaByKey();
    document.querySelectorAll('#graph-settings-form .graph-settings-range').forEach(function(input: any) {
        const key = input.dataset.key;
        if (!key || !schema[key]) return;
        const p = schema[key];
        cfg[key] = _snapGraphLayoutValue(input.value, p);
    });
    return cfg;
}

function scheduleApply() {
    if (_layoutApplyTimer) clearTimeout(_layoutApplyTimer);
    _layoutApplyTimer = setTimeout(function() {
        _layoutApplyTimer = null;
        const g = _graph();
        if (g) g.applyLayoutSettings(readForm());
    }, 100);
}

function reset() {
    const g = _graph();
    if (!g) return;
    resetGraphLayoutConfigStorage();
    g.layoutConfig = loadGraphLayoutConfig();
    buildForm(g.layoutConfig);
    g.applyLayoutSettings(g.layoutConfig);
}

window.GraphLayoutParams = {
    defaults: GRAPH_LAYOUT_DEFAULTS,
    schema: GRAPH_LAYOUT_SCHEMA,
    load: loadGraphLayoutConfig,
    save: saveGraphLayoutConfig,
    resetStorage: resetGraphLayoutConfigStorage,
    loadMode: loadGraphLayoutMode,
    saveMode: saveGraphLayoutMode,
    buildForm: buildForm,
    open: open,
    close: close,
    readForm: readForm,
    scheduleApply: scheduleApply,
    reset: reset,
};

// index.html onclick 使用的全局函数（行为与拆分前一致）
window.graphOpenLayoutSettings = function graphOpenLayoutSettings() { window.GraphLayoutParams!.open!(); };
window.graphCloseLayoutSettings = function graphCloseLayoutSettings() { window.GraphLayoutParams!.close!(); };
window.graphApplyLayoutSettings = function graphApplyLayoutSettings() {
    const g = _graph();
    if (g) g.applyLayoutSettings(window.GraphLayoutParams!.readForm!());
};
window.graphResetLayoutSettings = function graphResetLayoutSettings() { window.GraphLayoutParams!.reset!(); };

})();
