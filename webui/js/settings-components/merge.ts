// 入库自动化 / 主题阈值 / 合并预设与高级阈值（从 settings-components.ts 下沉）

import { saveAssistantUiConfig } from './shared';

// ---------------------------------------------------------------------------
// 入库自动化 / 主题阈值 / 合并预设与高级阈值
// ---------------------------------------------------------------------------

export function initIngestAutoSettings() {
    const el = document.getElementById('settings-ingest-auto-enabled') as HTMLInputElement | null;
    if (!el || el.dataset.bound) return;
    el.dataset.bound = '1';
    el.addEventListener('change', function() {
        saveAssistantUiConfig({ ingest_auto_enabled: el.checked });
    });
}

export function initMergePresetSettings() {
    var els = document.querySelectorAll('input[name="settings-merge-preset"]') as NodeListOf<HTMLInputElement>;
    if (!els.length || els[0].dataset.bound) return;
    els.forEach(function(el) { el.dataset.bound = '1'; });
    els.forEach(function(el) {
        el.addEventListener('change', function() {
            if (!el.checked) return;
            saveAssistantUiConfig({ merge_preset: el.value });
            clearMergeAdvancedForm();
        });
    });
}

var _MERGE_THRESHOLD_FIELDS = [
    'overlap_sim', 'coverage', 'title', 'topic', 'content', 'score', 'topic_name', 'topic_content'
];

function _mergeThresholdEl(key: any) {
    return document.getElementById('settings-merge-threshold-' + key) as HTMLInputElement | null;
}

export function applyMergeAdvancedToForm(overrides: any) {
    _MERGE_THRESHOLD_FIELDS.forEach(function(key) {
        var el = _mergeThresholdEl(key);
        if (!el) return;
        var value = overrides && overrides[key];
        el.value = (value != null && value !== '') ? value : '';
    });
}

function clearMergeAdvancedForm() {
    _MERGE_THRESHOLD_FIELDS.forEach(function(key) {
        var el = _mergeThresholdEl(key);
        if (el) el.value = '';
    });
    saveMergeAdvancedConfig();
}

function _readMergeAdvancedConfig() {
    var overrides: Record<string, any> = {};
    _MERGE_THRESHOLD_FIELDS.forEach(function(key) {
        var el = _mergeThresholdEl(key);
        if (!el) return;
        var value = parseFloat(el.value);
        if (isNaN(value)) return;
        value = Math.max(0, Math.min(1, value));
        el.value = value.toFixed(2);
        overrides[key] = value;
    });
    return overrides;
}

function saveMergeAdvancedConfig() {
    return saveAssistantUiConfig({ merge_overrides: _readMergeAdvancedConfig() });
}

export function initMergeAdvancedSettings() {
    const toggle = document.getElementById('settings-merge-advanced-toggle');
    const panel = document.getElementById('settings-merge-advanced');
    if (toggle && panel && !toggle.dataset.bound) {
        toggle.dataset.bound = '1';
        toggle.addEventListener('click', function() {
            var hidden = panel.style.display === 'none';
            panel.style.display = hidden ? 'block' : 'none';
            toggle.textContent = window.t(hidden ? 'settings.mergeAdvancedHide' : 'settings.mergeAdvancedToggle');
        });
    }
    _MERGE_THRESHOLD_FIELDS.forEach(function(key) {
        var el = _mergeThresholdEl(key);
        if (!el || el.dataset.bound) return;
        el.dataset.bound = '1';
        el.addEventListener('change', function() {
            saveMergeAdvancedConfig();
        });
    });
}

export function initTopicAutoThresholdSettings() {
    const el = document.getElementById('settings-topic-auto-threshold') as HTMLInputElement | null;
    if (!el || el.dataset.bound) return;
    el.dataset.bound = '1';
    el.addEventListener('change', async function() {
        var value = parseFloat(el.value);
        if (isNaN(value)) value = 0.80;
        value = Math.max(0, Math.min(1, value));
        el.value = value.toFixed(2);
        var saved = await saveAssistantUiConfig({ topic_auto_assign_threshold: value });
        if (!saved || !saved.success || !window.api || !window.api.applyTopicPlacementThreshold) return;
        try {
            var result = await window.api.applyTopicPlacementThreshold();
            if (result && result.success) {
                window.updateStatus(window.t('settings.topicThresholdApplied', { count: result.moved_count || 0 }));
                if (typeof window.loadPendingItems === 'function') window.loadPendingItems();
            } else {
                window.updateStatus((result && result.message) || window.t('pending.operationFailed'));
            }
        } catch (e) {
            window.updateStatus((e as Error).message || window.t('pending.operationFailed'));
        }
    });
}
