window.RewriteManager = (function() { 'use strict';

window._rewritingFilePath = null;
window._rewriteStreamText = '';
window._rewriteStreamUnlisten = null;
window._rewriteBuffer = '';
window._rewriteDisplayText = '';
window._rewriteFlushTimer = null;

function setEditorRewriting(filePath, isRewriting) {
    var container = document.getElementById('tiptap-editor-container');
    if (!container) return;

    if (isRewriting) {
        window._rewritingFilePath = filePath;
        container.classList.add('rewriting');
        if (window.StatusbarModule && window.StatusbarModule.setRewriting) {
            window.StatusbarModule.setRewriting(true, window.t('app.llmRewriting'));
        }
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(false);
        }
    } else {
        window._rewritingFilePath = null;
        container.classList.remove('rewriting');
        if (window.StatusbarModule && window.StatusbarModule.setRewriting) {
            window.StatusbarModule.setRewriting(false);
        }
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
    if (window.StatusbarModule && window.StatusbarModule.updateMessage) {
        window.StatusbarModule.updateMessage(
            window.t('app.rewritingChars', { count: window._rewriteDisplayText.length }),
            { className: 'rewriting' }
        );
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
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('app.rewriteFailedShort'));
        }
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
    if (typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('app.rewriteDoneConfirm'));
    }
}

async function onRewriteConfirm() {
    var filePath = window._rewritePendingFilePath;
    var rewrittenText = window._rewritePendingText;
    if (!filePath || !rewrittenText) return;

    if (typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('app.saving'));
    }
    try {
        var result = await window.api.llmRewriteApply(filePath, rewrittenText);
        if (result && result.success) {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('common.saved'));
            }
            if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
                window.StatusbarModule.updateSaveStatus('saved', window.t('common.saved'));
                setTimeout(function() {
                    if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
                        window.StatusbarModule.updateSaveStatus('', '');
                    }
                }, 3000);
            }
        } else {
            alert(window.t('app.saveFailed', { message: result ? result.message || window.t('common.unknownError') : window.t('common.unknownError') }));
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('app.rewriteFailedShort'));
            }
        }
    } catch (e) {
        alert(window.t('app.saveError', { message: e.message || e }));
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('app.saveError', { message: e.message || e }));
        }
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
    if (window.StatusbarModule && window.StatusbarModule.updateMessage) {
        window.StatusbarModule.updateMessage(
            window.t('app.rewriteCancelled'),
            { duration: 3000 }
        );
    }
    if (typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('app.rewriteCancelled'));
    }
    _cleanupRewriteState();
    if (window.AppState.selectedFilePath && window.PreviewModule && window.PreviewModule.loadFilePreview) {
        window.PreviewModule.loadFilePreview(window.AppState.selectedFilePath, window.AppState.selectedFileName);
    }
}

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
    if (typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('app.rewritingDoc'));
    }
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
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('app.rewriteError', { message: e.message || e }));
        }
        if (window.StatusbarModule && window.StatusbarModule.setRewriting) {
            window.StatusbarModule.setRewriting(false);
        }
        if (window.StatusbarModule && window.StatusbarModule.updateMessage) {
            window.StatusbarModule.updateMessage(
                window.t('app.rewriteError', { message: e.message || e }),
                { duration: 3000 }
            );
        }
        _cleanupRewriteState();
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    }
}

return {
    onLLMRewrite: onLLMRewrite,
    onRewriteConfirm: onRewriteConfirm,
    onRewriteCancel: onRewriteCancel,
    setEditorRewriting: setEditorRewriting
};

})();
