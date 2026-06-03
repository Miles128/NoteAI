(function() { 'use strict';

document.addEventListener('DOMContentLoaded', async function() {
    initMarked();

    // 主题已由 main.mjs 中 applyThemeBootstrap（服务端偏好 + localStorage）应用，此处不再覆盖

    if (window.ThemeModule && window.ThemeModule.restoreFontSize) {
        window.ThemeModule.restoreFontSize();
    }

    initResizer();
    initPreviewResizer();
    initWindowDrag();
    
    initTabSwitching();
    
    initCustomTooltip();
    
    if (window.TiptapEditorModule && window.TiptapEditorModule.preloadModules) {
        await window.TiptapEditorModule.preloadModules();
    }
    
    updateStatus(window.t('app.loading'));
    
    try {
        await checkWorkspaceStatus();
        
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            await window.TreeModule.loadFileTree();
        }
        
        // Default: show knowledge graph (full right panel, no splits)
        var ca = document.getElementById('content-area');
        var gp = document.getElementById('graph-panel');
        var cp = document.getElementById('content-panel');
        if (ca) ca.style.display = 'none';
        if (cp) cp.style.display = 'flex';
        if (gp) gp.style.display = 'flex';
        window.updateHomeStats();
        if (window.Graph3Tier && window.Graph3Tier.load) {
            window.Graph3Tier.load();
        }
        
        if (window.DownloaderModule && window.DownloaderModule.loadSavedConfig) {
            window.DownloaderModule.loadSavedConfig();
        }
        
        if (window.ConverterModule && window.ConverterModule.loadSavedConvConfig) {
            window.ConverterModule.loadSavedConvConfig();
        }
        
        if (typeof window.runPostWorkspaceSetup === 'function') {
            /* ingest deferred until schema wizard completes, if needed */
        }
        
            setTimeout(function() {
                if (window.api && window.api.mergeDuplicateTopics) {
                    window.api.mergeDuplicateTopics().then(function(result) {
                        if (result && result.success && result.merged_topics > 0) {
                            console.log('[App] 合并重复主题: ' + result.merged_topics + ' 个, 去重文件: ' + result.deduplicated_files + ' 个');
                        }
                    }).catch(function(e) { console.warn('[App] merge_duplicate_topics failed:', e); });
                }
            }, 8000);
        
        updateStatus(window.t('app.ready'));
    } catch (e) {
        console.error('[App] Initialization error:', e);
        updateStatus(window.t('app.initDone'));
    }

    initWorkspaceFileWatcher();
    initSidecarErrorListener();
    initRagEventListener();

    if (window.AssistantModule && window.AssistantModule.init) {
        window.AssistantModule.init();
    }
    
    const tabInputs = document.querySelectorAll('input[name="theme"], input[name="theme-popup"]');
    tabInputs.forEach(radio => {
        radio.addEventListener('change', (e) => {
            setTheme(e.target.value);
        });
    });
    
    const webAiToggle = document.getElementById('web-ai-toggle');
    if (webAiToggle) {
        webAiToggle.addEventListener('change', () => {
            if (window.TreeModule && window.TreeModule.updateWebAIStatus) {
                window.TreeModule.updateWebAIStatus();
            }
        });
    }
    
    const convAiToggle = document.getElementById('conv-ai-toggle');
    if (convAiToggle) {
        convAiToggle.addEventListener('change', () => {
            if (window.TreeModule && window.TreeModule.updateConvAIStatus) {
                window.TreeModule.updateConvAIStatus();
            }
        });
    }
    
    const topicList = document.getElementById('topic-list');
    if (topicList) {
        topicList.addEventListener('input', () => {
            if (window.IntegratorModule) {
                window.IntegratorModule.topicsReady = true;
                window.IntegratorModule.updateIntegrateBtnState();
            }
        });
    }
    
    console.log('[App] Initialization complete');
});

function initMarked() {
    if (window.EditorModule && window.EditorModule.initMarked) {
        window.EditorModule.initMarked();
    }
}

function initSystemThemeListener() {
    if (window.ThemeModule && window.ThemeModule.initSystemThemeListener) {
        window.ThemeModule.initSystemThemeListener();
    }
}

function applyTheme(theme) {
    if (window.ThemeModule && window.ThemeModule.applyTheme) {
        window.ThemeModule.applyTheme(theme);
    }
}

function setTheme(theme) {
    if (window.ThemeModule && window.ThemeModule.setTheme) {
        window.ThemeModule.setTheme(theme);
    }
}

function initResizer() {
    if (window.ThemeModule && window.ThemeModule.initResizer) {
        window.ThemeModule.initResizer();
    }
}

function initPreviewResizer() {
    if (window.ThemeModule && window.ThemeModule.initPreviewResizer) {
        window.ThemeModule.initPreviewResizer();
    }
}

function initWindowDrag() {
    if (window.EditorModule && window.EditorModule.initWindowDrag) {
        window.EditorModule.initWindowDrag();
    }
}

function initTabSwitching() {
    if (window.TabsModule && window.TabsModule.initTabs) {
        window.TabsModule.initTabs();
    }
}

async function checkWorkspaceStatus() {
    if (window.WorkspaceModule && window.WorkspaceModule.checkWorkspaceStatus) {
        await window.WorkspaceModule.checkWorkspaceStatus();
    }
}

function updateStatus(text) {
    if (window.WorkspaceModule && window.WorkspaceModule.updateStatus) {
        window.WorkspaceModule.updateStatus(text);
    }
}

var _fileImportUnlisten = null;

async function importFiles() {
    try {
        var result = await window.api.importFilesToWorkspace();
        if (!result || result.cancelled) return;

        if (result && result.success) {
            updateStatus(window.t('app.importing', { count: result.file_count || 0 }));

            if (typeof window.getTauriEventAPI === 'function') {
                var eventAPI = getTauriEventAPI();
                if (eventAPI) {
                    if (_fileImportUnlisten) {
                        _fileImportUnlisten();
                    }
                    _fileImportUnlisten = await eventAPI.listen('python-event', function(event) {
                        var data = event.payload;
                        if (!data) return;

                        if (data.type === 'progress' && data.element_id === 'import-progress') {
                            updateStatus(data.message || window.t('app.importProgress'));
                        } else if (data.type === 'file_import_complete') {
                            var d = data.data || {};
                            var msg = d.failed > 0 ? window.t('app.importDoneWithFailed', { imported: d.imported || 0, failed: d.failed }) : window.t('app.importDone', { imported: d.imported || 0 })
                            updateStatus(msg);
                            if (window.TreeModule && window.TreeModule.loadFileTree) {
                                window.TreeModule.loadFileTree();
                            }
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        } else if (data.type === 'file_import_error') {
                            updateStatus(window.t('app.importFailed', { message: data.error || window.t('common.unknownError') }));
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        }
                    });
                }
            }
        } else {
            updateStatus(window.t('app.importFailed', { message: result?.message || window.t('common.unknownError') }));
        }
    } catch (e) {
        console.error('[App] Import error:', e);
        updateStatus(window.t('app.importFailedGeneric'));
    }
}

window._rewritingFilePath = null;
window._rewriteStreamText = '';
window._rewriteStreamUnlisten = null;
window._rewriteBuffer = '';
window._rewriteDisplayText = '';
window._rewriteFlushTimer = null;

function setEditorRewriting(filePath, isRewriting) {
    var container = document.getElementById('tiptap-editor-container');
    var statusBar = document.getElementById('editor-status-bar');
    if (!container || !statusBar) return;

    if (isRewriting) {
        window._rewritingFilePath = filePath;
        container.classList.add('rewriting');
        statusBar.classList.add('rewriting');
        statusBar.textContent = window.t('app.llmRewriting');
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(false);
        }
    } else {
        window._rewritingFilePath = null;
        container.classList.remove('rewriting');
        statusBar.classList.remove('rewriting');
        statusBar.textContent = '';
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(true);
        }
    }
}

function _flushRewriteBuffer() {
    if (!window._rewriteBuffer || window._rewriteBuffer.length === 0) {
        if (window._rewriteFlushTimer) {
            clearInterval(window._rewriteFlushTimer);
            window._rewriteFlushTimer = null;
        }
        if (window._rewriteLLMDone) {
            _finishRewriteStream(window._rewriteDoneData);
        }
        return;
    }
    var chunkSize = 1;
    var take = window._rewriteBuffer.substring(0, chunkSize);
    window._rewriteBuffer = window._rewriteBuffer.substring(chunkSize);
    window._rewriteDisplayText += take;
    var statusBar = document.getElementById('editor-status-bar');
    if (statusBar) {
        statusBar.textContent = window.t('app.rewritingChars', { count: window._rewriteDisplayText.length });
    }
    if (window.TiptapEditor && window.TiptapEditor.instance) {
        if (window.marked) {
            var html = window.marked.parse(window._rewriteDisplayText);
            if (typeof DOMPurify !== 'undefined') { html = DOMPurify.sanitize(html); }
            window.TiptapEditor.instance.commands.setContent(html, false);
        }
    }
    var editorEl = document.getElementById('tiptap-editor');
    if (editorEl) {
        editorEl.scrollTop = editorEl.scrollHeight;
    }
    if (window._rewriteBuffer.length === 0 && window._rewriteFlushTimer) {
        clearInterval(window._rewriteFlushTimer);
        window._rewriteFlushTimer = null;
        if (window._rewriteLLMDone) {
            _finishRewriteStream(window._rewriteDoneData);
        }
    }
}

function _cleanupRewriteState() {
    if (window._rewriteFlushTimer) {
        clearInterval(window._rewriteFlushTimer);
        window._rewriteFlushTimer = null;
    }
    setEditorRewriting(null, false);
    if (window._rewriteStreamUnlisten) {
        window._rewriteStreamUnlisten();
        window._rewriteStreamUnlisten = null;
    }
    window._rewriteStreamText = '';
    window._rewriteBuffer = '';
    window._rewriteDisplayText = '';
    window._rewriteOriginalText = '';
    var diffPanel = document.getElementById('rewrite-diff-panel');
    if (diffPanel) diffPanel.remove();
    var container = document.getElementById('tiptap-editor-container');
    if (container) container.style.display = '';
    var previewPanel = document.getElementById('preview-panel');
    if (previewPanel) previewPanel.style.display = '';
}

function _finishRewriteStream(data) {
    if (window._rewriteFinished) return;
    window._rewriteFinished = true;
    window._rewriteDisplayText = window._rewriteStreamText;
    window._rewriteBuffer = '';
    if (window._rewriteFlushTimer) {
        clearInterval(window._rewriteFlushTimer);
        window._rewriteFlushTimer = null;
    }
    if (window._rewriteStreamUnlisten) {
        window._rewriteStreamUnlisten();
        window._rewriteStreamUnlisten = null;
    }
    if (data && data.success) {
        window._rewritePendingFilePath = data.file_path;
        window._rewritePendingText = data.rewritten_text || window._rewriteStreamText;
        _showRewriteDiffView();
    } else if (data) {
        alert(window.t('app.rewriteFailed', { message: data.message || window.t('common.unknownError') }));
        updateStatus(window.t('app.rewriteFailedShort'));
        _cleanupRewriteState();
    }
}

function _showRewriteDiffView() {
    var oldText = window._rewriteOriginalText || '';
    var newText = window._rewritePendingText || '';

    var container = document.getElementById('tiptap-editor-container');
    var previewPanel = document.getElementById('preview-panel');
    if (container) container.style.display = 'none';
    if (previewPanel) previewPanel.style.display = 'none';

    var diffPanel = document.getElementById('rewrite-diff-panel');
    if (!diffPanel) {
        diffPanel = document.createElement('div');
        diffPanel.id = 'rewrite-diff-panel';
        var mainContent = document.querySelector('.main-content');
        if (mainContent) mainContent.appendChild(diffPanel);
    }

    var oldHtml = window.marked ? window.marked.parse(oldText) : '<pre>' + escapeHtml(oldText) + '</pre>';
    var newHtml = window.marked ? window.marked.parse(newText) : '<pre>' + escapeHtml(newText) + '</pre>';

    if (typeof DOMPurify !== 'undefined') {
        oldHtml = DOMPurify.sanitize(oldHtml);
        newHtml = DOMPurify.sanitize(newHtml);
    }

    diffPanel.innerHTML = '<div class="rewrite-diff-header">' +
        '<span class="rewrite-diff-title">' + window.t('app.rewriteDiffTitle') + '</span>' +
        '<button class="rewrite-diff-btn rewrite-confirm-btn" onclick="onRewriteConfirm()">' + window.t('app.rewriteAccept') + '</button>' +
        '<button class="rewrite-diff-btn rewrite-cancel-btn" onclick="onRewriteCancel()">' + window.t('app.rewriteKeepOriginal') + '</button>' +
        '</div>' +
        '<div class="rewrite-diff-body">' +
        '<div class="rewrite-diff-pane"><div class="rewrite-diff-pane-label">' + window.t('app.rewriteOriginal') + '</div><div class="rewrite-diff-pane-content prose-preview">' + oldHtml + '</div></div>' +
        '<div class="rewrite-diff-divider"></div>' +
        '<div class="rewrite-diff-pane"><div class="rewrite-diff-pane-label">' + window.t('app.rewriteResult') + '</div><div class="rewrite-diff-pane-content prose-preview">' + newHtml + '</div></div>' +
        '</div>';

    diffPanel.style.display = 'flex';
    updateStatus(window.t('app.rewriteDoneConfirm'));
}

async function onRewriteConfirm() {
    var filePath = window._rewritePendingFilePath;
    var rewrittenText = window._rewritePendingText;
    if (!filePath || !rewrittenText) return;

    updateStatus(window.t('app.saving'));
    try {
        var result = await window.api.llmRewriteApply(filePath, rewrittenText);
        if (result && result.success) {
            updateStatus(window.t('common.saved'));
            var statusBar = document.getElementById('editor-status-bar');
            if (statusBar) {
                statusBar.textContent = window.t('common.saved');
                setTimeout(function() { statusBar.textContent = ''; }, 3000);
            }
        } else {
            alert(window.t('app.saveFailed', { message: result ? result.message || window.t('common.unknownError') : window.t('common.unknownError') }));
            updateStatus(window.t('app.rewriteFailedShort'));
        }
    } catch (e) {
        alert(window.t('app.saveError', { message: e.message || e }));
        updateStatus(window.t('app.saveError', { message: e.message || e }));
    } finally {
        window._rewritePendingFilePath = null;
        window._rewritePendingText = null;
        _cleanupRewriteState();
        if (window.AppState.selectedFilePath && window.PreviewModule && window.PreviewModule.loadFilePreview) {
            window.PreviewModule.loadFilePreview(window.AppState.selectedFilePath, window.AppState.selectedFileName);
        }
    }
}

function onRewriteCancel() {
    window._rewritePendingFilePath = null;
    window._rewritePendingText = null;
    var statusBar = document.getElementById('editor-status-bar');
    if (statusBar) {
        statusBar.textContent = window.t('app.rewriteCancelled');
        setTimeout(function() { statusBar.textContent = ''; }, 3000);
    }
    updateStatus(window.t('app.rewriteCancelled'));
    _cleanupRewriteState();
    if (window.AppState.selectedFilePath && window.PreviewModule && window.PreviewModule.loadFilePreview) {
        window.PreviewModule.loadFilePreview(window.AppState.selectedFilePath, window.AppState.selectedFileName);
    }
}

window.onRewriteConfirm = onRewriteConfirm;
window.onRewriteCancel = onRewriteCancel;

function _updateRewriteStreamEditor(token) {
    window._rewriteStreamText += token;
    window._rewriteBuffer += token;
    if (!window._rewriteFlushTimer) {
        window._rewriteFlushTimer = setInterval(_flushRewriteBuffer, 40);
    }
}

async function onLLMRewrite() {
    var curPath = window.AppState.selectedFilePath;
    if (!curPath) {
        alert(window.t('app.selectFileFirst'));
        return;
    }

    var btn = document.getElementById('tiptap-rewrite-btn');
    if (!(await window._customConfirm(window.t('app.rewriteConfirm')))) return;

    var rewritePath = curPath;

    try {
        var rawResult = await window.api.readFileRaw(rewritePath);
        window._rewriteOriginalText = (rawResult && rawResult.content) ? rawResult.content : '';
    } catch (e) {
        window._rewriteOriginalText = '';
    }

    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }
    updateStatus(window.t('app.rewritingDoc'));
    setEditorRewriting(rewritePath, true);
    window._rewriteStreamText = '';
    window._rewriteBuffer = '';
    window._rewriteDisplayText = '';
    window._rewriteLLMDone = false;
    window._rewriteDoneData = null;
    window._rewriteFinished = false;

    var eventAPI = window.__TAURI__ && window.__TAURI__.event;
    if (eventAPI) {
        window._rewriteStreamUnlisten = await eventAPI.listen('python-event', function(event) {
            var data = event.payload;
            if (!data) return;
            if (data.type === 'rewrite_chunk' && data.file_path === rewritePath) {
                _updateRewriteStreamEditor(data.token || '');
            } else if (data.type === 'rewrite_done' && data.file_path === rewritePath) {
                window._rewriteLLMDone = true;
                window._rewriteDoneData = data;
                if (!window._rewriteFlushTimer && window._rewriteBuffer.length === 0) {
                    _finishRewriteStream(data);
                }
            }
        });
    }

    try {
        await window.api.llmRewriteStream(rewritePath);
    } catch (e) {
        alert(window.t('app.rewriteError', { message: e.message || e }));
        updateStatus(window.t('app.rewriteError', { message: e.message || e }));
        var statusBar3 = document.getElementById('editor-status-bar');
        if (statusBar3) {
            statusBar3.textContent = window.t('app.rewriteError', { message: e.message || e });
            statusBar3.classList.remove('rewriting');
            setTimeout(function() { statusBar3.textContent = ''; }, 3000);
        }
        _cleanupRewriteState();
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    }
}

window.onLLMRewrite = onLLMRewrite;

window.App = {
    initMarked,
    initSystemThemeListener,
    applyTheme,
    setTheme,
    initResizer,
    initPreviewResizer,
    initWindowDrag,
    initTabSwitching,
    checkWorkspaceStatus,
    updateStatus,
    initWorkspaceFileWatcher
};

var _workspaceWatcherUnlisten = null;
var _workspaceWatcherDebounce = null;

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
            updateStatus('✓ ' + (data.topic ? window.t('app.autoAssignedTo', { topic: data.topic }) : window.t('app.autoAssignedTopic')));
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
            if (window.IngestModule && window.IngestModule.startIngest) {
                window.IngestModule.startIngest('incremental').catch(function(e) {
                    console.warn('[App] watcher incremental ingest failed:', e);
                });
            } else if (window.api && window.api.autoConvertPending) {
                window.api.autoConvertPending().catch(function(e) { console.warn('[App] watcher auto_convert_pending failed:', e); });
            }
        }, 3000);
    }).then(function(unlisten) {
        _workspaceWatcherUnlisten = unlisten;
    });
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
        window.Graph3Tier.load(null, true);
    }
    if (typeof window.updateHomeStats === 'function') {
        window.updateHomeStats();
    }
}

var _tooltipTimer = null;

async function runPostWorkspaceSetup() {
    if (window.api && window.api.needsSchemaSetup) {
        try {
            var st = await window.api.needsSchemaSetup();
            if (st && st.needs_setup) return;
        } catch (e) {
            console.warn('[App] needs_schema_setup check:', e);
        }
    }
    if (window.IngestModule && window.IngestModule.startIngest) {
        window.IngestModule.startIngest('incremental').catch(function(e) {
            console.warn('[App] start_ingest failed:', e);
        });
    } else if (window.api && window.api.autoConvertPending) {
        window.api.autoConvertPending().catch(function(e) { console.warn('[App] auto_convert_pending failed:', e); });
    }
}

window.runPostWorkspaceSetup = runPostWorkspaceSetup;

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
            updateStatus(window.t('app.errorPrefix') + msg);
            alert(window.t('app.startFailedAlert', { message: msg }));
        } else if (data.type === 'auto_convert_complete') {
            var info = data.data || {};
            if (info.converted > 0) {
                updateStatus(window.t('app.autoConvertDone', { done: info.converted, total: info.total }));
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
            updateStatus(data.message || window.t('app.indexBuilding'));
        } else if (data.type === 'progress' && data.element_id === 'survey_check') {
            updateStatus(data.message || window.t('app.checkingSurveys'));
        } else if (data.type === 'rag_chat_chunk' || data.type === 'rag_chat_done'
            || data.type === 'rag_error' || data.type === 'rag_index_built') {
            if (window.AssistantModule && window.AssistantModule.handleEvent) {
                window.AssistantModule.handleEvent(data);
            }
            if (data.type === 'rag_index_built') {
                if (data.data && data.data.success) {
                    updateStatus('RAG Ready');
                } else {
                    updateStatus(window.t('app.ragIndexFailed'));
                }
            }
        } else if (data.type === 'ingest_progress' || data.type === 'ingest_complete') {
            if (window.IngestModule && window.IngestModule.handleEvent) {
                window.IngestModule.handleEvent(data);
            }
        } else if (data.type === 'cascade_survey_chunk') {
            updateStatus(window.t('app.updatingSurvey', { topic: data.topic || '' }));
        } else if (data.type === 'cascade_done') {
            var d = data.data || {};
            if (d.success) {
                var msg = d.is_new_topic ? window.t('app.surveyNewTopic') : window.t('app.surveyUpdated');
                updateStatus(msg + ': ' + (data.topic || ''));
            } else {
                updateStatus(window.t('app.cascadeFailed', { topic: data.topic || '' }));
            }
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else if (data.type === 'batch_assign_progress') {
            if (data.message) {
                updateStatus(data.message);
            }
            if (data.message && data.message.startsWith('完成')) {
                if (window.TreeModule && window.TreeModule.loadFileTree) {
                    window.TreeModule.loadFileTree();
                }
            }
        }
    });
}

function initCustomTooltip() {
    var tip = document.getElementById('custom-tooltip');
    if (!tip) return;

    document.addEventListener('mouseover', function(e) {
        var el = e.target.closest('[title]');
        if (!el) return;
        var title = el.getAttribute('title');
        if (!title) return;

        clearTimeout(_tooltipTimer);
        _tooltipTimer = setTimeout(function() {
            tip.textContent = title;
            tip.classList.add('visible');

            var rect = el.getBoundingClientRect();
            var tipW = tip.offsetWidth;
            var tipH = tip.offsetHeight;
            var left = rect.left + rect.width / 2 - tipW / 2;
            var top = rect.bottom + 6;

            if (left < 4) left = 4;
            if (left + tipW > window.innerWidth - 4) left = window.innerWidth - tipW - 4;
            if (top + tipH > window.innerHeight - 4) top = rect.top - tipH - 6;

            tip.style.left = left + 'px';
            tip.style.top = top + 'px';
        }, 400);
    });

    document.addEventListener('mouseout', function(e) {
        var el = e.target.closest('[title]');
        if (!el) return;
        clearTimeout(_tooltipTimer);
        tip.classList.remove('visible');
    });

    document.addEventListener('mousedown', function() {
        clearTimeout(_tooltipTimer);
        tip.classList.remove('visible');
    });
}

window.importFiles = importFiles;

})();

