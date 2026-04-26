async function startFileConversion() {
    const btn = document.querySelector('#tab-1 .btn-primary');
    const originalText = btn ? btn.textContent : '开始转换';
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = '转换中...';
    }

    try {
        const fileListEl = document.getElementById('file-list');
        const formatSelectEl = document.getElementById('conv-target-format');
        const aiToggleEl = document.getElementById('conv-ai-toggle');

        const files = [];
        if (fileListEl && fileListEl.options) {
            for (let i = 0; i < fileListEl.options.length; i++) {
                files.push(fileListEl.options[i].value);
            }
        }
        
        const targetFormat = formatSelectEl ? formatSelectEl.value : 'markdown';
        const aiAssist = aiToggleEl ? aiToggleEl.checked : false;

        if (files.length === 0) {
            alert('请选择要转换的文件');
            return;
        }

        const result = await window.api.start_file_conversion(files, targetFormat, aiAssist);
        
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

function autoSaveConvConfig() {
    const formatSelect = document.getElementById('conv-target-format');
    const aiToggle = document.getElementById('conv-ai-toggle');
    
    const config = {
        targetFormat: formatSelect ? formatSelect.value : 'markdown',
        convAiAssist: aiToggle ? aiToggle.checked : false
    };
    
    localStorage.setItem('converter-config', JSON.stringify(config));
}

function loadSavedConvConfig() {
    try {
        const saved = localStorage.getItem('converter-config');
        if (saved) {
            const config = JSON.parse(saved);
            const formatSelect = document.getElementById('conv-target-format');
            const aiToggle = document.getElementById('conv-ai-toggle');
            
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
    startFileConversion,
    autoSaveConvConfig,
    loadSavedConvConfig
};
