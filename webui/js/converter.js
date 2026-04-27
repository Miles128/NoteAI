var _fileConversionUnlisten = null;

async function startFileConversion() {
    const btn = document.querySelector('#tab-1 .btn-primary');
    const originalText = btn ? btn.textContent : '开始转换';
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = '转换中...';
    }

    try {
        const aiToggleEl = document.getElementById('conv-ai-toggle');
        const aiAssist = aiToggleEl ? aiToggleEl.checked : false;

        updateStatus('正在转换...');
        updateProgress('conv-progress', 0, '正在准备转换...');

        if (window.__TAURI_INTERNALS__) {
            var listen = window.__TAURI_INTERNALS__.event?.listen;
            if (listen) {
                if (_fileConversionUnlisten) {
                    _fileConversionUnlisten();
                }
                _fileConversionUnlisten = await listen('python-event', function(event) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'file_conversion_complete') {
                        updateProgress('conv-progress', 1, '转换完成');
                        updateStatus('转换完成');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = originalText;
                        }
                        if (window.TreeModule && window.TreeModule.loadFileTree) {
                            window.TreeModule.loadFileTree();
                        }
                        if (_fileConversionUnlisten) {
                            _fileConversionUnlisten();
                            _fileConversionUnlisten = null;
                        }
                    } else if (data.type === 'file_conversion_error') {
                        updateProgress('conv-progress', 0, '转换失败：' + (data.error || '未知错误'));
                        updateStatus('转换失败：' + (data.error || '未知错误'));
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = originalText;
                        }
                        if (_fileConversionUnlisten) {
                            _fileConversionUnlisten();
                            _fileConversionUnlisten = null;
                        }
                    }
                });
            }
        }

        const result = await window.api.start_file_conversion(aiAssist);
        
        if (result && result.success) {
            updateStatus('正在转换，请稍候...');
        } else {
            updateStatus('转换失败: ' + (result?.message || '未知错误'));
            updateProgress('conv-progress', 0, '转换失败: ' + (result?.message || '未知错误'));
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error('[Converter] Conversion error:', e);
        updateStatus('转换失败: ' + e.message);
        updateProgress('conv-progress', 0, '转换失败: ' + e.message);
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
