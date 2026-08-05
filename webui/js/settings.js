(function() { 'use strict';

async function saveApiConfig() {
    const apiKeyEl = document.getElementById('api-key');
    const apiBaseEl = document.getElementById('api-base');
    const modelNameEl = document.getElementById('model-name');
    const temperatureEl = document.getElementById('temperature');
    const maxTokensEl = document.getElementById('max-tokens');
    const maxContextEl = document.getElementById('max-context');

    const config = {
        api_key: apiKeyEl ? apiKeyEl.value : '',
        api_base: apiBaseEl ? apiBaseEl.value : 'https://api.openai.com/v1',
        model_name: modelNameEl ? modelNameEl.value : 'gpt-4',
        temperature: temperatureEl ? parseFloat(temperatureEl.value) : 0.7,
        max_tokens: maxTokensEl ? parseInt(maxTokensEl.value) : 32000,
        max_context_tokens: maxContextEl ? parseInt(maxContextEl.value) : 128000,
        disable_thinking: document.getElementById('disable-thinking') ? document.getElementById('disable-thinking').checked : true
    };

    const statusEl = document.getElementById('api-config-status');
    const popupStatusEl = document.getElementById('api-config-status-popup');

    const showStatus = (msg, isError = false) => {
        if (statusEl) {
            statusEl.textContent = msg;
            statusEl.style.color = isError ? '#e53e3e' : '#38a169';
            statusEl.style.display = 'block';
        }
        if (popupStatusEl) {
            popupStatusEl.textContent = msg;
            popupStatusEl.style.color = isError ? '#e53e3e' : '#38a169';
            popupStatusEl.style.display = 'block';
        }
    };

    const hideStatus = () => {
        if (statusEl) statusEl.style.display = 'none';
        if (popupStatusEl) popupStatusEl.style.display = 'none';
    };

    showStatus(window.t('settings.testingConnection'));
    try {
        const result = await window.api.saveApiConfig(config);
        if (result && result.success) {
            showStatus(window.t('settings.configSaved'));
            setTimeout(hideStatus, 3000);
        } else {
            showStatus(result?.message || window.t('settings.saveFailed'), true);
        }
    } catch (e) {
        showStatus(window.t('settings.saveFailed') + ': ' + e.message, true);
    }
}

async function loadApiConfigToForm() {
    try {
        const apiConfig = await window.api.getApiConfig();
        if (apiConfig) {
            const apiKeyEl = document.getElementById('api-key');
            const apiBaseEl = document.getElementById('api-base');
            const modelNameEl = document.getElementById('model-name');
            const tempEl = document.getElementById('temperature');
            const maxTokensEl = document.getElementById('max-tokens');
            const maxContextEl = document.getElementById('max-context');

            if (apiKeyEl) apiKeyEl.value = apiConfig.api_key || '';
            if (apiBaseEl) apiBaseEl.value = apiConfig.api_base || 'https://api.openai.com/v1';
            if (modelNameEl) modelNameEl.value = apiConfig.model_name || 'gpt-4';
            if (tempEl) tempEl.value = apiConfig.temperature || 0.7;
            if (maxTokensEl) maxTokensEl.value = apiConfig.max_tokens || 32000;
            if (maxContextEl) maxContextEl.value = apiConfig.max_context_tokens || 128000;

            var disableThinkingEl = document.getElementById('disable-thinking');
            if (disableThinkingEl) {
                disableThinkingEl.checked = apiConfig.disable_thinking !== false;
            }
        }
    } catch (e) {
        console.error('[Settings] Load API config error:', e);
    }
}

async function refreshLog() {
    try {
        const result = await window.api.refreshLog();
        if (result && result.success) {
            updateStatus(window.t('settings.logRefreshed'));
        }
    } catch (e) {
        console.error('[Settings] Refresh log error:', e);
    }
}

function closeSettingsPanel() {
    const settingsPanel = document.getElementById('settings-panel');
    if (settingsPanel) {
        settingsPanel.classList.remove('active');
    }
}

function closeLogPanel() {
    const logPanel = document.getElementById('log-panel');
    if (logPanel) {
        logPanel.classList.remove('active');
    }
}

function switchSettingsTab(tabName) {
    document.querySelectorAll('.settings-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.classList.toggle('active', tab.id === 'tab-' + tabName);
    });
    if (tabName === 'cli') {
        initCliSettings();
        refreshCliAgentsSettings();
    }
    if (tabName === 'organize-rules' && window.OrganizeRulesModule && window.OrganizeRulesModule.load) {
        window.OrganizeRulesModule.load();
    }
    if (tabName === 'reliability') {
        initReliabilitySettings();
    }
}

// ---------------------------------------------------------------------------
// 备份与恢复 / 索引健康（本地可靠性）
// ---------------------------------------------------------------------------

function showReliabilityStatus(elId, msg, isError) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    el.style.color = isError ? '#e53e3e' : '#38a169';
}

function hideReliabilityStatus(elId) {
    const el = document.getElementById(elId);
    if (el) el.style.display = 'none';
}

function formatBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function backupWorkspaceNow() {
    const btn = document.getElementById('settings-backup-btn');
    if (btn) btn.disabled = true;
    hideReliabilityStatus('settings-backup-status');
    try {
        const result = await window.api.backupWorkspace({});
        if (!result || !result.success) throw new Error((result && result.message) || window.t('common.unknownError'));
        const msg = window.t('settings.reliabilityBackupDone', {
            path: result.backup_path,
            size: formatBytes(result.size_bytes),
            count: result.file_count || 0
        });
        showReliabilityStatus('settings-backup-status', msg, false);
        if (window.ToastModule) window.ToastModule.success(window.t('settings.reliabilityBackupSuccess'));
    } catch (e) {
        showReliabilityStatus('settings-backup-status', window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function exportNotesNow() {
    const btn = document.getElementById('settings-export-btn');
    if (btn) btn.disabled = true;
    hideReliabilityStatus('settings-backup-status');
    try {
        const result = await window.api.exportNotes({});
        if (!result || !result.success) throw new Error((result && result.message) || window.t('common.unknownError'));
        showReliabilityStatus('settings-backup-status', window.t('settings.reliabilityExportDone', {
            path: result.backup_path,
            size: formatBytes(result.size_bytes),
            count: result.file_count || 0
        }), false);
        if (window.ToastModule) window.ToastModule.success(window.t('settings.reliabilityExportSuccess'));
    } catch (e) {
        showReliabilityStatus('settings-backup-status', window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function restoreBackupNow() {
    let file = '';
    try {
        file = await window.api.openArchiveDialog();
    } catch (e) {
        showReliabilityStatus('settings-restore-status', window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
        return;
    }
    if (!file) return;
    if (!window.confirm(window.t('settings.reliabilityRestoreConfirm'))) return;
    const btn = document.getElementById('settings-restore-btn');
    if (btn) btn.disabled = true;
    hideReliabilityStatus('settings-restore-status');
    try {
        const result = await window.api.restoreWorkspaceBackup({ backup_path: file });
        if (!result || !result.success) throw new Error((result && result.message) || window.t('common.unknownError'));
        showReliabilityStatus('settings-restore-status', window.t('settings.reliabilityRestoreDone', {
            count: result.restored_count || 0,
            note: result.note || ''
        }), false);
        if (window.ToastModule) window.ToastModule.success(window.t('settings.reliabilityRestoreSuccess'));
    } catch (e) {
        showReliabilityStatus('settings-restore-status', window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function healthBadge(ok) {
    return ok ? window.escapeHtml(window.t('settings.health.ok')) : window.escapeHtml(window.t('settings.health.bad'));
}

function renderHealthReport(report) {
    const el = document.getElementById('settings-health-report');
    if (!el) return;
    const rows = ['rag', 'semantic', 'links', 'fulltext'].map(function(key) {
        const item = report[key] || {};
        const cls = item.ok ? 'settings-health-ok' : 'settings-health-bad';
        return '<div class="settings-health-row"><span class="settings-health-name">' + window.escapeHtml(window.t('settings.health.' + key)) + '</span><span class="settings-health-badge ' + cls + '">' + healthBadge(item.ok) + '</span><span class="settings-health-detail">' + window.escapeHtml(item.detail || '') + '</span></div>';
    }).join('');
    el.innerHTML = rows;
    el.style.display = 'block';
    const ragBtn = document.getElementById('settings-health-rag-btn');
    const semanticBtn = document.getElementById('settings-health-semantic-btn');
    const lintBtn = document.getElementById('settings-health-lint-btn');
    if (ragBtn) ragBtn.style.display = report.rag && !report.rag.ok ? 'inline-block' : 'none';
    if (semanticBtn) semanticBtn.style.display = report.semantic && !report.semantic.ok ? 'inline-block' : 'none';
    if (lintBtn) lintBtn.style.display = report.links && !report.links.ok ? 'inline-block' : 'none';
}

async function runHealthCheck() {
    const btn = document.getElementById('settings-health-check-btn');
    if (btn) btn.disabled = true;
    hideReliabilityStatus('settings-health-status');
    try {
        const result = await window.api.getIndexHealth();
        if (!result || !result.success) throw new Error((result && result.message) || window.t('common.unknownError'));
        renderHealthReport(result);
    } catch (e) {
        const el = document.getElementById('settings-health-report');
        if (el) el.style.display = 'none';
        showReliabilityStatus('settings-health-status', window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function runHealthRecovery(kind) {
    const statusEl = 'settings-health-status';
    hideReliabilityStatus(statusEl);
    try {
        let result;
        if (kind === 'rag') {
            result = await window.api.ragRebuildIndex({});
        } else if (kind === 'semantic') {
            result = await window.api.startSemanticFullCompile({});
        } else if (kind === 'lint') {
            result = await window.api.runKbLint({});
        }
        if (result && !result.success) throw new Error(result.message || window.t('common.unknownError'));
        showReliabilityStatus(statusEl, window.t('settings.health.recoveryQueued'), false);
        if (window.ToastModule) window.ToastModule.success(window.t('settings.health.recoveryQueued'));
    } catch (e) {
        showReliabilityStatus(statusEl, window.t('settings.reliabilityFailed', { message: e.message || String(e) }), true);
    }
}

function initReliabilitySettings() {
    const backupBtn = document.getElementById('settings-backup-btn');
    if (backupBtn && !backupBtn.dataset.bound) {
        backupBtn.dataset.bound = '1';
        backupBtn.addEventListener('click', backupWorkspaceNow);
    }
    const exportBtn = document.getElementById('settings-export-btn');
    if (exportBtn && !exportBtn.dataset.bound) {
        exportBtn.dataset.bound = '1';
        exportBtn.addEventListener('click', exportNotesNow);
    }
    const restoreBtn = document.getElementById('settings-restore-btn');
    if (restoreBtn && !restoreBtn.dataset.bound) {
        restoreBtn.dataset.bound = '1';
        restoreBtn.addEventListener('click', restoreBackupNow);
    }
    const healthBtn = document.getElementById('settings-health-check-btn');
    if (healthBtn && !healthBtn.dataset.bound) {
        healthBtn.dataset.bound = '1';
        healthBtn.addEventListener('click', runHealthCheck);
    }
    const ragBtn = document.getElementById('settings-health-rag-btn');
    if (ragBtn && !ragBtn.dataset.bound) {
        ragBtn.dataset.bound = '1';
        ragBtn.addEventListener('click', function() { runHealthRecovery('rag'); });
    }
    const semanticBtn = document.getElementById('settings-health-semantic-btn');
    if (semanticBtn && !semanticBtn.dataset.bound) {
        semanticBtn.dataset.bound = '1';
        semanticBtn.addEventListener('click', function() { runHealthRecovery('semantic'); });
    }
    const lintBtn = document.getElementById('settings-health-lint-btn');
    if (lintBtn && !lintBtn.dataset.bound) {
        lintBtn.dataset.bound = '1';
        lintBtn.addEventListener('click', function() { runHealthRecovery('lint'); });
    }
}

// 本模块由 main.mjs 动态 import，执行时 DOM 已解析完成，直接初始化（不再依赖 DOMContentLoaded 重放）
(function() {
    var settingsPanel = document.getElementById('settings-panel');
    if (settingsPanel) {
        settingsPanel.addEventListener('click', function(e) {
            if (e.target === settingsPanel) closeSettingsPanel();
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

    initRagSettings();
    initCliSettings();
    initIngestAutoSettings();
    initTopicAutoThresholdSettings();
    initMergePresetSettings();
    initMergeAdvancedSettings();
    initSemanticWorkbenchSettings();
})();

async function autoSaveConfig() {
    try {
        const uiConfig = {
            web_ai_assist: document.getElementById('web-ai-toggle')?.checked || false,
            web_include_images: document.getElementById('web-include-images')?.checked || false,
            conv_ai_assist: document.getElementById('conv-ai-toggle')?.checked || false,
            auto_topic: true,
            topic_list: document.getElementById('topic-list')?.value || ''
        };

        const result = await window.api.saveUiConfig(uiConfig);
        if (result && result.success) {
            updateStatus(window.t('settings.autoSaved'));
        } else {
            updateStatus(window.t('settings.autoSaveFailed', { message: result?.message || window.t('common.unknownError') }));
        }
    } catch (e) {
        console.error('[Settings] Auto save config error:', e);
    }
}

function resetApiConfig() {
    const apiBaseEl = document.getElementById('api-base');
    const modelNameEl = document.getElementById('model-name');
    const tempEl = document.getElementById('temperature');
    const maxTokensEl = document.getElementById('max-tokens');
    const maxContextEl = document.getElementById('max-context');

    if (apiBaseEl) apiBaseEl.value = 'https://api.openai.com/v1';
    if (modelNameEl) modelNameEl.value = 'gpt-4';
    if (tempEl) tempEl.value = 0.7;
    if (maxTokensEl) maxTokensEl.value = 32000;
    if (maxContextEl) maxContextEl.value = 128000;
}

async function saveFontSize(size) {
    try {
        var result = await window.api.saveUiConfig({ font_size: size });
        if (!result || !result.success) {
            console.error('[Settings] save font_size failed:', result);
        }
    } catch (e) {
        console.error('[Settings] save font_size error:', e);
    }
}

async function saveFontFamily(key, value) {
    try {
        var payload = {};
        payload[key] = value;
        var result = await window.api.saveUiConfig(payload);
        if (!result || !result.success) {
            console.error('[Settings] save font family failed:', result);
        }
    } catch (e) {
        console.error('[Settings] save font family error:', e);
    }
}

function getTypographyFromForm() {
    var roles = ['h1', 'h2', 'h3', 'body', 'quote'];
    var next = {};
    roles.forEach(function(role) {
        var familyEl = document.getElementById('typography-' + role + '-family');
        var styleEl = document.getElementById('typography-' + role + '-style');
        next[role] = {
            family: familyEl ? familyEl.value : 'system',
            style: styleEl ? styleEl.value : 'normal'
        };
    });
    return window.ThemeModule && window.ThemeModule.normalizeTypography
        ? window.ThemeModule.normalizeTypography(next)
        : next;
}

function applyTypographyToForm(typography) {
    var normalized = window.ThemeModule && window.ThemeModule.normalizeTypography
        ? window.ThemeModule.normalizeTypography(typography)
        : (typography || {});
    Object.keys(normalized).forEach(function(role) {
        var familyEl = document.getElementById('typography-' + role + '-family');
        var styleEl = document.getElementById('typography-' + role + '-style');
        if (familyEl) familyEl.value = normalized[role].family;
        if (styleEl) styleEl.value = normalized[role].style;
    });
}

async function saveTypographySettings() {
    var typography = getTypographyFromForm();
    if (window.ThemeModule && window.ThemeModule.applyTypography) {
        window.ThemeModule.applyTypography(typography);
    }
    try {
        var result = await window.api.saveUiConfig({ typography: typography });
        if (!result || !result.success) {
            console.error('[Settings] save typography failed:', result);
        }
    } catch (e) {
        console.error('[Settings] save typography error:', e);
    }
}

async function setLocale(locale) {
    if (!window.I18nModule || !window.I18nModule.setLocale) return;
    try {
        await window.I18nModule.setLocale(locale);
        if (typeof window.updateSidebarStats === 'function') {
            window.updateSidebarStats();
        }
        if (window.I18nModule.applyDomI18n) {
            window.I18nModule.applyDomI18n(document.getElementById('settings-panel'));
        }
    } catch (e) {
        console.error('[Settings] setLocale error:', e);
    }
}

async function loadUiConfigToForm() {
    try {
        var uiConfig = await window.api.getUiConfig();
        if (uiConfig) {
            var savedFontSize = uiConfig.font_size || 'small';
            if (window.ThemeModule && window.ThemeModule.restoreFontSize) {
                window.ThemeModule.setFontSize(savedFontSize);
            }
            document.querySelectorAll('input[name="font-size"]').forEach(function(radio) {
                radio.checked = radio.value === savedFontSize;
            });
            var sidebarFont = uiConfig.sidebar_font_family || 'system';
            var previewFont = uiConfig.preview_font_family || 'system';
            if (window.ThemeModule && window.ThemeModule.applyContentFonts) {
                window.ThemeModule.applyContentFonts(sidebarFont, previewFont);
                try {
                    localStorage.setItem('noteai_sidebar_font_family', sidebarFont);
                    localStorage.setItem('noteai_preview_font_family', previewFont);
                } catch (_e) {}
            }
            var typography = uiConfig.typography || {};
            if (window.ThemeModule && window.ThemeModule.applyTypography) {
                typography = window.ThemeModule.applyTypography(typography);
            }
            applyTypographyToForm(typography);
            var loc = uiConfig.locale === 'en' ? 'en' : 'zh-CN';
            document.querySelectorAll('input[name="ui-locale"]').forEach(function(radio) {
                radio.checked = radio.value === loc;
            });
            var ingestAutoEl = document.getElementById('settings-ingest-auto-enabled');
            if (ingestAutoEl) {
                ingestAutoEl.checked = uiConfig.ingest_auto_enabled !== false;
            }
            var topicThresholdEl = document.getElementById('settings-topic-auto-threshold');
            if (topicThresholdEl) {
                topicThresholdEl.value = uiConfig.topic_auto_assign_threshold != null ? uiConfig.topic_auto_assign_threshold : 0.80;
            }
            var mergePresetEls = document.querySelectorAll('input[name="settings-merge-preset"]');
            if (mergePresetEls.length) {
                var savedPreset = uiConfig.merge_preset || 'balanced';
                mergePresetEls.forEach(function(radio) { radio.checked = radio.value === savedPreset; });
            }
            applyMergeAdvancedToForm(uiConfig.merge_overrides || {});
            applyRagSettingsToForm(uiConfig);
            applyCliSettingsToForm(uiConfig);
            applySemanticSettingsToForm(uiConfig);
        }
    } catch (e) {
        console.error('[Settings] Load UI config error:', e);
    }
}

function applyRagSettingsToForm(uiConfig) {
    var ragEl = document.getElementById('settings-assistant-rag-enabled');
    if (ragEl) {
        ragEl.checked = uiConfig.rag_enabled === true;
    }
    updateRagIndexCardVisibility(uiConfig.rag_enabled === true);

    var hydeEl = document.getElementById('settings-rag-hyde-enabled');
    if (hydeEl) {
        hydeEl.checked = uiConfig.rag_hyde_enabled !== false;
    }
    var hydeThresholdEl = document.getElementById('settings-rag-hyde-threshold');
    if (hydeThresholdEl) {
        hydeThresholdEl.value = uiConfig.rag_hyde_threshold != null ? uiConfig.rag_hyde_threshold : 0.33;
    }
    var rerankEl = document.getElementById('settings-rag-rerank-enabled');
    if (rerankEl) {
        rerankEl.checked = uiConfig.rag_rerank_enabled !== false;
    }
    var rerankSkipEl = document.getElementById('settings-rag-rerank-skip-score');
    if (rerankSkipEl) {
        rerankSkipEl.value = uiConfig.rag_rerank_skip_score != null ? uiConfig.rag_rerank_skip_score : 0.75;
    }
    var denseEl = document.getElementById('settings-rag-dense-weight');
    if (denseEl) {
        var denseWeight = uiConfig.rag_dense_weight != null ? uiConfig.rag_dense_weight : 0.7;
        denseEl.value = Math.round(denseWeight * 100);
    }
    var topKEl = document.getElementById('settings-rag-top-k');
    if (topKEl) {
        topKEl.value = uiConfig.rag_top_k != null ? uiConfig.rag_top_k : 5;
    }
    var topKTagsEl = document.getElementById('settings-rag-top-k-tags');
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
}

function _updateDenseWeightHint() {
    var denseEl = document.getElementById('settings-rag-dense-weight');
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

function _readRagAdvancedConfig() {
    var denseEl = document.getElementById('settings-rag-dense-weight');
    var densePct = denseEl ? parseInt(denseEl.value, 10) : 70;
    if (isNaN(densePct)) densePct = 70;
    densePct = Math.max(0, Math.min(100, densePct));

    return {
        rag_hyde_enabled: document.getElementById('settings-rag-hyde-enabled')?.checked !== false,
        rag_hyde_threshold: parseFloat(document.getElementById('settings-rag-hyde-threshold')?.value) || 0.33,
        rag_rerank_enabled: document.getElementById('settings-rag-rerank-enabled')?.checked !== false,
        rag_rerank_skip_score: parseFloat(document.getElementById('settings-rag-rerank-skip-score')?.value) || 0.75,
        rag_dense_weight: densePct / 100,
        rag_top_k: parseInt(document.getElementById('settings-rag-top-k')?.value, 10) || 5,
        rag_top_k_tags: parseInt(document.getElementById('settings-rag-top-k-tags')?.value, 10) || 7,
    };
}

function saveRagAdvancedConfig() {
    _updateDenseWeightHint();
    return saveAssistantUiConfig(_readRagAdvancedConfig());
}

function applyCliSettingsToForm(uiConfig) {
    var selectEl = document.getElementById('settings-cli-agent-select');
    if (selectEl && uiConfig && uiConfig.cli_agent_id) {
        if (selectEl.querySelector('option[value="' + uiConfig.cli_agent_id + '"]')) {
            selectEl.value = uiConfig.cli_agent_id;
        }
    }
}

function _showCliAgentSaveStatus(message, isError) {
    var statusEl = document.getElementById('settings-cli-save-status');
    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.style.color = isError ? '#e53e3e' : 'var(--text-muted)';
        statusEl.textContent = message;
    }
    if (window.ToastModule && window.ToastModule.show && isError) {
        window.ToastModule.show(message, 'error');
    }
}

function _syncCliAgentSelectors(agentId) {
    var nextId = agentId || '';
    var settingsSel = document.getElementById('settings-cli-agent-select');
    var tabSel = document.getElementById('cli-agent-selector');
    if (settingsSel) {
        if (nextId && settingsSel.querySelector('option[value="' + nextId + '"]')) {
            settingsSel.value = nextId;
        } else if (!nextId) {
            settingsSel.value = '';
        }
    }
    if (tabSel) {
        if (nextId && tabSel.querySelector('option[value="' + nextId + '"]')) {
            tabSel.value = nextId;
        } else if (!nextId) {
            tabSel.value = '';
        }
    }
    if (window.CliAgentModule && window.CliAgentModule.applySavedAgentId) {
        window.CliAgentModule.applySavedAgentId(nextId);
    }
}

async function persistCliAgentId(agentId) {
    var nextId = String(agentId || '').trim();
    try {
        var saver = (window.state && window.state.saveUiConfig)
            ? window.state.saveUiConfig.bind(window.state)
            : window.api.saveUiConfig.bind(window.api);
        var result = await saver({ cli_agent_id: nextId });
        if (result && result.success) {
            _syncCliAgentSelectors(nextId);
            _showCliAgentSaveStatus(window.t('settings.autoSaved'), false);
            updateStatus(window.t('settings.autoSaved'));
            return result;
        }
        var failMsg = window.t('settings.autoSaveFailed', {
            message: (result && result.message) || window.t('common.unknownError'),
        });
        _showCliAgentSaveStatus(failMsg, true);
        updateStatus(failMsg);
        return result;
    } catch (e) {
        console.error('[Settings] persist cli_agent_id error:', e);
        var errMsg = window.t('settings.autoSaveFailed', { message: e.message || String(e) });
        _showCliAgentSaveStatus(errMsg, true);
        updateStatus(errMsg);
        return null;
    }
}

var _cliAgentsRefreshGen = 0;

async function refreshComponentsStatus() {
    if (!window.api || !window.api.getComponentsStatus) return;
    var statusEl = document.getElementById('settings-component-rag-status');
    var installBtn = document.getElementById('settings-component-rag-install');
    var removeBtn = document.getElementById('settings-component-rag-remove');
    if (!statusEl) return;
    try {
        var result = await window.api.getComponentsStatus();
        var components = (result && result.components) || [];
        var rag = components.find(function(c) { return c.id === 'rag'; });
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
        statusEl.textContent = e.message || String(e);
    }
}

function _showComponentMsg(text, isError) {
    var msgEl = document.getElementById('settings-component-rag-msg');
    if (!msgEl) return;
    msgEl.textContent = text;
    msgEl.style.display = 'block';
    msgEl.style.color = isError ? 'var(--danger, #c0392b)' : 'var(--text-muted)';
}

async function installRagComponent() {
    if (!window.api || !window.api.installComponent) return;
    var installBtn = document.getElementById('settings-component-rag-install');
    if (installBtn) installBtn.disabled = true;
    _showComponentMsg(window.t('settings.componentInstalling'), false);
    try {
        await window.api.installComponent({ id: 'rag' });
    } catch (e) {
        _showComponentMsg(window.t('settings.componentInstallFailed', { message: e.message }), true);
        if (installBtn) installBtn.disabled = false;
    }
}

async function removeRagComponent() {
    if (!window.confirm(window.t('settings.componentRemoveConfirm'))) return;
    if (!window.api || !window.api.uninstallComponent) return;
    var removeBtn = document.getElementById('settings-component-rag-remove');
    if (removeBtn) removeBtn.disabled = true;
    try {
        var result = await window.api.uninstallComponent({ id: 'rag' });
        if (result && result.success) {
            _showComponentMsg(window.t('settings.componentRemoveDone'), false);
            var ragEl = document.getElementById('settings-assistant-rag-enabled');
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
        _showComponentMsg(window.t('settings.componentRemoveFailed', { message: e.message }), true);
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
        if (statusEl) statusEl.textContent = window.t('assistant.indexStatusError', { message: e.message || String(e) });
    }
}

function updateRagIndexCardVisibility(ragEnabled) {
    var card = document.getElementById('settings-assistant-rag-index-card');
    if (card) {
        card.style.display = ragEnabled ? '' : 'none';
    }
    var advancedCard = document.getElementById('settings-rag-advanced-card');
    if (advancedCard) {
        advancedCard.style.display = ragEnabled ? '' : 'none';
    }
}

async function saveAssistantUiConfig(partial) {
    try {
        var result = await window.api.saveUiConfig(partial);
        if (result && result.success) {
            updateStatus(window.t('settings.autoSaved'));
        } else {
            updateStatus(window.t('settings.autoSaveFailed', {
                message: (result && result.message) || window.t('common.unknownError'),
            }));
        }
        return result;
    } catch (e) {
        console.error('[Settings] save assistant config error:', e);
        return null;
    }
}

async function refreshCliAgentsSettings() {
    var listEl = document.getElementById('settings-cli-agents-list');
    var selectEl = document.getElementById('settings-cli-agent-select');
    if (!listEl || !window.api || !window.api.listCliAgents) return;

    var refreshGen = ++_cliAgentsRefreshGen;
    listEl.innerHTML = '<p class="settings-hint">' + window.escapeHtml(window.t('settings.cliAgentsLoading')) + '</p>';

    try {
        var result = await window.api.listCliAgents();
        if (refreshGen !== _cliAgentsRefreshGen) return;

        var agents = (result && result.success && Array.isArray(result.agents)) ? result.agents : [];
        var uiConfig = {};
        if (window.state && window.state.getState) {
            uiConfig = window.state.getState().uiConfig || {};
        }
        if (!uiConfig.cli_agent_id && window.api.getUiConfig) {
            uiConfig = await window.api.getUiConfig();
        }
        if (refreshGen !== _cliAgentsRefreshGen) return;

        var pendingId = (selectEl && selectEl.dataset.pendingValue) ? String(selectEl.dataset.pendingValue) : '';
        var savedId = pendingId || ((uiConfig && uiConfig.cli_agent_id) ? String(uiConfig.cli_agent_id) : '');

        if (selectEl) {
            selectEl.innerHTML = '';
            var placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = window.t('settings.cliDefaultPlaceholder');
            selectEl.appendChild(placeholder);
            agents.forEach(function(agent) {
                var opt = document.createElement('option');
                opt.value = agent.id;
                opt.textContent = agent.name + (agent.installed ? '' : ' (' + window.t('settings.cliAgentNotInstalled') + ')');
                opt.disabled = !agent.installed;
                if (agent.resolved_path) {
                    opt.title = agent.resolved_path;
                }
                selectEl.appendChild(opt);
            });
            if (savedId && agents.some(function(a) { return a.id === savedId && a.installed; })) {
                selectEl.value = savedId;
            }
        }

        if (!agents.length) {
            listEl.innerHTML = '<p class="settings-hint">' + window.escapeHtml(window.t('settings.cliAgentsEmpty')) + '</p>';
            return;
        }

        listEl.innerHTML = '';
        agents.forEach(function(agent) {
            var row = document.createElement('div');
            row.className = 'settings-component-row settings-cli-agent-row';

            var info = document.createElement('div');
            info.className = 'settings-component-info';

            var name = document.createElement('div');
            name.className = 'settings-component-name';
            name.textContent = agent.name;

            var desc = document.createElement('p');
            desc.className = 'settings-hint';
            desc.textContent = agent.description || agent.command || '';

            var badge = document.createElement('span');
            badge.className = 'settings-component-badge' + (agent.installed ? ' is-ok' : '');
            badge.textContent = agent.installed
                ? window.t('settings.cliAgentInstalled')
                : window.t('settings.cliAgentNotInstalled');

            info.appendChild(name);
            info.appendChild(desc);
            info.appendChild(badge);
            if (agent.resolved_path) {
                var pathHint = document.createElement('p');
                pathHint.className = 'settings-hint';
                pathHint.style.fontSize = '11px';
                pathHint.textContent = agent.resolved_path;
                info.appendChild(pathHint);
            }
            row.appendChild(info);
            listEl.appendChild(row);
        });
    } catch (e) {
        listEl.innerHTML = '<p class="settings-hint" style="color:var(--danger,#c0392b)">' +
            window.escapeHtml(window.t('settings.cliAgentsLoadFailed', { message: e.message || String(e) })) + '</p>';
    }
}

function initCliSettings() {
    var selectEl = document.getElementById('settings-cli-agent-select');
    if (selectEl && !selectEl.dataset.bound) {
        selectEl.dataset.bound = '1';
        selectEl.addEventListener('change', function() {
            var nextId = selectEl.value || '';
            selectEl.dataset.pendingValue = nextId;
            persistCliAgentId(nextId).finally(function() {
                if (selectEl.dataset.pendingValue === nextId) {
                    delete selectEl.dataset.pendingValue;
                }
            });
        });
    }

    var refreshBtn = document.getElementById('settings-cli-refresh-btn');
    if (refreshBtn && !refreshBtn.dataset.bound) {
        refreshBtn.dataset.bound = '1';
        refreshBtn.addEventListener('click', refreshCliAgentsSettings);
    }

    var mdBtn = document.getElementById('settings-cli-generate-md-btn');
    if (mdBtn && !mdBtn.dataset.bound) {
        mdBtn.dataset.bound = '1';
        mdBtn.addEventListener('click', async function() {
            var statusEl = document.getElementById('settings-cli-md-status');
            if (!window.api || !window.api.generateVaultAgentsMd) return;
            mdBtn.disabled = true;
            if (statusEl) {
                statusEl.style.display = 'block';
                statusEl.textContent = window.t('settings.cliGenerateMdRunning');
            }
            try {
                var result = await window.api.generateVaultAgentsMd();
                if (statusEl) {
                    statusEl.textContent = (result && result.success)
                        ? window.t('settings.cliGenerateMdDone', { path: result.path || 'AGENTS.md' })
                        : window.t('settings.cliGenerateMdFailed', {
                            message: (result && result.message) || window.t('common.unknownError')
                        });
                }
            } catch (e) {
                if (statusEl) {
                    statusEl.textContent = window.t('settings.cliGenerateMdFailed', { message: e.message || String(e) });
                }
            } finally {
                mdBtn.disabled = false;
            }
        });
    }
}

function initRagSettings() {
    var ragEl = document.getElementById('settings-assistant-rag-enabled');
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
        document.addEventListener('component_installed', function(e) {
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
        document.addEventListener('rag-index-progress', function(e) {
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
        document.addEventListener('rag_index_built', function(e) {
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

function initIngestAutoSettings() {
    var el = document.getElementById('settings-ingest-auto-enabled');
    if (!el || el.dataset.bound) return;
    el.dataset.bound = '1';
    el.addEventListener('change', function() {
        saveAssistantUiConfig({ ingest_auto_enabled: el.checked });
    });
}

function initMergePresetSettings() {
    var els = document.querySelectorAll('input[name="settings-merge-preset"]');
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

function _mergeThresholdEl(key) {
    return document.getElementById('settings-merge-threshold-' + key);
}

function applyMergeAdvancedToForm(overrides) {
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
    var overrides = {};
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

function initMergeAdvancedSettings() {
    var toggle = document.getElementById('settings-merge-advanced-toggle');
    var panel = document.getElementById('settings-merge-advanced');
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

function initTopicAutoThresholdSettings() {
    var el = document.getElementById('settings-topic-auto-threshold');
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
                updateStatus(window.t('settings.topicThresholdApplied', { count: result.moved_count || 0 }));
                if (typeof window.loadPendingItems === 'function') window.loadPendingItems();
            } else {
                updateStatus((result && result.message) || window.t('pending.operationFailed'));
            }
        } catch (e) {
            updateStatus(e.message || window.t('pending.operationFailed'));
        }
    });
}

function _bindRagAdvancedControls() {
    var denseEl = document.getElementById('settings-rag-dense-weight');
    if (denseEl && !denseEl.dataset.bound) {
        denseEl.dataset.bound = '1';
        denseEl.addEventListener('input', function() {
            _updateDenseWeightHint();
        });
        denseEl.addEventListener('change', saveRagAdvancedConfig);
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
        el.addEventListener('change', saveRagAdvancedConfig);
    });
}

function _estimateIndexTime() {
    var files = (window.AppState && window.AppState.files) ? window.AppState.files.length : 0;
    var seconds = files > 0 ? Math.max(10, files * 0.5) : 60;
    if (seconds < 60) return Math.ceil(seconds) + '秒';
    return Math.ceil(seconds / 60) + '分钟';
}

// ---------------------------------------------------------------------------
// 语义关系工作台（设置页）
// ---------------------------------------------------------------------------

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
    return saveAssistantUiConfig(config).then(function(result) {
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

window.SettingsModule = {
    saveApiConfig,
    loadApiConfigToForm,
    refreshLog,
    closeSettingsPanel,
    closeLogPanel,
    switchSettingsTab,
    autoSaveConfig,
    resetApiConfig,
    saveFontSize,
    saveFontFamily,
    saveTypographySettings,
    applyTypographyToForm,
    loadUiConfigToForm,
    setLocale,
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
    syncCliAgentSelectors: _syncCliAgentSelectors,
    applySemanticSettingsToForm,
    initSemanticWorkbenchSettings,
    saveSemanticWorkbenchConfig,
    // backward-compatible aliases
    initAssistantSettings: initRagSettings,
    applyAssistantSettingsToForm: applyRagSettingsToForm,
};

window.setLocale = setLocale;
window.saveTypographySettings = saveTypographySettings;

window.saveApiConfig = saveApiConfig;
window.refreshLog = refreshLog;
window.closeSettingsPanel = closeSettingsPanel;
window.closeLogPanel = closeLogPanel;
window.resetApiConfig = resetApiConfig;

})();
