var _topicsReady = false;

function updateIntegrateBtnState() {
    var btn = document.getElementById('integrate-btn');
    var hint = document.getElementById('integration-hint');
    var topicList = document.getElementById('topic-list');
    var hasTopics = topicList && topicList.value.trim().length > 0;

    if (!btn) return;
    btn.disabled = !(_topicsReady && hasTopics);

    if (hint) {
        hint.textContent = (_topicsReady && hasTopics) ? '' : '请先点击提取主题按钮';
    }
}

async function extractTopics() {
    var btn = document.getElementById('extract-topics-btn');
    var progressFill = document.getElementById('integration-progress-fill');
    var progressText = document.getElementById('integration-status');

    if (!btn) return;

    btn.disabled = true;
    btn.textContent = '提取中...';
    if (progressFill) progressFill.style.width = '5%';
    if (progressText) progressText.textContent = '正在扫描文件...';
    updateStatus('正在提取主题...');

    try {
        if (progressFill) progressFill.style.width = '15%';
        if (progressText) progressText.textContent = '正在读取文件列表...';

        var topicCountInput = document.getElementById('topic-count');
        var topicCount = null;
        if (topicCountInput && topicCountInput.value.trim() !== '') {
            var count = parseInt(topicCountInput.value.trim());
            if (!isNaN(count) && count >= 2) {
                topicCount = count;
            }
        }

        var result = await window.api.extract_topics(topicCount);

        if (result && result.success) {
            if (progressFill) progressFill.style.width = '90%';
            if (progressText) progressText.textContent = '正在写入主题列表...';

            var topicList = document.getElementById('topic-list');
            if (topicList) {
                topicList.value = '';

                for (var i = 0; i < result.topics.length; i++) {
                    var topic = result.topics[i];
                    if (topicList.value.length > 0) {
                        topicList.value += '\n';
                    }
                    topicList.value += topic;
                    topicList.scrollTop = topicList.scrollHeight;

                    var progressPercent = 0.9 + (0.1 * (i + 1) / result.topics.length);
                    if (progressFill) progressFill.style.width = (progressPercent * 100) + '%';
                    if (progressText) progressText.textContent = '显示主题 ' + (i + 1) + '/' + result.topics.length + ': ' + topic;
                    updateStatus('显示主题 ' + (i + 1) + '/' + result.topics.length + ': ' + topic);

                    await new Promise(function(resolve) { setTimeout(resolve, 200); });
                }
            }

            _topicsReady = true;
            updateIntegrateBtnState();

            if (progressFill) progressFill.style.width = '100%';
            if (progressText) progressText.textContent = '提取完成，共 ' + result.topics.length + ' 个主题';
            updateStatus('主题提取完成，共 ' + result.topics.length + ' 个主题');
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
    if (!_topicsReady) {
        updateIntegrateBtnState();
        return;
    }

    var btn = document.getElementById('integrate-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '整合中...';
    }

    try {
        var topicList = document.getElementById('topic-list');
        var topics = topicList ? topicList.value.split('\n').map(function(t) { return t.trim(); }).filter(function(t) { return t; }) : [];

        var result = await window.api.start_note_integration(false, topics);

        if (result && result.success) {
            updateStatus('整合完成');
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else {
            updateStatus('整合失败: ' + (result?.message || '未知错误'));
            alert('整合失败: ' + (result?.message || '未知错误'));
        }
    } catch (e) {
        console.error('[Integrator] Integration error:', e);
        alert('整合失败: ' + e.message);
        updateStatus('整合失败: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '开始整合';
        }
    }
}

function clearTopicList() {
    var topicList = document.getElementById('topic-list');
    if (topicList) {
        topicList.value = '';
    }
    _topicsReady = false;
    updateIntegrateBtnState();
}

window.IntegratorModule = {
    get topicsReady() { return _topicsReady; },
    set topicsReady(v) { _topicsReady = v; },
    updateIntegrateBtnState: updateIntegrateBtnState,
    extractTopics: extractTopics,
    startNoteIntegration: startNoteIntegration,
    clearTopicList: clearTopicList
};
