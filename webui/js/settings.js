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
        const displayMsg = isError ? `<span style="color: #e53e3e;">${escapeHtml(msg)}</span>` : `<span style="color: #38a169;">${escapeHtml(msg)}</span>`;
        if (statusEl) {
            statusEl.innerHTML = displayMsg;
            statusEl.style.display = 'block';
        }
        if (popupStatusEl) {
            popupStatusEl.innerHTML = displayMsg;
            popupStatusEl.style.display = 'block';
        }
    };

    const hideStatus = () => {
        if (statusEl) statusEl.style.display = 'none';
        if (popupStatusEl) popupStatusEl.style.display = 'none';
    };

    showStatus('正在测试连接...');
    try {
        const result = await window.api.saveApiConfig(config);
        if (result && result.success) {
            showStatus('配置已保存');
            setTimeout(hideStatus, 3000);
        } else {
            showStatus(result?.message || '保存失败', true);
        }
    } catch (e) {
        showStatus('保存失败: ' + e.message, true);
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
            updateStatus('日志已刷新');
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
    if (tabName === 'profile') {
        loadUserProfile();
    }
}

document.addEventListener('DOMContentLoaded', function() {
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
});

async function autoSaveConfig() {
    try {
        const uiConfig = {
            web_ai_assist: document.getElementById('web-ai-toggle')?.checked || false,
            web_include_images: document.getElementById('web-include-images')?.checked || false,
            conv_ai_assist: document.getElementById('conv-ai-toggle')?.checked || false,
            web_save_path: document.getElementById('web-save-path')?.value || '',
            conv_save_path: document.getElementById('conv-save-path')?.value || '',
            integration_source_path: document.getElementById('integration-source-path')?.value || '',
            integration_output_path: document.getElementById('integration-output-path')?.value || '',
            auto_topic: true,
            topic_list: document.getElementById('topic-list')?.value || ''
        };

        const result = await window.api.saveUiConfig(uiConfig);
        if (result && result.success) {
            updateStatus('配置已自动保存');
        } else {
            updateStatus('配置保存失败: ' + (result?.message || '未知错误'));
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
        }
    } catch (e) {
        console.error('[Settings] Load UI config error:', e);
    }
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
    saveUserProfile,
    loadUserProfile,
    saveFontSize,
    loadUiConfigToForm
};

async function saveUserProfile() {
    var profileMd = document.getElementById('profile-md')?.value || '';

    var data = {
        profile_md: profileMd,
    };

    var statusEl = document.getElementById('profile-status');
    try {
        var result = await window.api.saveUserProfile(data);
        if (result && result.success) {
            if (statusEl) { statusEl.innerHTML = '<span style="color: #38a169;">画像已保存</span>'; statusEl.style.display = 'block'; }
        } else {
            if (statusEl) { statusEl.innerHTML = '<span style="color: #e53e3e;">保存失败</span>'; statusEl.style.display = 'block'; }
        }
    } catch (e) {
        if (statusEl) { statusEl.innerHTML = '<span style="color: #e53e3e;">' + escapeHtml(e.message) + '</span>'; statusEl.style.display = 'block'; }
    }
    setTimeout(function() { if (statusEl) statusEl.style.display = 'none'; }, 3000);
}

async function loadUserProfile() {
    try {
        var result = await window.api.getUserProfile();
        if (result && result.success && result.profile) {
            var profileMd = result.profile.profile_md || '';

            if (!profileMd) {
                var identity = result.profile.identity || {};
                var prefs = result.profile.preferences || {};
                var lines = [];
                lines.push('## 关于我');
                lines.push('');
                if (identity.profession) lines.push('- 职业：' + identity.profession);
                if (identity.expertise_areas && identity.expertise_areas.length) lines.push('- 专业领域：' + identity.expertise_areas.join(', '));
                if (identity.interests && identity.interests.length) lines.push('- 兴趣：' + identity.interests.join(', '));
                if (identity.learning_goals && identity.learning_goals.length) lines.push('- 学习目标：' + identity.learning_goals.join(', '));
                lines.push('');
                lines.push('## 偏好');
                lines.push('');
                lines.push('- 回答风格：' + (prefs.answer_style === 'detailed' ? '详细' : '简洁'));
                lines.push('- 回答深度：' + (prefs.detail_level === 'general' ? '通俗向' : '技术向'));
                profileMd = lines.join('\n');
            }

            var mdEl = document.getElementById('profile-md');
            if (mdEl) mdEl.value = profileMd;
        }
    } catch (e) {
        console.error('[Settings] Load user profile error:', e);
    }
}

window.saveApiConfig = saveApiConfig;
window.refreshLog = refreshLog;
window.closeSettingsPanel = closeSettingsPanel;
window.closeLogPanel = closeLogPanel;
window.resetApiConfig = resetApiConfig;
window.saveUserProfile = saveUserProfile;

})();

