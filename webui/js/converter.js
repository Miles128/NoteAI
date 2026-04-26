async function startFileConversion() {
    var btn = document.querySelector('#tab-1 .btn-primary');
    var originalText = btn ? btn.textContent : '开始转换';

    if (btn) {
        btn.disabled = true;
        btn.textContent = '转换中...';
    }

    try {
        var aiToggleEl = document.getElementById('conv-ai-toggle');
        var aiAssist = aiToggleEl ? aiToggleEl.checked : false;

        var result = await window.api.start_file_conversion(aiAssist);

        if (result && result.success) {
            updateStatus('转换完成');
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else {
            updateStatus('转换失败: ' + (result?.message || '未知错误'));
        }
    } catch (e) {
        console.error('[Converter] Conversion error:', e);
        alert('转换失败: ' + e.message);
        updateStatus('转换失败: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

function saveConverterConfig() {
    var formatSelect = document.getElementById('conv-target-format');
    var aiToggle = document.getElementById('conv-ai-toggle');

    var config = {
        targetFormat: formatSelect ? formatSelect.value : 'markdown',
        convAiAssist: aiToggle ? aiToggle.checked : false
    };

    localStorage.setItem('converter-config', JSON.stringify(config));
}

function loadSavedConvConfig() {
    try {
        var saved = localStorage.getItem('converter-config');
        if (saved) {
            var config = JSON.parse(saved);
            var formatSelect = document.getElementById('conv-target-format');
            var aiToggle = document.getElementById('conv-ai-toggle');

            if (formatSelect && config.targetFormat) {
                formatSelect.value = config.targetFormat;
            }
            if (aiToggle && config.convAiAssist !== undefined) {
                aiToggle.checked = config.convAiAssist;
            }

            if (window.TreeModule) {
                if (window.TreeModule.updateConvAIStatus) {
                    window.TreeModule.updateConvAIStatus();
                }
            }
        }
    } catch (e) {
        console.warn('[Converter] Failed to load config:', e);
    }
}

window.ConverterModule = {
    startFileConversion: startFileConversion,
    saveConverterConfig: saveConverterConfig,
    loadSavedConvConfig: loadSavedConvConfig
};
