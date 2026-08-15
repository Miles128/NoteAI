window.EventListeners = (function() { 'use strict';

var _workspaceWatcherUnlisten = null;
var _workspaceWatcherDebounce = null;
var _hasRunInitialIngest = false;

function initWorkspaceFileWatcher() {
    var eventAPI = typeof window.getTauriEventAPI === 'function' ? window.getTauriEventAPI() : null;
    if (!eventAPI || typeof eventAPI.listen !== 'function') return;

    if (_workspaceWatcherUnlisten) {
        _workspaceWatcherUnlisten();
    }

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data || !data.type) return;

        if (data.type === 'auto_topic_assigned') {
            window.updateStatus('✓ ' + (data.topic ? window.t('app.autoAssignedTo', { topic: data.topic }) : window.t('app.autoAssignedTopic')));
            if (typeof window.refreshPendingBtnState === 'function') refreshPendingBtnState();
            if (window._pendingViewVisible && typeof window.loadPendingItems === 'function') loadPendingItems();
            refreshWorkspaceViewsAfterChange();
            return;
        }

        if (data.type === 'auto_file_moved') {
            if (typeof window.refreshPendingBtnState === 'function') refreshPendingBtnState();
            refreshWorkspaceViewsAfterChange();
            return;
        }

        if (data.type !== 'workspace_files_changed') return;

        if (_workspaceWatcherDebounce) {
            clearTimeout(_workspaceWatcherDebounce);
        }
        _workspaceWatcherDebounce = setTimeout(function() {
            _workspaceWatcherDebounce = null;
            refreshWorkspaceViewsAfterChange();
        }, 3000);
    }).then(function(unlisten) {
        _workspaceWatcherUnlisten = unlisten;
    });
}

function markInitialIngestDone() {
    _hasRunInitialIngest = true;
}

var _treeRefreshDirty = false;

function markSidebarTreeDirty() {
    _treeRefreshDirty = true;
}

function consumeSidebarTreeDirty() {
    var dirty = _treeRefreshDirty;
    _treeRefreshDirty = false;
    return dirty;
}

function getActiveSidebarView() {
    var activeView = document.querySelector('.sidebar-view-btn.active');
    return activeView ? activeView.getAttribute('data-sidebar') : null;
}

function refreshWorkspaceViewsAfterChange() {
    var treeLoad = null;
    if (getActiveSidebarView() === 'tree') {
        treeLoad = window.TreeModule && window.TreeModule.loadFileTree ? window.TreeModule.loadFileTree(true) : null;
    } else {
        // 树视图不可见：标记 dirty，切回 tree 视图时由 switchSidebarView 补刷，
        // 避免每次文件变化都在隐藏容器上全量重建
        markSidebarTreeDirty();
    }

    if (typeof window.loadTopicTree === 'function') {
        window.loadTopicTree(true, true);
    }
    refreshCurrentSidebarView(true);
    refreshKnowledgeGraph();

    if (typeof window.updateHomeStats === 'function') {
        if (treeLoad) {
            Promise.resolve(treeLoad)
                .then(function() { window.updateHomeStats(); })
                .catch(function(e) { console.warn('[App] file tree refresh after workspace change failed:', e); });
        } else {
            window.updateHomeStats();
        }
    }
}

function refreshCurrentSidebarView(forceRefresh) {
    var activeView = document.querySelector('.sidebar-view-btn.active');
    if (!activeView) {
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree(!!forceRefresh);
        }
        return;
    }

    var view = activeView.getAttribute('data-sidebar');
    if (view === 'tree') {
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree(!!forceRefresh);
        }
    } else if (view === 'tags') {
        if (typeof window.loadTagsView === 'function') {
            window.loadTagsView(true);
        }
    } else if (view === 'graph') {
        if (window.Graph3Tier && typeof window.Graph3Tier.load === 'function') {
            window.Graph3Tier.load('all');
        }
    } else if (view === 'relation') {
        if (typeof window.loadRelationGraphData === 'function') {
            window.loadRelationGraphData();
        }
    }
}

function refreshKnowledgeGraph() {
    if (window.Graph3Tier && typeof window.Graph3Tier.load === 'function') {
        window.Graph3Tier.load(null, false);
    }
}

function initSidecarErrorListener() {
    var eventAPI = typeof window.getTauriEventAPI === 'function' ? window.getTauriEventAPI() : null;
    if (!eventAPI || typeof eventAPI.listen !== 'function') return;

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data) return;
        if (data.type === 'sidecar_died') {
            var diedMsg = data.message || window.t('app.backendExited');
            console.error('[App] Sidecar died:', diedMsg);
            window.updateStatus(diedMsg);
        } else if (data.type === 'sidecar_ready') {
            window.updateStatus(data.message || window.t('app.backendRecovered'));
        } else if (data.type === 'sidecar_error') {
            var msg = data.message || window.t('app.backendStartFailed');
            console.error('[App] Sidecar error:', msg);
            window.updateStatus(window.t('app.errorPrefix') + msg);
            alert(window.t('app.startFailedAlert', { message: msg }));
        } else if (data.type === 'auto_convert_complete') {
            var info = data.data || {};
            if (info.converted > 0) {
                window.updateStatus(window.t('app.autoConvertDone', { done: info.converted, total: info.total }));
                refreshWorkspaceViewsAfterChange();
            }
        } else if (data.type === 'auto_convert_error') {
            console.error('[App] Auto convert error:', data.error);
        }
    });
}

function initRagEventListener() {
    var eventAPI = typeof window.getTauriEventAPI === 'function' ? window.getTauriEventAPI() : null;
    if (!eventAPI || typeof eventAPI.listen !== 'function') return;

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data) return;
        if (data.type === 'progress' && data.element_id === 'rag-index') {
            var pct = Math.round((data.progress || 0) * 100);
            var msg = data.message || window.t('app.indexBuilding');
            window.updateStatus(pct > 0 ? msg + ' (' + pct + '%)' : msg);
        } else if (data.type === 'job_update') {
            document.dispatchEvent(new CustomEvent('job_update', { detail: data.job || data }));
        } else if (data.type === 'progress' && data.element_id === 'survey_check') {
            window.updateStatus(data.message || window.t('app.checkingSurveys'));
        } else if (data.type === 'progress' && data.element_id === 'component-install') {
            var compMsg = document.getElementById('settings-component-rag-msg');
            if (compMsg) {
                compMsg.style.display = 'block';
                compMsg.textContent = (data.message || window.t('settings.componentInstalling'))
                    + (data.progress ? ' (' + Math.round(data.progress) + '%)' : '');
            }
        } else if (data.type === 'component_installed') {
            var compEvent = new CustomEvent('component_installed', { detail: data });
            document.dispatchEvent(compEvent);
        } else if (data.type === 'rag_chat_chunk' || data.type === 'rag_chat_done'
            || data.type === 'rag_retrieval'
            || data.type === 'rag_error' || data.type === 'rag_index_built') {
            if (window.AssistantModule && window.AssistantModule.handleEvent) {
                window.AssistantModule.handleEvent(data);
            }
            var assistantEvent = new CustomEvent(data.type, { detail: data.data || data });
            document.dispatchEvent(assistantEvent);
            if (data.type === 'rag_index_built') {
                var indexPayload = data.data || data;
                if (indexPayload.success) {
                    window.updateStatus('RAG Ready');
                } else {
                    window.updateStatus(window.t('app.ragIndexFailed'));
                }
            }
        } else if (data.type === 'progress' && data.element_id === 'rag-index-progress') {
            var progressEvent = new CustomEvent('rag-index-progress', {
                detail: { percent: data.progress || 0, message: data.message || '' }
            });
            document.dispatchEvent(progressEvent);
        } else if (
            data.type === 'ingest_progress'
            || data.type === 'ingest_complete'
            || data.type === 'ingest_cascade_started'
            || data.type === 'ingest_cascade_complete'
        ) {
            if (window.IngestModule && window.IngestModule.handleEvent) {
                window.IngestModule.handleEvent(data);
            }
        } else if (data.type === 'cascade_survey_chunk') {
            window.updateStatus(window.t('app.updatingSurvey', { topic: data.topic || '' }));
        } else if (data.type === 'cascade_done') {
            var d = data.data || {};
            if (d.success) {
                var msg = d.is_new_topic ? window.t('app.surveyNewTopic') : window.t('app.surveyUpdated');
                window.updateStatus(msg + ': ' + (data.topic || ''));
            } else {
                window.updateStatus(window.t('app.cascadeFailed', { topic: data.topic || '' }));
            }
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else if (data.type === 'batch_assign_progress') {
            if (data.message) {
                window.updateStatus(data.message);
            }
            if (data.message && data.message.startsWith('完成')) {
                if (window.TreeModule && window.TreeModule.loadFileTree) {
                    window.TreeModule.loadFileTree();
                }
            }
        } else if (data.type && data.type.indexOf('cli_agent_') === 0) {
            if (window.CliAgentModule && window.CliAgentModule.handleEvent) {
                window.CliAgentModule.handleEvent(data);
            }
        }
    });
}

return {
    initWorkspaceFileWatcher: initWorkspaceFileWatcher,
    initSidecarErrorListener: initSidecarErrorListener,
    initRagEventListener: initRagEventListener,
    refreshWorkspaceViewsAfterChange: refreshWorkspaceViewsAfterChange,
    refreshCurrentSidebarView: refreshCurrentSidebarView,
    refreshKnowledgeGraph: refreshKnowledgeGraph,
    markInitialIngestDone: markInitialIngestDone,
    markSidebarTreeDirty: markSidebarTreeDirty,
    consumeSidebarTreeDirty: consumeSidebarTreeDirty
};

})();
