document.addEventListener('DOMContentLoaded', async function() {
    initMarked();
    
    initSystemThemeListener();
    
    const savedTheme = localStorage.getItem('noteai_theme') || 'system';
    applyTheme(savedTheme);
    
    initResizer();
    initPreviewResizer();
    initWindowDrag();
    
    initTabSwitching();
    
    initCustomTooltip();
    
    if (window.TiptapEditorModule && window.TiptapEditorModule.preloadModules) {
        window.TiptapEditorModule.preloadModules();
    }
    
    updateStatus('正在加载...');
    
    try {
        await checkWorkspaceStatus();
        
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
        
        if (window.DownloaderModule && window.DownloaderModule.loadSavedConfig) {
            window.DownloaderModule.loadSavedConfig();
        }
        
        if (window.ConverterModule && window.ConverterModule.loadSavedConvConfig) {
            window.ConverterModule.loadSavedConvConfig();
        }
        
        updateStatus('就绪');
    } catch (e) {
        console.error('[App] Initialization error:', e);
        updateStatus('初始化完成');
    }

    initWorkspaceFileWatcher();
    initSidecarErrorListener();
    
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
            updateStatus('正在导入 ' + (result.file_count || '') + ' 个文件...');

            if (typeof getTauriEventAPI === 'function') {
                var eventAPI = getTauriEventAPI();
                if (eventAPI) {
                    if (_fileImportUnlisten) {
                        _fileImportUnlisten();
                    }
                    _fileImportUnlisten = await eventAPI.listen('python-event', function(event) {
                        var data = event.payload;
                        if (!data) return;

                        if (data.type === 'progress' && data.element_id === 'import-progress') {
                            updateStatus(data.message || '导入中...');
                        } else if (data.type === 'file_import_complete') {
                            var d = data.data || {};
                            var msg = '导入完成：' + (d.imported || 0) + ' 个文件';
                            if (d.failed > 0) {
                                msg += '，' + d.failed + ' 个失败';
                            }
                            updateStatus(msg);
                            if (window.TreeModule && window.TreeModule.loadFileTree) {
                                window.TreeModule.loadFileTree();
                            }
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        } else if (data.type === 'file_import_error') {
                            updateStatus('导入失败：' + (data.error || '未知错误'));
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        }
                    });
                }
            }
        } else {
            updateStatus('导入失败：' + (result?.message || '未知错误'));
        }
    } catch (e) {
        console.error('[App] Import error:', e);
        updateStatus('导入失败');
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
        statusBar.textContent = 'LLM 正在改写文档...';
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
        statusBar.textContent = 'LLM 正在改写... (' + window._rewriteDisplayText.length + ' 字)';
    }
    if (window.TiptapEditor && window.TiptapEditor.instance) {
        if (window.marked) {
            var html = window.marked.parse(window._rewriteDisplayText);
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
        alert('改写失败：' + (data.message || '未知错误'));
        updateStatus('改写失败');
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

    var oldHtml = window.marked ? window.marked.parse(oldText) : '<pre>' + oldText + '</pre>';
    var newHtml = window.marked ? window.marked.parse(newText) : '<pre>' + newText + '</pre>';

    diffPanel.innerHTML = '<div class="rewrite-diff-header">' +
        '<span class="rewrite-diff-title">改写对比</span>' +
        '<button class="rewrite-diff-btn rewrite-confirm-btn" onclick="onRewriteConfirm()">✓ 采用新版本</button>' +
        '<button class="rewrite-diff-btn rewrite-cancel-btn" onclick="onRewriteCancel()">✕ 保留原版本</button>' +
        '</div>' +
        '<div class="rewrite-diff-body">' +
        '<div class="rewrite-diff-pane"><div class="rewrite-diff-pane-label">原文</div><div class="rewrite-diff-pane-content prose-preview">' + oldHtml + '</div></div>' +
        '<div class="rewrite-diff-divider"></div>' +
        '<div class="rewrite-diff-pane"><div class="rewrite-diff-pane-label">改写后</div><div class="rewrite-diff-pane-content prose-preview">' + newHtml + '</div></div>' +
        '</div>';

    diffPanel.style.display = 'flex';
    updateStatus('改写完成，请确认是否采用新版本');
}

async function onRewriteConfirm() {
    var filePath = window._rewritePendingFilePath;
    var rewrittenText = window._rewritePendingText;
    if (!filePath || !rewrittenText) return;

    updateStatus('正在保存...');
    try {
        var result = await window.api.llm_rewrite_apply(filePath, rewrittenText);
        if (result && result.success) {
            updateStatus('已保存');
            var statusBar = document.getElementById('editor-status-bar');
            if (statusBar) {
                statusBar.textContent = '已保存';
                setTimeout(function() { statusBar.textContent = ''; }, 3000);
            }
        } else {
            alert('保存失败：' + (result ? result.message || '未知错误' : '未知错误'));
            updateStatus('保存失败');
        }
    } catch (e) {
        alert('保存出错：' + (e.message || e));
        updateStatus('保存出错');
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
        statusBar.textContent = '已放弃改写';
        setTimeout(function() { statusBar.textContent = ''; }, 3000);
    }
    updateStatus('已放弃改写');
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
        alert('请先选择一个文件');
        return;
    }

    var btn = document.getElementById('titlebar-rewrite-btn');
    if (!confirm('确定要用 LLM 改写此文档吗？\n改写后将用中立客观的笔记风格重写，改写完成后可对比确认。')) return;

    var rewritePath = curPath;

    try {
        var rawResult = await window.api.read_file_raw(rewritePath);
        window._rewriteOriginalText = (rawResult && rawResult.content) ? rawResult.content : '';
    } catch (e) {
        window._rewriteOriginalText = '';
    }

    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }
    updateStatus('正在改写文档...');
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
        await window.api.llm_rewrite_stream(rewritePath);
    } catch (e) {
        alert('改写出错：' + (e.message || e));
        updateStatus('改写出错');
        var statusBar3 = document.getElementById('editor-status-bar');
        if (statusBar3) {
            statusBar3.textContent = '改写出错';
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
        if (!data || data.type !== 'workspace_files_changed') return;

        if (_workspaceWatcherDebounce) {
            clearTimeout(_workspaceWatcherDebounce);
        }
        _workspaceWatcherDebounce = setTimeout(function() {
            _workspaceWatcherDebounce = null;
            refreshCurrentSidebarView();
        }, 3000);
    }).then(function(unlisten) {
        _workspaceWatcherUnlisten = unlisten;
    });
}

function refreshCurrentSidebarView() {
    var activeView = document.querySelector('.sidebar-view-btn.active');
    if (!activeView) {
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
        return;
    }

    var view = activeView.getAttribute('data-sidebar');
    if (view === 'tree') {
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
    } else if (view === 'topic') {
        if (typeof loadTopicTree === 'function') {
            loadTopicTree(true);
        }
    } else if (view === 'tags') {
        if (typeof loadTagsView === 'function') {
            loadTagsView(true);
        }
    } else if (view === 'graph') {
        if (typeof loadLinksData === 'function') {
            loadLinksData();
        }
    } else if (view === 'relation') {
        if (typeof loadRelationGraphData === 'function') {
            loadRelationGraphData();
        }
    }
}

var _tooltipTimer = null;

function initSidecarErrorListener() {
    var eventAPI = window.__TAURI__ && window.__TAURI__.event && window.__TAURI__.event.listen
        ? window.__TAURI__.event
        : (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && window.__TAURI_INTERNALS__.event.listen
            ? window.__TAURI_INTERNALS__.event
            : null);
    if (!eventAPI) return;

    eventAPI.listen('python-event', function(event) {
        var data = event.payload;
        if (!data || data.type !== 'sidecar_error') return;
        var msg = data.message || 'Python 后端启动失败';
        console.error('[App] Sidecar error:', msg);
        updateStatus('错误: ' + msg);
        alert('NoteAI 启动失败\n\n' + msg + '\n\n请检查 Python 环境和依赖是否正确安装。');
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
