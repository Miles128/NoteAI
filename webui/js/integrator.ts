(function() { 'use strict';

let topicsReady = false;
var _noteIntegrationUnlisten: any = null;

function updateIntegrateBtnState() {
    const btn = document.getElementById('integrate-btn') as HTMLButtonElement | null;
    const hint = document.getElementById('integration-hint');
    const topicList = document.getElementById('topic-list') as HTMLTextAreaElement | null;
    const hasTopics = topicList && topicList.value.trim().length > 0;
    
    if (!btn) return;
    btn.disabled = !(topicsReady && hasTopics);
    
    if (hint) {
        hint.textContent = (topicsReady && hasTopics) ? '' : window.t('integrator.extractTopicsFirst');
    }
}

async function extractTopics() {
    const btn = document.getElementById('extract-topics-btn') as HTMLButtonElement | null;
    const progressFill = document.getElementById('integration-progress-fill');
    const progressText = document.getElementById('integration-status');
    
    if (!btn) return;

    btn.disabled = true;
    btn.textContent = window.t('integrator.extracting');
    if (progressFill) progressFill.style.width = '5%';
    if (progressText) progressText.textContent = window.t('integrator.scanningFiles');
    window.updateStatus(window.t('integrator.extractingTopics'));

    try {
        if (progressFill) progressFill.style.width = '15%';
        if (progressText) progressText.textContent = window.t('integrator.readingFileList');

        const topicCountInput = document.getElementById('topic-count') as HTMLInputElement | null;
        let topicCount: any = null;
        if (topicCountInput && topicCountInput.value.trim() !== '') {
            const count = parseInt(topicCountInput.value.trim());
            if (!isNaN(count) && count >= 2) {
                topicCount = count;
            }
        }

        const result = await window.api.extractTopics(topicCount as any);

        if (result && result.success) {
            if (progressFill) progressFill.style.width = '90%';
            if (progressText) progressText.textContent = window.t('integrator.writingTopics');

            const topicList = document.getElementById('topic-list') as HTMLTextAreaElement | null;
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
                    if (progressText) progressText.textContent = window.t('integrator.showTopic', { current: i + 1, total: result.topics.length, topic: topic });
                    window.updateStatus(window.t('integrator.showTopic', { current: i + 1, total: result.topics.length, topic: topic }));
                    
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }
            
            topicsReady = true;
            updateIntegrateBtnState();

            if (progressFill) progressFill.style.width = '100%';
            if (progressText) progressText.textContent = window.t('integrator.extractDone', { count: result.topics.length });
            window.updateStatus(window.t('integrator.extractDone', { count: result.topics.length }));
        } else {
            if (progressFill) progressFill.style.width = '0%';
            if (progressText) progressText.textContent = window.t('integrator.extractFailed');
            alert(window.t('integrator.extractTopicsFailed') + (result?.error || result?.message || window.t('common.unknownError')));
        }
    } catch (e) {
        if (progressFill) progressFill.style.width = '0%';
        if (progressText) progressText.textContent = window.t('integrator.extractFailed');
        console.error('[Integrator] Extract topics error:', e);
        alert(window.t('integrator.extractTopicsFailed') + (e as Error).message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = window.t('integrator.extractTopics');
        }
    }
}

async function startNoteIntegration() {
    if (!topicsReady) {
        updateIntegrateBtnState();
        return;
    }

    const btn = document.getElementById('integrate-btn') as HTMLButtonElement | null;
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('integrator.integrating');
    }
    
    try {
        const topicList = document.getElementById('topic-list') as HTMLTextAreaElement | null;
        const topics = topicList ? topicList.value.split('\n').map((t: any) => t.trim()).filter((t: any) => t) : [];
        
        window.updateStatus(window.t('integrator.integratingStatus'));
        window.updateProgress('integration-progress', 0, window.t('integrator.preparing'));

        if (typeof window.getTauriEventAPI === 'function') {
            var eventAPI = window.getTauriEventAPI();
            if (eventAPI) {
                if (_noteIntegrationUnlisten) {
                    _noteIntegrationUnlisten();
                }
                _noteIntegrationUnlisten = await eventAPI.listen('python-event', function(event: any) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'progress' && data.element_id === 'integration-progress') {
                        window.updateProgress('integration-progress', data.progress || 0, data.message || '');
                        window.updateStatus(data.message || window.t('integrator.integrating'));
                    } else if (data.type === 'note_integration_complete') {
                        window.updateProgress('integration-progress', 1, window.t('integrator.integrateDone'));
                        window.updateStatus(window.t('integrator.integrateDone'));
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = window.t('integrator.start');
                        }
                        if (window.TreeModule && window.TreeModule.loadFileTree) {
                            window.TreeModule.loadFileTree();
                        }
                        if (_noteIntegrationUnlisten) {
                            _noteIntegrationUnlisten();
                            _noteIntegrationUnlisten = null;
                        }
                    } else if (data.type === 'note_integration_error') {
                        window.updateProgress('integration-progress', 0, window.t('integrator.integrateFailed', { message: data.error || window.t('common.unknownError') }));
                        window.updateStatus(window.t('integrator.integrateFailedShort') + (data.error || window.t('common.unknownError')));
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = window.t('integrator.start');
                        }
                        if (_noteIntegrationUnlisten) {
                            _noteIntegrationUnlisten();
                            _noteIntegrationUnlisten = null;
                        }
                    }
                });
            }
        }

        const result = await window.api.startNoteIntegration(false, topics);
        
        if (result && result.success) {
            window.updateStatus(window.t('integrator.integratingWait'));
        } else {
            window.updateStatus(window.t('integrator.integrateFailedShort') + (result?.message || window.t('common.unknownError')));
            window.updateProgress('integration-progress', 0, window.t('integrator.integrateFailed', { message: result?.message || window.t('common.unknownError') }));
            if (btn) {
                btn.disabled = false;
                btn.textContent = window.t('integrator.start');
            }
        }
    } catch (e) {
        console.error('[Integrator] Integration error:', e);
        window.updateStatus(window.t('integrator.integrateFailedShort') + (e as Error).message);
        window.updateProgress('integration-progress', 0, window.t('integrator.integrateFailed', { message: (e as Error).message }));
        if (btn) {
            btn.disabled = false;
            btn.textContent = window.t('integrator.start');
        }
    }
}

function clearTopicList() {
    const topicList = document.getElementById('topic-list') as HTMLTextAreaElement | null;
    if (topicList) {
        topicList.value = '';
    }
    topicsReady = false;
    updateIntegrateBtnState();
}

window.updateIntegrateBtnState = updateIntegrateBtnState;

window.IntegratorModule = {
    get topicsReady() { return topicsReady; },
    set topicsReady(v) { topicsReady = v; },
    updateIntegrateBtnState,
    extractTopics,
    startNoteIntegration,
    clearTopicList
};

window.extractTopics = extractTopics;
window.startNoteIntegration = startNoteIntegration;

})();

