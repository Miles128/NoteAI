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
    if (typeof marked !== 'undefined') {
        var renderer = new marked.Renderer();
        renderer.html = function(html) {
            return html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
        };
        marked.setOptions({
            gfm: true,
            breaks: true,
            renderer: renderer,
            highlight: function(code, lang) {
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

function updateHljsTheme() {
    const isDark = getEffectiveTheme() === 'dark';
    const lightLink = document.getElementById('hljs-light');
    const darkLink = document.getElementById('hljs-dark');
    if (lightLink) lightLink.disabled = isDark;
    if (darkLink) darkLink.disabled = !isDark;
}

function updateSaveStatus(status, text) {
    const statusEl = document.getElementById('editor-save-status');
    if (!statusEl) return;
    statusEl.className = 'editor-save-status ' + status;
    statusEl.textContent = text || '';
}

function initCodeMirrorEditor(content, filePath) {
    const container = document.getElementById('cm-editor-container');
    if (!container) return;

    container.innerHTML = '';

    window.mdEditor.originalContent = content;
    window.mdEditor.filePath = filePath;
    window.mdEditor.isActive = true;

    updateSaveStatus('saved', '加载中...');

    if (!window.EditorBridge || !window.EditorBridge.isReady) {
        console.warn('[Editor] EditorBridge not ready, waiting 5s...');
        let waited = 0;
        const checkInterval = setInterval(() => {
            waited += 200;
            if (window.EditorBridge && window.EditorBridge.isReady) {
                clearInterval(checkInterval);
                createCodeMirrorInstance(content, filePath, container);
            } else if (waited >= 5000) {
                clearInterval(checkInterval);
                console.warn('[Editor] EditorBridge timeout, using textarea fallback');
                createTextareaFallback(content, filePath, container);
            }
        }, 200);
        return;
    }

    try {
        createCodeMirrorInstance(content, filePath, container);
    } catch (e) {
        console.error('[Editor] CodeMirror init failed:', e);
        createTextareaFallback(content, filePath, container);
    }
}

function createCodeMirrorInstance(content, filePath, container) {
    const M = window.EditorBridge.modules;
    const isDark = getEffectiveTheme() === 'dark';
    const theme = isDark ? M.oneDark : M.oneLight;

    const updateListener = M.EditorView.updateListener.of((v) => {
        if (v.docChanged) {
            const newContent = v.state.doc.toString();
            updateMarkdownPreview(newContent);
            scheduleAutoSave(newContent);
        }
    });

    const scrollListener = M.EditorView.domEventHandlers({
        scroll: (event, view) => {
            if (window.mdEditor.isScrollSyncing) return;
            syncScrollFromEditor(view);
        }
    });

    const extensions = [
        M.basicSetup,
        M.markdown(),
        theme,
        updateListener,
        scrollListener,
        M.keymap.of([
            M.indentWithTab,
            ...M.closeBracketsKeymap,
            ...M.defaultKeymap,
            ...M.historyKeymap,
            ...M.completionKeymap,
            ...M.lintKeymap
        ])
    ];

    const state = M.EditorState.create({
        doc: content,
        extensions: extensions
    });

    window.mdEditor.view = new M.EditorView({
        state: state,
        parent: container
    });

    updateMarkdownPreview(content);
    updateSaveStatus('saved', '已保存');
    initPreviewScrollListener();

    console.log('[Editor] CodeMirror initialized for:', filePath, 'content length:', content.length);
}

function createTextareaFallback(content, filePath, container) {
    window.mdEditor.usingFallback = true;
    const textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.style.cssText = 'width:100%;height:100%;border:none;outline:none;padding:12px;font-family:monospace;font-size: 14px;line-height:1.6;resize:none;background:var(--surface);color:var(--text);';
    textarea.addEventListener('input', () => {
        updateMarkdownPreview(textarea.value);
        scheduleAutoSave(textarea.value);
    });
    container.appendChild(textarea);

    updateMarkdownPreview(content);
    updateSaveStatus('saved', '已保存(简易模式)');
    initPreviewScrollListener();

    window.mdEditor.getFallbackContent = () => textarea.value;
    console.log('[Editor] Textarea fallback for:', filePath, 'content length:', content.length);
}

function destroyCodeMirrorEditor() {
    if (window.mdEditor.saveTimer) {
        clearTimeout(window.mdEditor.saveTimer);
        window.mdEditor.saveTimer = null;
    }
    if (window.mdEditor.usingFallback) {
        performImmediateSave();
        window.mdEditor.usingFallback = false;
        window.mdEditor.getFallbackContent = null;
    } else if (window.mdEditor.view) {
        performImmediateSave();
        window.mdEditor.view.destroy();
        window.mdEditor.view = null;
    }
    window.mdEditor.filePath = null;
    window.mdEditor.originalContent = null;
    window.mdEditor.isActive = false;
    window.mdEditor.isScrollSyncing = false;
}

function updateEditorTheme() {
    if (!window.mdEditor.view || !window.EditorBridge || !window.EditorBridge.isReady) return;
    
    const M = window.EditorBridge.modules;
    const isDark = getEffectiveTheme() === 'dark';
    const theme = isDark ? M.oneDark : M.oneLight;
    
    const currentDoc = window.mdEditor.view.state.doc;
    const container = window.mdEditor.view.dom.parentElement;
    
    window.mdEditor.view.destroy();
    
    const updateListener = M.EditorView.updateListener.of((v) => {
        if (v.docChanged) {
            const newContent = v.state.doc.toString();
            updateMarkdownPreview(newContent);
            scheduleAutoSave(newContent);
        }
    });

    const extensions = [
        M.basicSetup,
        M.markdown(),
        theme,
        updateListener,
        M.keymap.of([
            M.indentWithTab,
            ...M.closeBracketsKeymap,
            ...M.defaultKeymap,
            ...M.historyKeymap,
            ...M.completionKeymap,
            ...M.lintKeymap
        ])
    ];

    const state = M.EditorState.create({
        doc: currentDoc,
        extensions: extensions
    });

    window.mdEditor.view = new M.EditorView({
        state: state,
        parent: container
    });
    
    updateHljsTheme();
    console.log('[Editor] Theme updated to:', isDark ? 'dark' : 'light');
}

function updateMarkdownPreview(content) {
    const previewEl = document.getElementById('editor-preview-scroll');
    if (!previewEl) return;
    
    if (typeof marked !== 'undefined') {
        try {
            previewEl.innerHTML = marked.parse(content);
        } catch (e) {
            console.error('[Marked] Parse error:', e);
            previewEl.innerHTML = '<p class="preview-error">解析失败</p>';
        }
    } else {
        previewEl.innerHTML = '<pre>' + escapeHtml(content) + '</pre>';
    }
}

function renderMarkdownPreview(content) {
    if (typeof marked !== 'undefined') {
        try {
            return marked.parse(content);
        } catch (e) {
            console.error('[Marked] Parse error:', e);
            return '<p class="preview-error">解析失败</p>';
        }
    }
    return '<pre>' + escapeHtml(content) + '</pre>';
}

function scheduleAutoSave(content) {
    if (window.mdEditor.saveTimer) {
        clearTimeout(window.mdEditor.saveTimer);
    }
    
    window.mdEditor.saveTimer = setTimeout(() => {
        performSave(content);
    }, 1000);
}

function performImmediateSave() {
    let content;
    if (window.mdEditor.usingFallback && window.mdEditor.getFallbackContent) {
        content = window.mdEditor.getFallbackContent();
    } else if (window.mdEditor.view) {
        content = window.mdEditor.view.state.doc.toString();
    } else {
        return;
    }
    
    if (window.mdEditor.saveTimer) {
        clearTimeout(window.mdEditor.saveTimer);
        window.mdEditor.saveTimer = null;
    }
    performSave(content);
}

async function performSave(content) {
    if (!window.mdEditor.filePath) return;
    
    updateSaveStatus('saving', '保存中...');
    
    try {
        const result = await window.api.save_note_file(window.mdEditor.filePath, content);
        
        if (result && result.success) {
            window.mdEditor.originalContent = content;
            updateSaveStatus('saved', '已保存');
            console.log('[Editor] Saved:', window.mdEditor.filePath);
        } else {
            updateSaveStatus('error', '保存失败');
            console.error('[Editor] Save failed:', result);
        }
    } catch (e) {
        updateSaveStatus('error', '保存失败');
        console.error('[Editor] Save error:', e);
    }
}

function initPreviewScrollListener() {
    const previewScroll = document.getElementById('editor-preview-scroll');
    if (!previewScroll) return;
    
    previewScroll.addEventListener('scroll', () => {
        if (window.mdEditor.isScrollSyncing) return;
        syncScrollFromPreview(previewScroll);
    });
}

function syncScrollFromEditor(view) {
    const previewScroll = document.getElementById('editor-preview-scroll');
    if (!previewScroll) return;
    
    window.mdEditor.isScrollSyncing = true;
    
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
        window.mdEditor.isScrollSyncing = false;
    }, 50);
}

function syncScrollFromPreview(previewScroll) {
    if (!window.mdEditor.view) return;
    
    window.mdEditor.isScrollSyncing = true;
    
    const previewScrollTop = previewScroll.scrollTop;
    const previewScrollHeight = previewScroll.scrollHeight;
    const previewClientHeight = previewScroll.clientHeight;
    
    const editorScrollDOM = window.mdEditor.view.scrollDOM;
    const editorScrollHeight = editorScrollDOM.scrollHeight;
    const editorClientHeight = editorScrollDOM.clientHeight;
    
    const previewMaxScroll = previewScrollHeight - previewClientHeight;
    const scrollRatio = previewMaxScroll > 0 ? previewScrollTop / previewMaxScroll : 0;
    const editorScrollTop = scrollRatio * (editorScrollHeight - editorClientHeight);
    
    editorScrollDOM.scrollTop = editorScrollTop;
    
    setTimeout(() => {
        window.mdEditor.isScrollSyncing = false;
    }, 50);
}

function enterEditMode() {
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
        if (currentPreviewData && currentPreviewData.type === 'markdown') {
            const content = document.getElementById('preview-content');
            if (content) {
                content.innerHTML = renderMarkdownPreview(currentPreviewData.content);
            }
        }
    } else {
        if (currentPreviewData && currentPreviewData.type === 'markdown') {
            if (window.TiptapEditorModule && window.TiptapEditorModule.openMarkdownInEditor) {
                const success = await window.TiptapEditorModule.openMarkdownInEditor(
                    currentPreviewData.content,
                    selectedFilePath
                );
                if (!success) {
                    console.warn('[Editor] Tiptap init failed, using CodeMirror fallback');
                    enterEditMode();
                    initCodeMirrorEditor(currentPreviewData.content, selectedFilePath);
                    if (splitBtn) splitBtn.classList.add('active');
                }
            } else {
                enterEditMode();
                initCodeMirrorEditor(currentPreviewData.content, selectedFilePath);
                if (splitBtn) splitBtn.classList.add('active');
            }
        }
    }
}

function initEditorInnerResizer() {
}

function initWindowDrag() {
}

window.EditorModule = {
    mdEditor: window.mdEditor,
    initMarked,
    getEffectiveTheme,
    updateHljsTheme,
    updateSaveStatus,
    initCodeMirrorEditor,
    createCodeMirrorInstance,
    createTextareaFallback,
    destroyCodeMirrorEditor,
    updateEditorTheme,
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
