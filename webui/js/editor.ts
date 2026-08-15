(function() { 'use strict';

window.mdEditor = {
    view: null,
    filePath: null,
    saveTimer: null,
    isScrollSyncing: false,
    originalContent: null,
    isActive: false,
    usingFallback: false,
    getFallbackContent: null
};

function initMarked() {
    if (typeof window.marked !== 'undefined') {
        var renderer = new window.marked.Renderer();
        renderer.html = function(html: any) {
            if (typeof DOMPurify !== 'undefined') {
                return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'code', 'br', 'span', 'sub', 'sup', 'mark', 'abbr', 'kbd'] });
            }
            // fallback: strip all tags except safe inline ones
            return html.replace(/<(?!\/?(?:b|i|em|strong|code|br|span|sub|sup|mark|abbr|kbd)\b)[^>]*>/gi, '');
        };
        window.marked.setOptions({
            gfm: true,
            breaks: true,
            renderer: renderer,
            highlight: function(code: any, lang: any) {
                if (typeof hljs !== 'undefined') {
                    try {
                        if (lang && hljs.getLanguage(lang)) {
                            return hljs.highlight(code, { language: lang }).value;
                        }
                        return hljs.highlightAuto(code).value;
                    } catch (e) {
                        console.warn('[Marked] Highlight error:', e);
                    }
                }
                return code;
            }
        });
    }
}

function getEffectiveTheme() {
    const html = document.documentElement;
    const dataTheme = html.getAttribute('data-theme');
    if (dataTheme === 'dark') return 'dark';
    if (dataTheme === 'light') return 'light';
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'dark' : 'light';
}

var _hljsLinksEnsured = false;
function _ensureHljsThemeLinks() {
    if (_hljsLinksEnsured) return;
    _hljsLinksEnsured = true;
    function make(id: string, href: string) {
        if (document.getElementById(id)) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.id = id;
        link.href = href;
        document.head.appendChild(link);
    }
    make('hljs-light', 'hljs-github.css');
    make('hljs-dark', 'hljs-github-dark.css');
}

function updateHljsTheme() {
    _ensureHljsThemeLinks();
    const isDark = getEffectiveTheme() === 'dark';
    const lightLink = document.getElementById('hljs-light') as HTMLLinkElement | null;
    const darkLink = document.getElementById('hljs-dark') as HTMLLinkElement | null;
    if (lightLink) lightLink.disabled = isDark;
    if (darkLink) darkLink.disabled = !isDark;
}

function updateSaveStatus(status: any, text: any) {
    if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
        window.StatusbarModule.updateSaveStatus(status, text);
        return;
    }
    const statusEl = document.getElementById('statusbar-save-status');
    if (!statusEl) return;
    statusEl.className = 'statusbar-item statusbar-save-status ' + status;
    statusEl.textContent = text || '';
}

function initCodeMirrorEditor(content: any, filePath: any) {
    const container = document.getElementById('cm-editor-container');
    if (!container) return;

    container.innerHTML = '';

    window.mdEditor!.originalContent = content;
    window.mdEditor!.filePath = filePath;
    window.mdEditor!.isActive = true;

    updateSaveStatus('saved', window.t('editor.saveLoading'));
    createTextareaFallback(content, filePath, container);
}

function createTextareaFallback(content: any, filePath: any, container: any) {
    window.mdEditor!.usingFallback = true;
    const textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.style.cssText = 'width:100%;height:100%;border:none;outline:none;padding:12px;font-family:monospace;font-size: 14px;line-height:1.6;resize:none;background:var(--surface);color:var(--text);';
    textarea.addEventListener('input', () => {
        updateMarkdownPreview(textarea.value);
        scheduleAutoSave(textarea.value);
    });
    container.appendChild(textarea);

    updateMarkdownPreview(content);
    updateSaveStatus('saved', window.t('editor.saveSavedSimple'));
    initPreviewScrollListener();

    window.mdEditor!.getFallbackContent = () => textarea.value;
    console.log('[Editor] Textarea fallback for:', filePath, 'content length:', content.length);
}

function destroyCodeMirrorEditor() {
    if (window.mdEditor!.saveTimer) {
        clearTimeout(window.mdEditor!.saveTimer);
        window.mdEditor!.saveTimer = null;
    }
    if (window.mdEditor!.usingFallback) {
        performImmediateSave();
        window.mdEditor!.usingFallback = false;
        window.mdEditor!.getFallbackContent = null;
    }
    window.mdEditor!.filePath = null;
    window.mdEditor!.originalContent = null;
    window.mdEditor!.isActive = false;
    window.mdEditor!.isScrollSyncing = false;
}

function updateMarkdownPreview(content: any) {
    const previewEl = document.getElementById('editor-preview-scroll');
    if (!previewEl) return;

    if (typeof window.marked !== 'undefined') {
        try {
            var rawHtml = window.marked.parse(content);
            previewEl.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : window.escapeHtml(content);
        } catch (e) {
            console.error('[Marked] Parse error:', e);
            previewEl.innerHTML = '<p class="preview-error">' + window.t('editor.previewParseError') + '</p>';
        }
    } else {
        previewEl.innerHTML = '<pre>' + window.escapeHtml(content) + '</pre>';
    }
}

function renderMarkdownPreview(content: any) {
    if (typeof window.marked !== 'undefined') {
        try {
            var processedContent = processAbstractLinks(content);
            var rawHtml = window.marked.parse(processedContent);
            return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : window.escapeHtml(content);
        } catch (e) {
            console.error('[Marked] Parse error:', e);
            return '<p class="preview-error">' + window.t('editor.parseFailed') + '</p>';
        }
    }
    return '<pre>' + window.escapeHtml(content) + '</pre>';
}

function processAbstractLinks(content: any) {
    if (!content) return content;

    var result = content;

    // 处理 {{abstract:主题名}} 嵌入语法
    result = result.replace(/\{\{abstract:([^}]+)\}\}/g, function(match: any, topicName: any) {
        var trimmed = topicName.trim();
        var absPath = buildAbstractPath(trimmed);
        return `<span class="abstract-embed" data-topic="${window.escapeHtml(trimmed)}" data-path="${window.escapeHtml(absPath)}">${window.t('editor.surveyEmbed', { topic: trimmed })}</span>`;
    });

    // 处理 [[主题名|显示文本]] 带显示文本的链接
    result = result.replace(/\[\[([^\|]+)\|([^\]]+)\]\]/g, function(match: any, topicName: any, displayText: any) {
        var trimmedTopic = topicName.trim();
        var display = displayText.trim();
        var absPath = buildAbstractPath(trimmedTopic);
        return `[${display}](notes://${encodeURIComponent(absPath)})`;
    });

    // 处理 [[主题名]] 简单链接
    result = result.replace(/\[\[([^\]]+)\]\]/g, function(match: any, topicName: any) {
        var trimmed = topicName.trim();
        var absPath = buildAbstractPath(trimmed);
        return `[${trimmed}](notes://${encodeURIComponent(absPath)})`;
    });

    return result;
}

function buildAbstractPath(topicName: any) {
    if (topicName.includes(' > ')) {
        var parts = topicName.split(' > ');
        return `wiki/${parts[0]}/${parts[parts.length - 1]}.md`;
    }
    return `wiki/${topicName}.md`;
}

function scheduleAutoSave(content: any) {
    if (window.mdEditor!.saveTimer) {
        clearTimeout(window.mdEditor!.saveTimer);
    }

    window.mdEditor!.saveTimer = setTimeout(() => {
        performSave(content);
    }, 1000);
}

function performImmediateSave() {
    let content;
    if (window.mdEditor!.usingFallback && window.mdEditor!.getFallbackContent) {
        content = window.mdEditor!.getFallbackContent();
    } else if (window.mdEditor!.view) {
        content = window.mdEditor!.view.state.doc.toString();
    } else {
        return;
    }

    if (window.mdEditor!.saveTimer) {
        clearTimeout(window.mdEditor!.saveTimer);
        window.mdEditor!.saveTimer = null;
    }
    performSave(content);
}

var _savePromise: any = null;

async function performSave(content: any) {
    if (!window.mdEditor!.filePath) return;

    while (_savePromise) {
        await _savePromise;
    }

    _savePromise = (async () => {
        updateSaveStatus('saving', window.t('editor.saving'));

        try {
            const result = await window.api.saveFileContent(window.mdEditor!.filePath, content);

            if (result && result.success) {
                window.mdEditor!.originalContent = content;
                updateSaveStatus('saved', window.t('editor.saveSaved'));
            } else {
                updateSaveStatus('error', window.t('editor.saveFailed'));
            }
        } catch (e) {
            updateSaveStatus('error', window.t('editor.saveFailed'));
        } finally {
            _savePromise = null;
        }
    })();

    await _savePromise;
}

var _previewScrollBound = false;

function initPreviewScrollListener() {
    const previewScroll = document.getElementById('editor-preview-scroll');
    if (!previewScroll || _previewScrollBound) return;
    _previewScrollBound = true;

    previewScroll.addEventListener('scroll', () => {
        if (window.mdEditor!.isScrollSyncing) return;
        syncScrollFromPreview(previewScroll);
    });
}

function syncScrollFromEditor(view: any) {
    const previewScroll = document.getElementById('editor-preview-scroll');
    if (!previewScroll) return;

    window.mdEditor!.isScrollSyncing = true;

    const editorScrollTop = view.scrollDOM.scrollTop;
    const editorScrollHeight = view.scrollDOM.scrollHeight;
    const editorClientHeight = view.scrollDOM.clientHeight;

    const previewScrollHeight = previewScroll.scrollHeight;
    const previewClientHeight = previewScroll.clientHeight;

    const editorMaxScroll = editorScrollHeight - editorClientHeight;
    const scrollRatio = editorMaxScroll > 0 ? editorScrollTop / editorMaxScroll : 0;
    const previewScrollTop = scrollRatio * (previewScrollHeight - previewClientHeight);

    previewScroll.scrollTop = previewScrollTop;

    setTimeout(() => {
        window.mdEditor!.isScrollSyncing = false;
    }, 50);
}

function syncScrollFromPreview(previewScroll: any) {
    if (!window.mdEditor!.view) return;

    window.mdEditor!.isScrollSyncing = true;

    const previewScrollTop = previewScroll.scrollTop;
    const previewScrollHeight = previewScroll.scrollHeight;
    const previewClientHeight = previewScroll.clientHeight;

    const editorScrollDOM = window.mdEditor!.view.scrollDOM;
    const editorScrollHeight = editorScrollDOM.scrollHeight;
    const editorClientHeight = editorScrollDOM.clientHeight;

    const previewMaxScroll = previewScrollHeight - previewClientHeight;
    const scrollRatio = previewMaxScroll > 0 ? previewScrollTop / previewMaxScroll : 0;
    const editorScrollTop = scrollRatio * (editorScrollHeight - editorClientHeight);

    editorScrollDOM.scrollTop = editorScrollTop;

    setTimeout(() => {
        window.mdEditor!.isScrollSyncing = false;
    }, 50);
}

function enterEditMode() {
    // 编辑渲染依赖 marked/highlight/purify；若尚未懒加载则后台预热（幂等）
    if (window.ensureMarkedConfigured) window.ensureMarkedConfigured();
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');
    const splitBtn = document.getElementById('titlebar-split-btn');

    if (previewContent) previewContent.style.display = 'none';
    if (tiptapContainer) tiptapContainer.style.display = 'flex';
    if (toolbar) toolbar.style.display = 'flex';
    if (splitBtn) splitBtn.classList.add('active');
}

function exitEditMode() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');
    const splitBtn = document.getElementById('titlebar-split-btn');

    if (window.TiptapEditor && window.TiptapEditor.isActive) {
        if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
            window.TiptapEditorModule.hideEditorUI();
        }
    }

    if (previewContent) previewContent.style.display = 'block';
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
    if (splitBtn) splitBtn.classList.remove('active');
}

async function toggleEditMode() {
    const splitBtn = document.getElementById('titlebar-split-btn');

    if (window.TiptapEditor && window.TiptapEditor.isActive) {
        exitEditMode();
        var pd = window.PreviewModule ? window.PreviewModule.currentPreviewData : null;
        if (pd && pd.type === 'markdown') {
            const content = document.getElementById('preview-content');
            if (content) {
                content.innerHTML = renderMarkdownPreview(pd.content);
            }
        }
    } else {
        var pd = window.PreviewModule ? window.PreviewModule.currentPreviewData : null;
        if (pd && pd.type === 'markdown') {
            if (window.TiptapEditorModule && window.TiptapEditorModule.openMarkdownInEditor) {
                const success = await window.TiptapEditorModule.openMarkdownInEditor(
                    pd.content,
                    window.AppState.selectedFilePath
                );
                if (!success) {
                    console.warn('[Editor] Tiptap init failed, using CodeMirror fallback');
                    enterEditMode();
                    initCodeMirrorEditor(pd.content, window.AppState.selectedFilePath);
                    if (splitBtn) splitBtn.classList.add('active');
                }
            } else {
                enterEditMode();
                initCodeMirrorEditor(pd.content, window.AppState.selectedFilePath);
                if (splitBtn) splitBtn.classList.add('active');
            }
        }
    }
}

function initEditorInnerResizer() {
}

function initWindowDrag() {
}

window.toggleEditMode = toggleEditMode;

window.EditorModule = {
    mdEditor: window.mdEditor,
    initMarked,
    getEffectiveTheme,
    updateHljsTheme,
    updateSaveStatus,
    initCodeMirrorEditor,
    createTextareaFallback,
    destroyCodeMirrorEditor,
    updateMarkdownPreview,
    renderMarkdownPreview,
    scheduleAutoSave,
    performImmediateSave,
    performSave,
    initPreviewScrollListener,
    syncScrollFromEditor,
    syncScrollFromPreview,
    enterEditMode,
    exitEditMode,
    toggleEditMode,
    initEditorInnerResizer,
    initWindowDrag
};

})();

