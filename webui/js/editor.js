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
        marked.setOptions({
            gfm: true,
            breaks: true,
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
    textarea.style.cssText = 'width:100%;height:100%;border:none;outline:none;padding:12px;font-family:monospace;font-size:13px;line-height:1.6;resize:none;background:var(--surface);color:var(--text);';
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
    
    const scrollRatio = editorScrollTop / (editorScrollHeight - editorClientHeight);
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
    
    const scrollRatio = previewScrollTop / (previewScrollHeight - previewClientHeight);
    const editorScrollTop = scrollRatio * (editorScrollHeight - editorClientHeight);
    
    editorScrollDOM.scrollTop = editorScrollTop;
    
    setTimeout(() => {
        window.mdEditor.isScrollSyncing = false;
    }, 50);
}

function enterEditMode() {
    const previewContent = document.getElementById('preview-content');
    const editorContainer = document.getElementById('editor-container');
    const previewPanel = document.getElementById('preview-panel');

    if (previewContent) previewContent.style.display = 'none';
    if (editorContainer) editorContainer.style.display = 'flex';
    if (previewPanel) previewPanel.classList.add('editor-active');

    initEditorInnerResizer();
    updateHljsTheme();
}

function exitEditMode() {
    const previewContent = document.getElementById('preview-content');
    const editorContainer = document.getElementById('editor-container');
    const previewPanel = document.getElementById('preview-panel');
    const splitBtn = document.getElementById('preview-split-btn');

    destroyCodeMirrorEditor();

    if (previewContent) previewContent.style.display = 'block';
    if (editorContainer) editorContainer.style.display = 'none';
    if (previewPanel) previewPanel.classList.remove('editor-active');
    if (splitBtn) splitBtn.classList.remove('active');
}

function toggleEditMode() {
    const splitBtn = document.getElementById('preview-split-btn');
    if (window.mdEditor.isActive) {
        exitEditMode();
        if (currentPreviewData && currentPreviewData.type === 'markdown') {
            const content = document.getElementById('preview-content');
            if (content) content.innerHTML = renderMarkdownPreview(currentPreviewData.content);
        }
    } else {
        if (currentPreviewData && currentPreviewData.type === 'markdown') {
            enterEditMode();
            initCodeMirrorEditor(currentPreviewData.content, selectedFilePath);
            if (splitBtn) splitBtn.classList.add('active');
        }
    }
}

function initEditorInnerResizer() {
    const resizer = document.getElementById('editor-inner-resizer');
    const leftPane = document.getElementById('editor-pane-left');
    const rightPane = document.getElementById('editor-pane-right');

    if (!resizer || !leftPane || !rightPane) {
        console.log('[DEBUG] initEditorInnerResizer: elements not found');
        return;
    }

    let isResizing = false;
    let startX = 0;
    let leftStartFlex = 1;
    let rightStartFlex = 1;

    const savedLeftFlex = localStorage.getItem('editor-left-flex');
    const savedRightFlex = localStorage.getItem('editor-right-flex');
    if (savedLeftFlex && savedRightFlex) {
        leftPane.style.flex = savedLeftFlex;
        rightPane.style.flex = savedRightFlex;
    }

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        startX = e.clientX;
        const leftStyle = window.getComputedStyle(leftPane);
        const rightStyle = window.getComputedStyle(rightPane);
        leftStartFlex = parseFloat(leftStyle.flexGrow) || 1;
        rightStartFlex = parseFloat(rightStyle.flexGrow) || 1;
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const dx = e.clientX - startX;
        const totalFlex = leftStartFlex + rightStartFlex;
        const containerWidth = leftPane.parentElement.clientWidth;
        const flexPerPixel = totalFlex / containerWidth;
        const flexDelta = dx * flexPerPixel;
        let newLeftFlex = leftStartFlex + flexDelta;
        let newRightFlex = rightStartFlex - flexDelta;
        const minFlex = 0.3;
        if (newLeftFlex < minFlex) {
            newLeftFlex = minFlex;
            newRightFlex = totalFlex - minFlex;
        }
        if (newRightFlex < minFlex) {
            newRightFlex = minFlex;
            newLeftFlex = totalFlex - minFlex;
        }
        leftPane.style.flex = newLeftFlex;
        rightPane.style.flex = newRightFlex;
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        const leftStyle = window.getComputedStyle(leftPane);
        const rightStyle = window.getComputedStyle(rightPane);
        localStorage.setItem('editor-left-flex', leftStyle.flexGrow);
        localStorage.setItem('editor-right-flex', rightStyle.flexGrow);
    });
}

function initWindowDrag() {
    const titlebar = document.querySelector('.titlebar-drag');
    if (!titlebar || !window.api) return;

    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let accumDx = 0;
    let accumDy = 0;
    let rafId = null;

    function flushMove() {
        if (accumDx !== 0 || accumDy !== 0) {
            window.api.move_window(accumDx, accumDy);
            accumDx = 0;
            accumDy = 0;
        }
        if (isDragging) {
            rafId = requestAnimationFrame(flushMove);
        }
    }

    titlebar.addEventListener('mousedown', (e) => {
        if (e.target.closest('.titlebar-btn')) return;
        isDragging = true;
        dragStartX = e.screenX;
        dragStartY = e.screenY;
        accumDx = 0;
        accumDy = 0;
        rafId = requestAnimationFrame(flushMove);
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        accumDx += e.screenX - dragStartX;
        accumDy += e.screenY - dragStartY;
        dragStartX = e.screenX;
        dragStartY = e.screenY;
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        if (rafId) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
        if (accumDx !== 0 || accumDy !== 0) {
            window.api.move_window(accumDx, accumDy);
            accumDx = 0;
            accumDy = 0;
        }
    });
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
