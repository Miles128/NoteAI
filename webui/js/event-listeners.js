window.EventListeners = (function() { 'use strict';

var _workspaceWatcherUnlisten = null;
var _workspaceWatcherDebounce = null;
var _hasRunInitialIngest = false;

function initWorkspaceFileWatcher() {
    var eventAPI = window.__TAURI__ && window.__TAURI__.event && window.__TAURI__.event.listen
        ? window.__TAURI__.event
        : (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && window.__TAURI_INTERNALS__.event.listen
            ? window.__TAURI_INTERNALS__.event
            : null);
    if (!eventAPI) return;

    if (_workspaceWatcherUnlisten) {
        _workspaceWatcherUnlisten();
    }

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data || !data.type) return;

        if (data.type === 'auto_topic_assigned') {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus('✓ ' + (data.topic ? window.t('app.autoAssignedTo', { topic: data.topic }) : window.t('app.autoAssignedTopic')));
            }
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

function refreshWorkspaceViewsAfterChange() {
    var treeLoad = null;
    if (window.TreeModule && window.TreeModule.loadFileTree) {
        treeLoad = window.TreeModule.loadFileTree(true);
    }

    if (typeof window.loadTopicTree === 'function') {
        window.loadTopicTree(true, true);
    }
    refreshCurrentSidebarView(true);
    refreshKnowledgeGraph();

    if (treeLoad && typeof window.updateHomeStats === 'function') {
        Promise.resolve(treeLoad)
            .then(function() { window.updateHomeStats(); })
            .catch(function(e) { console.warn('[App] file tree refresh after workspace change failed:', e); });
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
        if (window.LinksModule && typeof window.LinksModule.loadLinksData === 'function') {
            window.LinksModule.loadLinksData();
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
    if (typeof window.updateHomeStats === 'function') {
        window.updateHomeStats();
    }
}

function initSidecarErrorListener() {
    var eventAPI = window.__TAURI__ && window.__TAURI__.event && window.__TAURI__.event.listen
        ? window.__TAURI__.event
        : (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && window.__TAURI_INTERNALS__.event.listen
            ? window.__TAURI_INTERNALS__.event
            : null);
    if (!eventAPI) return;

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data) return;
        if (data.type === 'sidecar_died') {
            var diedMsg = data.message || window.t('app.backendExited');
            console.error('[App] Sidecar died:', diedMsg);
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(diedMsg);
            }
        } else if (data.type === 'sidecar_ready') {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(data.message || window.t('app.backendRecovered'));
            }
        } else if (data.type === 'sidecar_error') {
            var msg = data.message || window.t('app.backendStartFailed');
            console.error('[App] Sidecar error:', msg);
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('app.errorPrefix') + msg);
            }
            alert(window.t('app.startFailedAlert', { message: msg }));
        } else if (data.type === 'auto_convert_complete') {
            var info = data.data || {};
            if (info.converted > 0) {
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus(window.t('app.autoConvertDone', { done: info.converted, total: info.total }));
                }
                refreshWorkspaceViewsAfterChange();
            }
        } else if (data.type === 'auto_convert_error') {
            console.error('[App] Auto convert error:', data.error);
        }
    });
}

function initRagEventListener() {
    var eventAPI = window.__TAURI__ && window.__TAURI__.event
        ? window.__TAURI__.event
        : (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && window.__TAURI_INTERNALS__.event.listen
            ? window.__TAURI_INTERNALS__.event
            : null);
    if (!eventAPI) return;

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data) return;
        if (data.type === 'progress' && data.element_id === 'rag-index') {
            if (typeof window.updateStatus === 'function') {
                var pct = Math.round((data.progress || 0) * 100);
                var msg = data.message || window.t('app.indexBuilding');
                window.updateStatus(pct > 0 ? msg + ' (' + pct + '%)' : msg);
            }
        } else if (data.type === 'progress' && data.element_id === 'survey_check') {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(data.message || window.t('app.checkingSurveys'));
            }
        } else if (data.type === 'rag_chat_chunk' || data.type === 'rag_chat_done'
            || data.type === 'rag_error' || data.type === 'rag_index_built') {
            if (window.AssistantModule && window.AssistantModule.handleEvent) {
                window.AssistantModule.handleEvent(data);
            }
            if (data.type === 'rag_index_built') {
                if (data.data && data.data.success) {
                    if (typeof window.updateStatus === 'function') {
                        window.updateStatus('RAG Ready');
                    }
                } else {
                    if (typeof window.updateStatus === 'function') {
                        window.updateStatus(window.t('app.ragIndexFailed'));
                    }
                }
            }
        } else if (data.type === 'ingest_progress' || data.type === 'ingest_complete') {
            if (window.IngestModule && window.IngestModule.handleEvent) {
                window.IngestModule.handleEvent(data);
            }
        } else if (data.type === 'cascade_survey_chunk') {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('app.updatingSurvey', { topic: data.topic || '' }));
            }
        } else if (data.type === 'cascade_done') {
            var d = data.data || {};
            if (d.success) {
                var msg = d.is_new_topic ? window.t('app.surveyNewTopic') : window.t('app.surveyUpdated');
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus(msg + ': ' + (data.topic || ''));
                }
            } else {
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus(window.t('app.cascadeFailed', { topic: data.topic || '' }));
                }
            }
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else if (data.type === 'batch_assign_progress') {
            if (data.message) {
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus(data.message);
                }
            }
            if (data.message && data.message.startsWith('完成')) {
                if (window.TreeModule && window.TreeModule.loadFileTree) {
                    window.TreeModule.loadFileTree();
                }
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
    markInitialIngestDone: markInitialIngestDone
};

})();
