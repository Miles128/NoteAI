// RAG 助手设置 / 组件管理（从 settings-components.ts 下沉）
import { saveAssistantUiConfig } from './shared';

// ---------------------------------------------------------------------------
// RAG 助手设置 / 组件管理
// ---------------------------------------------------------------------------

export function applyRagSettingsToForm(uiConfig: any) {
    var ragEl = document.getElementById('settings-assistant-rag-enabled') as HTMLInputElement | null;
    if (ragEl) {
        ragEl.checked = uiConfig.rag_enabled === true;
    }
    updateRagIndexCardVisibility(uiConfig.rag_enabled === true);

    var hydeEl = document.getElementById('settings-rag-hyde-enabled') as HTMLInputElement | null;
    if (hydeEl) {
        hydeEl.checked = uiConfig.rag_hyde_enabled !== false;
    }
    var hydeThresholdEl = document.getElementById('settings-rag-hyde-threshold') as HTMLInputElement | null;
    if (hydeThresholdEl) {
        hydeThresholdEl.value = uiConfig.rag_hyde_threshold != null ? uiConfig.rag_hyde_threshold : 0.33;
    }
    var rerankEl = document.getElementById('settings-rag-rerank-enabled') as HTMLInputElement | null;
    if (rerankEl) {
        rerankEl.checked = uiConfig.rag_rerank_enabled !== false;
    }
    var rerankSkipEl = document.getElementById('settings-rag-rerank-skip-score') as HTMLInputElement | null;
    if (rerankSkipEl) {
        rerankSkipEl.value = uiConfig.rag_rerank_skip_score != null ? uiConfig.rag_rerank_skip_score : 0.75;
    }
    var denseEl = document.getElementById('settings-rag-dense-weight') as HTMLInputElement | null;
    if (denseEl) {
        var denseWeight = uiConfig.rag_dense_weight != null ? uiConfig.rag_dense_weight : 0.7;
        denseEl.value = String(Math.round(denseWeight * 100));
    }
    var topKEl = document.getElementById('settings-rag-top-k') as HTMLInputElement | null;
    if (topKEl) {
        topKEl.value = uiConfig.rag_top_k != null ? uiConfig.rag_top_k : 5;
    }
    var topKTagsEl = document.getElementById('settings-rag-top-k-tags') as HTMLInputElement | null;
    if (topKTagsEl) {
        topKTagsEl.value = uiConfig.rag_top_k_tags != null ? uiConfig.rag_top_k_tags : 7;
    }
    var rerankModelEl = document.getElementById('settings-rag-rerank-model');
    if (rerankModelEl && uiConfig.rag_rerank_model) {
        rerankModelEl.textContent = uiConfig.rag_rerank_model;
    }
    _updateDenseWeightHint();

    if (uiConfig.rag_enabled === true) {
        refreshRagIndexStatus();
    }
    refreshComponentsStatus();
    refreshStorageUsage();
}

function _updateDenseWeightHint() {
    var denseEl = document.getElementById('settings-rag-dense-weight') as HTMLInputElement | null;
    var hintEl = document.getElementById('settings-rag-dense-weight-hint');
    if (!denseEl || !hintEl) return;
    var densePct = parseInt(denseEl.value, 10);
    if (isNaN(densePct)) densePct = 70;
    densePct = Math.max(0, Math.min(100, densePct));
    var sparsePct = 100 - densePct;
    hintEl.textContent = window.t('settings.ragDenseWeightHint', {
        dense: densePct,
        sparse: sparsePct
    });
}

function _readRagAdvancedConfig(): Record<string, any> {
    var config = _readRagPresetFromForm();
    config.rag_dense_weight = Math.max(0, Math.min(1, config.rag_dense_weight));
    return config;
}

function saveRagAdvancedConfig() {
    _updateDenseWeightHint();
    return saveAssistantUiConfig(_readRagAdvancedConfig());
}

async function refreshComponentsStatus() {
    if (!window.api || !window.api.getComponentsStatus) return;
    var statusEl = document.getElementById('settings-component-rag-status');
    var installBtn = document.getElementById('settings-component-rag-install') as HTMLButtonElement | null;
    var removeBtn = document.getElementById('settings-component-rag-remove') as HTMLButtonElement | null;
    if (!statusEl) return;
    try {
        var result = await window.api.getComponentsStatus();
        var components = (result && result.components) || [];
        var rag = components.find(function(c: any) { return c.id === 'rag'; });
        if (!rag) {
            statusEl.textContent = window.t('common.unknownError');
            return;
        }
        statusEl.className = 'settings-component-badge';
        if (rag.installed) {
            statusEl.textContent = window.t('settings.componentInstalled');
            statusEl.classList.add('is-ok');
        } else if (rag.user_removed) {
            statusEl.textContent = window.t('settings.componentRemovedByUser');
            statusEl.classList.add('is-warn');
        } else {
            statusEl.textContent = window.t('settings.componentNotInstalled');
        }
        if (installBtn) installBtn.disabled = !!rag.installed;
        if (removeBtn) removeBtn.disabled = !rag.installed;
    } catch (e) {
        statusEl.textContent = (e as Error).message || String(e);
    }
}

function _showComponentMsg(text: any, isError: any) {
    var msgEl = document.getElementById('settings-component-rag-msg');
    if (!msgEl) return;
    msgEl.textContent = text;
    msgEl.style.display = 'block';
    msgEl.style.color = isError ? 'var(--danger, #c0392b)' : 'var(--text-muted)';
}

async function installRagComponent() {
    if (!window.api || !window.api.installComponent) return;
    var installBtn = document.getElementById('settings-component-rag-install') as HTMLButtonElement | null;
    if (installBtn) installBtn.disabled = true;
    _showComponentMsg(window.t('settings.componentInstalling'), false);
    try {
        await window.api.installComponent({ id: 'rag' });
    } catch (e) {
        _showComponentMsg(window.t('settings.componentInstallFailed', { message: (e as Error).message }), true);
        if (installBtn) installBtn.disabled = false;
    }
}

async function removeRagComponent() {
    if (!window.confirm(window.t('settings.componentRemoveConfirm'))) return;
    if (!window.api || !window.api.uninstallComponent) return;
    var removeBtn = document.getElementById('settings-component-rag-remove') as HTMLButtonElement | null;
    if (removeBtn) removeBtn.disabled = true;
    try {
        var result = await window.api.uninstallComponent({ id: 'rag' });
        if (result && result.success) {
            _showComponentMsg(window.t('settings.componentRemoveDone'), false);
            var ragEl = document.getElementById('settings-assistant-rag-enabled') as HTMLInputElement | null;
            if (ragEl) {
                ragEl.checked = false;
                updateRagIndexCardVisibility(false);
            }
            await refreshComponentsStatus();
        } else {
            _showComponentMsg(window.t('settings.componentRemoveFailed', {
                message: (result && result.message) || window.t('common.unknownError')
            }), true);
            if (removeBtn) removeBtn.disabled = false;
        }
    } catch (e) {
        _showComponentMsg(window.t('settings.componentRemoveFailed', { message: (e as Error).message }), true);
        if (removeBtn) removeBtn.disabled = false;
    }
}

async function refreshRagIndexStatus() {
    var statusEl = document.getElementById('settings-assistant-index-status');
    if (!statusEl || !window.api || !window.api.ragIndexStatus) return;
    try {
        var result = await window.api.ragIndexStatus();
        if (!result || !result.success) {
            statusEl.textContent = window.t('assistant.indexStatusError', {
                message: (result && result.message) || window.t('common.unknownError')
            });
            return;
        }
        if (!result.enabled) {
            statusEl.textContent = window.t('assistant.indexStatusDisabled');
            return;
        }
        if (!result.built) {
            statusEl.textContent = window.t('assistant.indexStatusNotBuilt');
            return;
        }
        var when = result.mtime ? new Date(result.mtime * 1000).toLocaleString() : '';
        statusEl.textContent = window.t('assistant.indexStatusBuilt', {
            files: result.file_count || 0,
            chunks: result.chunk_count || 0,
            when: when
        });
    } catch (e) {
        if (statusEl) statusEl.textContent = window.t('assistant.indexStatusError', { message: (e as Error).message || String(e) });
    }
}

function updateRagIndexCardVisibility(ragEnabled: any) {
    var card = document.getElementById('settings-assistant-rag-index-card');
    if (card) {
        card.style.display = ragEnabled ? '' : 'none';
    }
    var advancedCard = document.getElementById('settings-rag-advanced-card');
    if (advancedCard) {
        advancedCard.style.display = ragEnabled ? '' : 'none';
    }
}

function _estimateIndexTime() {
    var files = (window.AppState && window.AppState.files) ? window.AppState.files.length : 0;
    var seconds = files > 0 ? Math.max(10, files * 0.5) : 60;
    if (seconds < 60) return Math.ceil(seconds) + '秒';
    return Math.ceil(seconds / 60) + '分钟';
}

function _formatStorageBytes(bytes: any) {
    var n = Number(bytes);
    if (!isFinite(n) || n <= 0) return window.t('settings.storageEmpty');
    if (n < 1024) return Math.round(n) + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function _storageSizeEl(id: any) {
    if (id === 'hf_hub') return document.getElementById('settings-storage-hf-hub-size');
    if (id === 'fastembed') return document.getElementById('settings-storage-fastembed-size');
    if (id === 'index') return document.getElementById('settings-storage-index-size');
    return null;
}

function _storageClearBtn(id: any) {
    if (id === 'hf_hub') return document.getElementById('settings-storage-clear-hf-hub') as HTMLButtonElement | null;
    if (id === 'fastembed') return document.getElementById('settings-storage-clear-fastembed') as HTMLButtonElement | null;
    if (id === 'index') return document.getElementById('settings-storage-clear-index') as HTMLButtonElement | null;
    return null;
}

function _showStorageMsg(text: any, isError: any) {
    var msgEl = document.getElementById('settings-storage-msg');
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.display = text ? 'block' : 'none';
    msgEl.style.color = isError ? 'var(--danger, #c0392b)' : 'var(--text-muted)';
}

function _applyStorageUsage(result: any) {
    var items = (result && result.items) || [];
    var byId: Record<string, any> = {};
    items.forEach(function(item: any) {
        if (item && item.id) byId[item.id] = item;
    });
    ['hf_hub', 'fastembed', 'index'].forEach(function(id) {
        var item = byId[id] || { bytes: 0 };
        var sizeEl = _storageSizeEl(id);
        if (sizeEl) sizeEl.textContent = _formatStorageBytes(item.bytes);
        var btn = _storageClearBtn(id);
        if (btn) btn.disabled = !item.bytes;
    });
    var totalEl = document.getElementById('settings-storage-total');
    if (totalEl) {
        totalEl.textContent = window.t('settings.storageTotal', {
            size: _formatStorageBytes(result && result.total_bytes),
        });
    }
}

export async function refreshStorageUsage() {
    if (!window.api || !window.api.getStorageUsage) return;
    try {
        var result = await window.api.getStorageUsage();
        if (!result || !result.success) {
            _showStorageMsg(window.t('settings.storageUnavailable'), true);
            return;
        }
        _applyStorageUsage(result);
        if (result.purged_stale_bytes > 0) {
            _showStorageMsg(window.t('settings.storageStalePurged', {
                size: _formatStorageBytes(result.purged_stale_bytes),
            }), false);
        }
    } catch (e) {
        _showStorageMsg(window.t('settings.storageUnavailable'), true);
    }
}

async function clearStorageTarget(target: any) {
    if (!window.api || !window.api.clearStorage) return;
    var sizeEl = _storageSizeEl(target);
    var sizeText = sizeEl ? sizeEl.textContent : window.t('settings.storageEmpty');
    var confirmKey = target === 'index' ? 'settings.storageClearIndexConfirm' : 'settings.storageClearModelsConfirm';
    if (!window.confirm(window.t(confirmKey, { size: sizeText || window.t('settings.storageEmpty') }))) return;
    var btn = _storageClearBtn(target);
    if (btn) btn.disabled = true;
    try {
        var result = await window.api.clearStorage([target]);
        if (!result || !result.success) {
            _showStorageMsg(window.t('settings.storageClearFailed', {
                message: (result && result.message) || window.t('common.unknownError'),
            }), true);
            if (btn) btn.disabled = false;
            return;
        }
        _applyStorageUsage(result);
        _showStorageMsg(window.t('settings.storageClearDone', {
            size: _formatStorageBytes(result.freed_bytes),
        }), false);
        if (target === 'index') {
            refreshRagIndexStatus();
        }
    } catch (e) {
        _showStorageMsg(window.t('settings.storageClearFailed', { message: (e as Error).message || String(e) }), true);
        if (btn) btn.disabled = false;
    }
}

function _bindStorageControls() {
    var mapping: Record<string, string> = {
        'settings-storage-clear-hf-hub': 'hf_hub',
        'settings-storage-clear-fastembed': 'fastembed',
        'settings-storage-clear-index': 'index',
    };
    Object.keys(mapping).forEach(function(id) {
        var el = document.getElementById(id);
        if (!el || el.dataset.bound) return;
        el.dataset.bound = '1';
        el.addEventListener('click', function() {
            clearStorageTarget(mapping[id]);
        });
    });
}

var RAG_PRESETS: Record<string, any> = {
    fast: {
        rag_hyde_enabled: false, rag_hyde_threshold: 0.33,
        rag_rerank_enabled: false, rag_rerank_skip_score: 0.75,
        rag_dense_weight: 0.6, rag_top_k: 3, rag_top_k_tags: 4,
    },
    balanced: {
        rag_hyde_enabled: true, rag_hyde_threshold: 0.33,
        rag_rerank_enabled: true, rag_rerank_skip_score: 0.75,
        rag_dense_weight: 0.7, rag_top_k: 5, rag_top_k_tags: 7,
    },
    deep: {
        rag_hyde_enabled: true, rag_hyde_threshold: 0.30,
        rag_rerank_enabled: true, rag_rerank_skip_score: 0.60,
        rag_dense_weight: 0.75, rag_top_k: 8, rag_top_k_tags: 10,
    },
};

function _readRagPresetFromForm(): Record<string, any> {
    var denseEl = document.getElementById('settings-rag-dense-weight') as HTMLInputElement | null;
    var densePct = denseEl ? parseInt(denseEl.value, 10) : 70;
    if (isNaN(densePct)) densePct = 70;
    return {
        rag_hyde_enabled: (document.getElementById('settings-rag-hyde-enabled') as HTMLInputElement | null)?.checked !== false,
        rag_hyde_threshold: parseFloat(((document.getElementById('settings-rag-hyde-threshold') as HTMLInputElement | null)?.value) || '') || 0.33,
        rag_rerank_enabled: (document.getElementById('settings-rag-rerank-enabled') as HTMLInputElement | null)?.checked !== false,
        rag_rerank_skip_score: parseFloat(((document.getElementById('settings-rag-rerank-skip-score') as HTMLInputElement | null)?.value) || '') || 0.75,
        rag_dense_weight: densePct / 100,
        rag_top_k: parseInt(((document.getElementById('settings-rag-top-k') as HTMLInputElement | null)?.value) || '', 10) || 5,
        rag_top_k_tags: parseInt(((document.getElementById('settings-rag-top-k-tags') as HTMLInputElement | null)?.value) || '', 10) || 7,
    };
}

function _syncRagPresetButtons() {
    var row = document.getElementById('settings-rag-preset-row');
    if (!row) return;
    var current = _readRagPresetFromForm();
    var matched = '';
    Object.keys(RAG_PRESETS).forEach(function(name) {
        var preset = RAG_PRESETS[name];
        var ok = Object.keys(preset).every(function(k) {
            return Math.abs((current[k] || 0) - (preset[k] || 0)) < 1e-9;
        });
        if (ok) matched = name;
    });
    var buttons = row.querySelectorAll('.rag-preset-btn');
    buttons.forEach(function(btn: any) {
        btn.classList.toggle('is-active', btn.dataset.ragPreset === matched);
    });
}

function applyRagPreset(name: string) {
    var preset = RAG_PRESETS[name];
    if (!preset) return;
    var denseEl = document.getElementById('settings-rag-dense-weight') as HTMLInputElement | null;
    if (denseEl) denseEl.value = String(Math.round((preset.rag_dense_weight || 0.7) * 100));
    var hydeEl = document.getElementById('settings-rag-hyde-enabled') as HTMLInputElement | null;
    if (hydeEl) hydeEl.checked = preset.rag_hyde_enabled !== false;
    var hydeThresholdEl = document.getElementById('settings-rag-hyde-threshold') as HTMLInputElement | null;
    if (hydeThresholdEl) hydeThresholdEl.value = String(preset.rag_hyde_threshold != null ? preset.rag_hyde_threshold : 0.33);
    var rerankEl = document.getElementById('settings-rag-rerank-enabled') as HTMLInputElement | null;
    if (rerankEl) rerankEl.checked = preset.rag_rerank_enabled !== false;
    var rerankSkipEl = document.getElementById('settings-rag-rerank-skip-score') as HTMLInputElement | null;
    if (rerankSkipEl) rerankSkipEl.value = String(preset.rag_rerank_skip_score != null ? preset.rag_rerank_skip_score : 0.75);
    var topKEl = document.getElementById('settings-rag-top-k') as HTMLInputElement | null;
    if (topKEl) topKEl.value = String(preset.rag_top_k != null ? preset.rag_top_k : 5);
    var topKTagsEl = document.getElementById('settings-rag-top-k-tags') as HTMLInputElement | null;
    if (topKTagsEl) topKTagsEl.value = String(preset.rag_top_k_tags != null ? preset.rag_top_k_tags : 7);
    _updateDenseWeightHint();
    _syncRagPresetButtons();
    saveRagAdvancedConfig();
}

function _bindRagAdvancedControls() {
    var presetRow = document.getElementById('settings-rag-preset-row');
    if (presetRow && !presetRow.dataset.bound) {
        presetRow.dataset.bound = '1';
        presetRow.querySelectorAll('.rag-preset-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var name = (btn as HTMLElement).dataset.ragPreset;
                if (name) applyRagPreset(name);
            });
        });
    }

    var denseEl = document.getElementById('settings-rag-dense-weight');
    if (denseEl && !denseEl.dataset.bound) {
        denseEl.dataset.bound = '1';
        denseEl.addEventListener('input', function() {
            _updateDenseWeightHint();
        });
        denseEl.addEventListener('change', function() {
            _syncRagPresetButtons();
            saveRagAdvancedConfig();
        });
    }

    [
        'settings-rag-hyde-enabled',
        'settings-rag-hyde-threshold',
        'settings-rag-rerank-enabled',
        'settings-rag-rerank-skip-score',
        'settings-rag-top-k',
        'settings-rag-top-k-tags',
    ].forEach(function(id) {
        var el = document.getElementById(id);
        if (!el || el.dataset.bound) return;
        el.dataset.bound = '1';
        el.addEventListener('change', function() {
            _syncRagPresetButtons();
            saveRagAdvancedConfig();
        });
    });
}

export function initRagSettings() {
    const ragEl = document.getElementById('settings-assistant-rag-enabled') as HTMLInputElement | null;
    if (ragEl && !ragEl.dataset.bound) {
        ragEl.dataset.bound = '1';
        ragEl.addEventListener('change', function() {
            var enabled = ragEl.checked;
            updateRagIndexCardVisibility(enabled);
            saveAssistantUiConfig({ rag_enabled: enabled });
            if (enabled) {
                refreshRagIndexStatus();
            } else {
                var statusEl = document.getElementById('settings-assistant-index-status');
                if (statusEl) statusEl.textContent = window.t('assistant.indexStatusDisabled');
            }
        });
    }

    if (!window.__componentInstallBound) {
        window.__componentInstallBound = true;
        document.addEventListener('component_installed', function(e: any) {
            var data = e.detail || {};
            if (data.id !== 'rag') return;
            if (data.success) {
                _showComponentMsg(window.t('settings.componentInstallDone'), false);
            } else {
                _showComponentMsg(window.t('settings.componentInstallFailed', {
                    message: data.message || window.t('common.unknownError')
                }), true);
            }
            refreshComponentsStatus();
        });
    }

    var ragInstallBtn = document.getElementById('settings-component-rag-install');
    if (ragInstallBtn && !ragInstallBtn.dataset.bound) {
        ragInstallBtn.dataset.bound = '1';
        ragInstallBtn.addEventListener('click', installRagComponent);
    }
    var ragRemoveBtn = document.getElementById('settings-component-rag-remove');
    if (ragRemoveBtn && !ragRemoveBtn.dataset.bound) {
        ragRemoveBtn.dataset.bound = '1';
        ragRemoveBtn.addEventListener('click', removeRagComponent);
    }

    _bindRagAdvancedControls();
    _bindStorageControls();

    var rebuildBtn = document.getElementById('settings-assistant-rebuild-index-btn');
    if (rebuildBtn && !rebuildBtn.dataset.bound) {
        rebuildBtn.dataset.bound = '1';
        rebuildBtn.addEventListener('click', function() {
            var statusEl = document.getElementById('settings-assistant-rebuild-status');
            var progressWrap = document.getElementById('settings-assistant-rebuild-progress');
            var progressFill = document.getElementById('settings-assistant-rebuild-progress-fill');
            var progressText = document.getElementById('settings-assistant-rebuild-progress-text');
            if (statusEl) {
                statusEl.textContent = window.t('assistant.indexBuilding', { estimate: _estimateIndexTime() });
                statusEl.style.display = 'block';
            }
            if (progressWrap) progressWrap.style.display = 'block';
            if (progressFill) progressFill.style.width = '0%';
            if (progressText) progressText.textContent = '0%';
            if (window.AssistantModule && window.AssistantModule.rebuildIndex) {
                window.AssistantModule.rebuildIndex();
            } else if (window.api && window.api.ragRebuildIndex) {
                window.api.ragRebuildIndex().catch(function(err) {
                    if (statusEl) {
                        statusEl.textContent = window.t('assistant.indexRequestFailed', {
                            message: err.message || String(err)
                        });
                        statusEl.style.display = 'block';
                    }
                });
            }
        });
    }

    // Listen for index progress events to update the settings UI bar
    if (!window.__ragIndexProgressBound) {
        window.__ragIndexProgressBound = true;
        document.addEventListener('rag-index-progress', function(e: any) {
            var data = e.detail || {};
            var progressWrap = document.getElementById('settings-assistant-rebuild-progress');
            var progressFill = document.getElementById('settings-assistant-rebuild-progress-fill');
            var progressText = document.getElementById('settings-assistant-rebuild-progress-text');
            if (progressWrap) progressWrap.style.display = 'block';
            if (progressFill) progressFill.style.width = (data.percent || 0) + '%';
            if (progressText) {
                progressText.textContent = window.t('assistant.indexProgress', {
                    percent: data.percent || 0,
                    message: data.message || ''
                });
            }
        });
        document.addEventListener('rag_index_built', function(e: any) {
            var data = e.detail || {};
            var progressWrap = document.getElementById('settings-assistant-rebuild-progress');
            var statusEl = document.getElementById('settings-assistant-rebuild-status');
            if (progressWrap) progressWrap.style.display = 'none';
            if (data.success) {
                if (statusEl) statusEl.textContent = window.t('assistant.indexBuildDone', { count: data.chunk_count || 0 });
            } else {
                if (statusEl) statusEl.textContent = window.t('assistant.indexBuildFailed', { message: data.message || '' });
            }
            refreshRagIndexStatus();
        });
    }
}
