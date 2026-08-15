(function() { 'use strict';

var _fileConversionUnlisten: any = null;

async function startFileConversion() {
    const btn = document.querySelector('#tab-1 .btn-primary') as HTMLButtonElement | null;
    const originalText = btn ? btn.textContent : window.t('converter.auto.converter_auto_converter_auto_开始转换');
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('converter.auto.converter_auto_converter_auto_转换中');
    }

    try {
        const aiToggleEl = document.getElementById('conv-ai-toggle') as HTMLInputElement | null;
        const aiAssist = aiToggleEl ? aiToggleEl.checked : false;

        window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_正在转换'));
        window.updateProgress('conv-progress', 0, '正在准备转换...');

        if (typeof window.getTauriEventAPI === 'function') {
            var eventAPI = window.getTauriEventAPI();
            if (eventAPI) {
                if (_fileConversionUnlisten) {
                    _fileConversionUnlisten();
                }
                _fileConversionUnlisten = await eventAPI.listen('python-event', function(event: any) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'progress' && data.element_id === 'conv-progress') {
                        window.updateProgress('conv-progress', data.progress || 0, data.message || '');
                        window.updateStatus(data.message || window.t('converter.auto.converter_auto_converter_auto_转换中'));
                    } else if (data.type === 'file_conversion_complete') {
                        window.updateProgress('conv-progress', 1, '转换完成');
                        window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_转换完成'));
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
                        window.updateProgress('conv-progress', 0, '转换失败：' + (data.error || '未知错误'));
                        window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_转换失败') + (data.error || window.t('common.unknownError')));
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

        const result = await window.api.startFileConversion(aiAssist);
        
        if (result && result.success) {
            window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_正在转换_请稍候'));
        } else {
            window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_转换失败_2') + (result?.message || window.t('common.unknownError')));
            window.updateProgress('conv-progress', 0, '转换失败: ' + (result?.message || '未知错误'));
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error('[Converter] Conversion error:', e);
        window.updateStatus(window.t('converter.auto.converter_auto_converter_auto_转换失败_2') + (e as Error).message);
        window.updateProgress('conv-progress', 0, '转换失败: ' + (e as Error).message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

function autoSaveConvConfig() {
    const formatSelect = document.getElementById('conv-target-format') as HTMLSelectElement | null;
    const aiToggle = document.getElementById('conv-ai-toggle') as HTMLInputElement | null;
    
    const config = {
        targetFormat: formatSelect ? formatSelect.value : 'markdown',
        convAiAssist: aiToggle ? aiToggle.checked : false
    };
    
    window.Storage.setItem(window.Storage.KEYS.CONVERTER_CONFIG, config);
}

function loadSavedConvConfig() {
    const config: any = window.Storage.getItem(window.Storage.KEYS.CONVERTER_CONFIG, null);
    if (config) {
        const formatSelect = document.getElementById('conv-target-format') as HTMLSelectElement | null;
        const aiToggle = document.getElementById('conv-ai-toggle') as HTMLInputElement | null;
        
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
}

window.ConverterModule = {
    startFileConversion,
    autoSaveConvConfig,
    loadSavedConvConfig
};

window.startFileConversion = startFileConversion;

})();

