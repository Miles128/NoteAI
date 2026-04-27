let topicsReady = false;
var _noteIntegrationUnlisten = null;

function updateIntegrateBtnState() {
    const btn = document.getElementById('integrate-btn');
    const hint = document.getElementById('integration-hint');
    const topicList = document.getElementById('topic-list');
    const hasTopics = topicList && topicList.value.trim().length > 0;
    
    if (!btn) return;
    btn.disabled = !(topicsReady && hasTopics);
    
    if (hint) {
        hint.textContent = (topicsReady && hasTopics) ? '' : '请先点击提取主题按钮';
    }
}

async function extractTopics() {
    const btn = document.getElementById('extract-topics-btn');
    const progressFill = document.getElementById('integration-progress-fill');
    const progressText = document.getElementById('integration-status');
    
    if (!btn) return;

    btn.disabled = true;
    btn.textContent = '提取中...';
    if (progressFill) progressFill.style.width = '5%';
    if (progressText) progressText.textContent = '正在扫描文件...';
    updateStatus('正在提取主题...');

    try {
        if (progressFill) progressFill.style.width = '15%';
        if (progressText) progressText.textContent = '正在读取文件列表...';

        const topicCountInput = document.getElementById('topic-count');
        let topicCount = null;
        if (topicCountInput && topicCountInput.value.trim() !== '') {
            const count = parseInt(topicCountInput.value.trim());
            if (!isNaN(count) && count >= 2) {
                topicCount = count;
            }
        }

        const result = await window.api.extract_topics(topicCount);

        if (result && result.success) {
            if (progressFill) progressFill.style.width = '90%';
            if (progressText) progressText.textContent = '正在写入主题列表...';

            const topicList = document.getElementById('topic-list');
            if (topicList) {
                topicList.value = '';
                
                for (let i = 0; i < result.topics.length; i++) {
                    const topic = result.topics[i];
                    if (topicList.value.length > 0) {
                        topicList.value += '\n';
                    }
                    topicList.value += topic;
                    topicList.scrollTop = topicList.scrollHeight;
                    
                    const progressPercent = 0.9 + (0.1 * (i + 1) / result.topics.length);
                    if (progressFill) progressFill.style.width = (progressPercent * 100) + '%';
                    if (progressText) progressText.textContent = `显示主题 ${i + 1}/${result.topics.length}: ${topic}`;
                    updateStatus(`显示主题 ${i + 1}/${result.topics.length}: ${topic}`);
                    
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }
            
            topicsReady = true;
            updateIntegrateBtnState();

            if (progressFill) progressFill.style.width = '100%';
            if (progressText) progressText.textContent = `提取完成，共 ${result.topics.length} 个主题`;
            updateStatus(`主题提取完成，共 ${result.topics.length} 个主题`);
        } else {
            if (progressFill) progressFill.style.width = '0%';
            if (progressText) progressText.textContent = '提取失败';
            alert('提取主题失败: ' + (result?.error || result?.message || '未知错误'));
        }
    } catch (e) {
        if (progressFill) progressFill.style.width = '0%';
        if (progressText) progressText.textContent = '提取失败';
        console.error('[Integrator] Extract topics error:', e);
        alert('提取主题失败: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '提取主题';
        }
    }
}

async function startNoteIntegration() {
    if (!topicsReady) {
        updateIntegrateBtnState();
        return;
    }

    const btn = document.getElementById('integrate-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '整合中...';
    }
    
    try {
        const topicList = document.getElementById('topic-list');
        const topics = topicList ? topicList.value.split('\n').map(t => t.trim()).filter(t => t) : [];
        
        updateStatus('正在整合...');
        updateProgress('integration-progress', 0, '正在准备整合...');

        if (window.__TAURI_INTERNALS__) {
            var listen = window.__TAURI_INTERNALS__.event?.listen;
            if (listen) {
                if (_noteIntegrationUnlisten) {
                    _noteIntegrationUnlisten();
                }
                _noteIntegrationUnlisten = await listen('python-event', function(event) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'note_integration_complete') {
                        updateProgress('integration-progress', 1, '整合完成');
                        updateStatus('整合完成');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = '开始整合';
                        }
                        if (window.TreeModule && window.TreeModule.loadFileTree) {
                            window.TreeModule.loadFileTree();
                        }
                        if (_noteIntegrationUnlisten) {
                            _noteIntegrationUnlisten();
                            _noteIntegrationUnlisten = null;
                        }
                    } else if (data.type === 'note_integration_error') {
                        updateProgress('integration-progress', 0, '整合失败：' + (data.error || '未知错误'));
                        updateStatus('整合失败：' + (data.error || '未知错误'));
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = '开始整合';
                        }
                        if (_noteIntegrationUnlisten) {
                            _noteIntegrationUnlisten();
                            _noteIntegrationUnlisten = null;
                        }
                    }
                });
            }
        }

        const result = await window.api.start_note_integration(false, topics);
        
        if (result && result.success) {
            updateStatus('正在整合，请稍候...');
        } else {
            updateStatus('整合失败: ' + (result?.message || '未知错误'));
            updateProgress('integration-progress', 0, '整合失败: ' + (result?.message || '未知错误'));
            if (btn) {
                btn.disabled = false;
                btn.textContent = '开始整合';
            }
        }
    } catch (e) {
        console.error('[Integrator] Integration error:', e);
        updateStatus('整合失败: ' + e.message);
        updateProgress('integration-progress', 0, '整合失败: ' + e.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = '开始整合';
        }
    }
}

function clearTopicList() {
    const topicList = document.getElementById('topic-list');
    if (topicList) {
        topicList.value = '';
    }
    topicsReady = false;
    updateIntegrateBtnState();
}

window.IntegratorModule = {
    topicsReady,
    updateIntegrateBtnState,
    extractTopics,
    startNoteIntegration,
    clearTopicList
};
