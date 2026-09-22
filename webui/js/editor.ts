(function() { 'use strict';


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
                    window.AppState.selectedFilePath || ''
                );
                if (!success) {
                    console.error('[Editor] Tiptap init failed, no fallback available');
                    if (window.updateStatus) window.updateStatus(window.t ? window.t('editor.openFailed') : '编辑器初始化失败');
                }
            } else {
                console.error('[Editor] TiptapEditorModule unavailable, no fallback available');
                if (window.updateStatus) window.updateStatus(window.t ? window.t('editor.openFailed') : '编辑器初始化失败');
            }
        }
    }
}
window.toggleEditMode = toggleEditMode;

window.EditorModule = {
    initMarked,
    getEffectiveTheme,
    updateHljsTheme,
    renderMarkdownPreview,
    exitEditMode,
    toggleEditMode,
};

})();

