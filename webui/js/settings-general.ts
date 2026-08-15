// ============================================================================
// settings-general.js —— 设置面板「通用」子模块
// 职责：API 配置、面板开关、日志刷新、排版/字体/语言、通用 UI 配置回填、
//       备份与恢复 / 索引健康（本地可靠性）。
// 对外：window.SettingsGeneral（供薄主入口 settings.js 组装 SettingsModule）。
// 依赖：window.api / window.t / window.ThemeModule / window.I18nModule /
//       window.ToastModule / window.updateStatus(toast.js) /
//       window.SettingsComponents、window.SettingsSemantic（loadUiConfigToForm 回填时调用）。
// ============================================================================
(function() { 'use strict';

async function saveApiConfig() {
    const apiKeyEl = document.getElementById('api-key') as HTMLInputElement | null;
    const apiBaseEl = document.getElementById('api-base') as HTMLInputElement | null;
    const modelNameEl = document.getElementById('model-name') as HTMLInputElement | null;
    const temperatureEl = document.getElementById('temperature') as HTMLInputElement | null;
    const maxTokensEl = document.getElementById('max-tokens') as HTMLInputElement | null;
    const maxContextEl = document.getElementById('max-context') as HTMLInputElement | null;
    const disableThinkingEl = document.getElementById('disable-thinking') as HTMLInputElement | null;

    const config = {
        api_key: apiKeyEl ? apiKeyEl.value : '',
        api_base: apiBaseEl ? apiBaseEl.value : 'https://api.openai.com/v1',
        model_name: modelNameEl ? modelNameEl.value : 'gpt-4',
        temperature: temperatureEl ? parseFloat(temperatureEl.value) : 0.7,
        max_tokens: maxTokensEl ? parseInt(maxTokensEl.value) : 32000,
        max_context_tokens: maxContextEl ? parseInt(maxContextEl.value) : 128000,
        disable_thinking: disableThinkingEl ? disableThinkingEl.checked : true
    };

    const statusEl = document.getElementById('api-config-status');
    const popupStatusEl = document.getElementById('api-config-status-popup');

    const showStatus = (msg: any, isError = false) => {
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
        showStatus(window.t('settings.saveFailed') + ': ' + (e as Error).message, true);
    }
}

async function loadApiConfigToForm() {
    try {
        const apiConfig = await window.api.getApiConfig();
        if (apiConfig) {
            const apiKeyEl = document.getElementById('api-key') as HTMLInputElement | null;
            const apiBaseEl = document.getElementById('api-base') as HTMLInputElement | null;
            const modelNameEl = document.getElementById('model-name') as HTMLInputElement | null;
            const tempEl = document.getElementById('temperature') as HTMLInputElement | null;
            const maxTokensEl = document.getElementById('max-tokens') as HTMLInputElement | null;
            const maxContextEl = document.getElementById('max-context') as HTMLInputElement | null;

            if (apiKeyEl) apiKeyEl.value = apiConfig.api_key || '';
            if (apiBaseEl) apiBaseEl.value = apiConfig.api_base || 'https://api.openai.com/v1';
            if (modelNameEl) modelNameEl.value = apiConfig.model_name || 'gpt-4';
            if (tempEl) tempEl.value = apiConfig.temperature || 0.7;
            if (maxTokensEl) maxTokensEl.value = apiConfig.max_tokens || 32000;
            if (maxContextEl) maxContextEl.value = apiConfig.max_context_tokens || 128000;

            var disableThinkingEl = document.getElementById('disable-thinking') as HTMLInputElement | null;
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
            window.updateStatus(window.t('settings.logRefreshed'));
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

async function autoSaveConfig() {
    try {
        const uiConfig = {
            web_ai_assist: (document.getElementById('web-ai-toggle') as HTMLInputElement | null)?.checked || false,
            web_include_images: (document.getElementById('web-include-images') as HTMLInputElement | null)?.checked || false,
            conv_ai_assist: (document.getElementById('conv-ai-toggle') as HTMLInputElement | null)?.checked || false,
            auto_topic: true,
            topic_list: (document.getElementById('topic-list') as HTMLInputElement | null)?.value || ''
        };

        const result = await window.api.saveUiConfig(uiConfig);
        if (result && result.success) {
            window.updateStatus(window.t('settings.autoSaved'));
        } else {
            window.updateStatus(window.t('settings.autoSaveFailed', { message: result?.message || window.t('common.unknownError') }));
        }
    } catch (e) {
        console.error('[Settings] Auto save config error:', e);
    }
}

function resetApiConfig() {
    const apiBaseEl = document.getElementById('api-base') as HTMLInputElement | null;
    const modelNameEl = document.getElementById('model-name') as HTMLInputElement | null;
    const tempEl = document.getElementById('temperature') as HTMLInputElement | null;
    const maxTokensEl = document.getElementById('max-tokens') as HTMLInputElement | null;
    const maxContextEl = document.getElementById('max-context') as HTMLInputElement | null;

    if (apiBaseEl) apiBaseEl.value = 'https://api.openai.com/v1';
    if (modelNameEl) modelNameEl.value = 'gpt-4';
    if (tempEl) tempEl.value = String(0.7);
    if (maxTokensEl) maxTokensEl.value = String(32000);
    if (maxContextEl) maxContextEl.value = String(128000);
}

async function saveFontSize(size: any) {
    try {
        var result = await window.api.saveUiConfig({ font_size: size });
        if (!result || !result.success) {
            console.error('[Settings] save font_size failed:', result);
        }
    } catch (e) {
        console.error('[Settings] save font_size error:', e);
    }
}

async function saveFontFamily(key: any, value: any) {
    try {
        var payload: Record<string, any> = {};
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
    var next: Record<string, any> = {};
    roles.forEach(function(role: any) {
        var familyEl = document.getElementById('typography-' + role + '-family') as HTMLInputElement | null;
        var styleEl = document.getElementById('typography-' + role + '-style') as HTMLInputElement | null;
        next[role] = {
            family: familyEl ? familyEl.value : 'system',
            style: styleEl ? styleEl.value : 'normal'
        };
    });
    return window.ThemeModule && window.ThemeModule.normalizeTypography
        ? window.ThemeModule.normalizeTypography(next)
        : next;
}

function applyTypographyToForm(typography: any) {
    var normalized = window.ThemeModule && window.ThemeModule.normalizeTypography
        ? window.ThemeModule.normalizeTypography(typography)
        : (typography || {});
    Object.keys(normalized).forEach(function(role: any) {
        var familyEl = document.getElementById('typography-' + role + '-family') as HTMLInputElement | null;
        var styleEl = document.getElementById('typography-' + role + '-style') as HTMLInputElement | null;
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

async function setLocale(locale: any) {
    if (!window.I18nModule || !window.I18nModule.setLocale) return;
    try {
        await window.I18nModule.setLocale(locale);
        if (typeof window.updateSidebarStats === 'function') {
            window.updateSidebarStats();
        }
        if (window.I18nModule.applyDomI18n) {
            window.I18nModule.applyDomI18n(document.getElementById('settings-panel') as ParentNode | undefined);
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
            if (window.ThemeModule) {
                window.ThemeModule.setFontSize(savedFontSize);
            }
            document.querySelectorAll('input[name="font-size"]').forEach(function(radio) {
                (radio as HTMLInputElement).checked = (radio as HTMLInputElement).value === savedFontSize;
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
                (radio as HTMLInputElement).checked = (radio as HTMLInputElement).value === loc;
            });
            var ingestAutoEl = document.getElementById('settings-ingest-auto-enabled') as HTMLInputElement | null;
            if (ingestAutoEl) {
                ingestAutoEl.checked = uiConfig.ingest_auto_enabled !== false;
            }
            var topicThresholdEl = document.getElementById('settings-topic-auto-threshold') as HTMLInputElement | null;
            if (topicThresholdEl) {
                topicThresholdEl.value = uiConfig.topic_auto_assign_threshold != null ? uiConfig.topic_auto_assign_threshold : 0.80;
            }
            var mergePresetEls = document.querySelectorAll('input[name="settings-merge-preset"]');
            if (mergePresetEls.length) {
                var savedPreset = uiConfig.merge_preset || 'balanced';
                mergePresetEls.forEach(function(radio) { (radio as HTMLInputElement).checked = (radio as HTMLInputElement).value === savedPreset; });
            }
            if (window.SettingsComponents) {
                window.SettingsComponents.applyMergeAdvancedToForm(uiConfig.merge_overrides || {});
                window.SettingsComponents.applyRagSettingsToForm(uiConfig);
                window.SettingsComponents.applyCliSettingsToForm(uiConfig);
            }
            window.SettingsSemantic?.applySemanticSettingsToForm?.(uiConfig);
        }
    } catch (e) {
        console.error('[Settings] Load UI config error:', e);
    }
}

// ---------------------------------------------------------------------------
// 备份与恢复 / 索引健康（本地可靠性）
// ---------------------------------------------------------------------------

function showReliabilityStatus(elId: any, msg: any, isError: any) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    el.style.color = isError ? '#e53e3e' : '#38a169';
}

function hideReliabilityStatus(elId: any) {
    const el = document.getElementById(elId);
    if (el) el.style.display = 'none';
}

function formatBytes(bytes: any) {
    if (bytes == null || isNaN(bytes)) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function backupWorkspaceNow() {
    const btn = document.getElementById('settings-backup-btn') as HTMLButtonElement | null;
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
        showReliabilityStatus('settings-backup-status', window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function exportNotesNow() {
    const btn = document.getElementById('settings-export-btn') as HTMLButtonElement | null;
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
        showReliabilityStatus('settings-backup-status', window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function restoreBackupNow() {
    let file = '';
    try {
        file = await window.api.openArchiveDialog();
    } catch (e) {
        showReliabilityStatus('settings-restore-status', window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
        return;
    }
    if (!file) return;
    if (!window.confirm(window.t('settings.reliabilityRestoreConfirm'))) return;
    const btn = document.getElementById('settings-restore-btn') as HTMLButtonElement | null;
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
        showReliabilityStatus('settings-restore-status', window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function healthBadge(ok: any) {
    return ok ? window.escapeHtml(window.t('settings.health.ok')) : window.escapeHtml(window.t('settings.health.bad'));
}

function renderHealthReport(report: any) {
    const el = document.getElementById('settings-health-report');
    if (!el) return;
    const rows = ['rag', 'semantic', 'links', 'fulltext'].map(function(key: any) {
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
    const btn = document.getElementById('settings-health-check-btn') as HTMLButtonElement | null;
    if (btn) btn.disabled = true;
    hideReliabilityStatus('settings-health-status');
    try {
        const result = await window.api.getIndexHealth();
        if (!result || !result.success) throw new Error((result && result.message) || window.t('common.unknownError'));
        renderHealthReport(result);
    } catch (e) {
        const el = document.getElementById('settings-health-report');
        if (el) el.style.display = 'none';
        showReliabilityStatus('settings-health-status', window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function runHealthRecovery(kind: any) {
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
        showReliabilityStatus(statusEl, window.t('settings.reliabilityFailed', { message: (e as Error).message || String(e) }), true);
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

window.SettingsGeneral = {
    saveApiConfig,
    loadApiConfigToForm,
    refreshLog,
    closeSettingsPanel,
    closeLogPanel,
    autoSaveConfig,
    resetApiConfig,
    saveFontSize,
    saveFontFamily,
    saveTypographySettings,
    applyTypographyToForm,
    loadUiConfigToForm,
    setLocale,
    initReliabilitySettings,
} as any;

// 历史全局别名（保持对外行为不变）
window.setLocale = setLocale;
window.saveTypographySettings = saveTypographySettings;
window.saveApiConfig = saveApiConfig;
window.refreshLog = refreshLog;
window.closeSettingsPanel = closeSettingsPanel;
window.closeLogPanel = closeLogPanel;
window.resetApiConfig = resetApiConfig as any;

})();
