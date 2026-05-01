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
        max_context_tokens: maxContextEl ? parseInt(maxContextEl.value) : 128000
    };

    const statusEl = document.getElementById('api-config-status');
    const popupStatusEl = document.getElementById('api-config-status-popup');

    const showStatus = (msg, isError = false) => {
        const displayMsg = isError ? `<span style="color: #e53e3e;">${msg}</span>` : `<span style="color: #38a169;">${msg}</span>`;
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
        const result = await window.api.save_api_config(config);
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
        const apiConfig = await window.api.get_api_config();
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
        }
    } catch (e) {
        console.error('[Settings] Load API config error:', e);
    }
}

async function refreshLog() {
    try {
        const result = await window.api.refresh_log();
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

function closeAboutPanel() {
    const aboutPanel = document.getElementById('about-panel');
    if (aboutPanel) {
        aboutPanel.classList.remove('active');
    }
}

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

        const result = await window.api.save_ui_config(uiConfig);
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

window.SettingsModule = {
    saveApiConfig,
    loadApiConfigToForm,
    refreshLog,
    closeSettingsPanel,
    closeLogPanel,
    closeAboutPanel,
    autoSaveConfig,
    resetApiConfig
};
