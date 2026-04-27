window.TiptapEditor = {
    instance: null,
    filePath: null,
    saveTimer: null,
    isActive: false,
    originalContent: null,
    modules: {},
    modulesReady: false,
    initPromise: null
};

window.TiptapEditor.initPromise = new Promise((resolve) => {
    window.TiptapEditor.resolveInit = resolve;
});

function initTiptapModules() {
    if (window.TiptapEditor.modulesReady) {
        return window.TiptapEditor.initPromise;
    }

    const script = document.createElement('script');
    script.type = 'module';
    script.textContent = `
        (async () => {
            console.log('[Tiptap] Starting module load...');
            try {
                const [
                    { Editor },
                    { default: StarterKit },
                    { Markdown }
                ] = await Promise.all([
                    import('https://esm.sh/@tiptap/core@2.6.6'),
                    import('https://esm.sh/@tiptap/starter-kit@2.6.6'),
                    import('https://esm.sh/tiptap-markdown@0.8.0')
                ]);

                console.log('[Tiptap] Core modules loaded');

                window.TiptapEditor.modules = {
                    Editor,
                    StarterKit,
                    Markdown
                };

                window.TiptapEditor.modulesReady = true;
                window.TiptapEditor.resolveInit(true);
                window.dispatchEvent(new CustomEvent('tiptap-ready'));
                console.log('[Tiptap] All modules loaded successfully');
            } catch (e) {
                console.error('[Tiptap] Failed to load modules:', e);
                window.TiptapEditor.resolveInit(false);
            }
        })();
    `;
    document.head.appendChild(script);

    return window.TiptapEditor.initPromise;
}

function bindTiptapToolbarEvents() {
    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    toolbar.addEventListener('click', (e) => {
        const btn = e.target.closest('.tiptap-btn[data-action]');
        if (!btn || btn.disabled) return;

        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
        executeTiptapAction(action, level);
    });
}

function executeTiptapAction(action, level) {
    const editor = window.TiptapEditor.instance;
    if (!editor) {
        console.warn('[Tiptap] No editor instance');
        return;
    }

    try {
        switch (action) {
            case 'bold':
                editor.chain().focus().toggleBold().run();
                break;
            case 'italic':
                editor.chain().focus().toggleItalic().run();
                break;
            case 'strike':
                editor.chain().focus().toggleStrike().run();
                break;
            case 'code':
                editor.chain().focus().toggleCode().run();
                break;
            case 'heading':
                if (level) {
                    editor.chain().focus().toggleHeading({ level }).run();
                }
                break;
            case 'bulletList':
                editor.chain().focus().toggleBulletList().run();
                break;
            case 'orderedList':
                editor.chain().focus().toggleOrderedList().run();
                break;
            case 'blockquote':
                editor.chain().focus().toggleBlockquote().run();
                break;
            case 'codeBlock':
                editor.chain().focus().toggleCodeBlock().run();
                break;
            case 'undo':
                editor.chain().focus().undo().run();
                break;
            case 'redo':
                editor.chain().focus().redo().run();
                break;
        }
    } catch (e) {
        console.error('[Tiptap] Action error:', action, e);
    }

    updateTiptapToolbarState();
}

function updateTiptapToolbarState() {
    const editor = window.TiptapEditor.instance;
    if (!editor) return;

    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    const buttons = toolbar.querySelectorAll('.tiptap-btn[data-action]');
    buttons.forEach(btn => {
        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;

        if (action === 'undo') {
            try {
                btn.disabled = !editor.can().undo();
            } catch (e) {
                btn.disabled = false;
            }
        } else if (action === 'redo') {
            try {
                btn.disabled = !editor.can().redo();
            } catch (e) {
                btn.disabled = false;
            }
        } else {
            btn.disabled = false;
        }

        let isActive = false;
        try {
            if (action === 'heading' && level) {
                isActive = editor.isActive('heading', { level });
            } else if (action === 'bulletList') {
                isActive = editor.isActive('bulletList');
            } else if (action === 'orderedList') {
                isActive = editor.isActive('orderedList');
            } else if (action === 'blockquote') {
                isActive = editor.isActive('blockquote');
            } else if (action === 'codeBlock') {
                isActive = editor.isActive('codeBlock');
            } else if (action === 'bold') {
                isActive = editor.isActive('bold');
            } else if (action === 'italic') {
                isActive = editor.isActive('italic');
            } else if (action === 'strike') {
                isActive = editor.isActive('strike');
            } else if (action === 'code') {
                isActive = editor.isActive('code');
            }
        } catch (e) {}

        if (isActive) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

function createTiptapEditor(markdownContent, filePath) {
    const container = document.getElementById('tiptap-editor');
    if (!container) {
        console.error('[Tiptap] Editor container not found');
        return false;
    }

    if (window.TiptapEditor.instance) {
        destroyTiptapEditor();
    }

    const M = window.TiptapEditor.modules;

    if (!M.Editor || !M.StarterKit || !M.Markdown) {
        console.error('[Tiptap] Required modules not available');
        return false;
    }

    container.innerHTML = '';

    window.TiptapEditor.filePath = filePath;
    window.TiptapEditor.originalContent = markdownContent;
    window.TiptapEditor.isActive = true;

    try {
        const extensions = [
            M.StarterKit.configure({
                heading: {
                    levels: [1, 2, 3, 4, 5, 6]
                }
            }),
            M.Markdown.configure({
                html: true,
                tightLists: true,
                bulletListMarker: '-',
                linkify: false,
                breaks: true
            })
        ];

        window.TiptapEditor.instance = new M.Editor({
            element: container,
            extensions: extensions,
            content: markdownContent || '',
            editorProps: {
                attributes: {
                    class: 'tiptap-prose',
                    spellcheck: 'true'
                }
            },
            onUpdate: ({ editor }) => {
                if (window.TiptapEditor.saveTimer) {
                    clearTimeout(window.TiptapEditor.saveTimer);
                }
                window.TiptapEditor.saveTimer = setTimeout(() => {
                    saveTiptapContent();
                }, 1000);
            },
            onSelectionUpdate: () => {
                updateTiptapToolbarState();
            }
        });

        bindTiptapToolbarEvents();
        updateTiptapToolbarState();

        console.log('[Tiptap] Editor created for:', filePath, 'content length:', (markdownContent || '').length);
        return true;
    } catch (e) {
        console.error('[Tiptap] Failed to create editor:', e);
        window.TiptapEditor.isActive = false;
        return false;
    }
}

async function saveTiptapContent() {
    if (!window.TiptapEditor.instance || !window.TiptapEditor.filePath) {
        return;
    }

    try {
        const markdown = window.TiptapEditor.instance.storage.markdown.getMarkdown();
        const result = await window.api.save_note_file(window.TiptapEditor.filePath, markdown);

        if (result && result.success) {
            window.TiptapEditor.originalContent = markdown;
            console.log('[Tiptap] Saved:', window.TiptapEditor.filePath);
        } else {
            console.error('[Tiptap] Save failed:', result);
        }
    } catch (e) {
        console.error('[Tiptap] Save error:', e);
    }
}

function destroyTiptapEditor() {
    if (window.TiptapEditor.saveTimer) {
        clearTimeout(window.TiptapEditor.saveTimer);
        window.TiptapEditor.saveTimer = null;
    }

    if (window.TiptapEditor.instance) {
        saveTiptapContent();
        try {
            window.TiptapEditor.instance.destroy();
        } catch (e) {}
        window.TiptapEditor.instance = null;
    }

    window.TiptapEditor.filePath = null;
    window.TiptapEditor.originalContent = null;
    window.TiptapEditor.isActive = false;

    const container = document.getElementById('tiptap-editor');
    if (container) {
        container.innerHTML = '';
    }

    console.log('[Tiptap] Editor destroyed');
}

function showEditorUI() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

    if (previewContent) previewContent.style.display = 'none';
    if (tiptapContainer) tiptapContainer.style.display = 'flex';
    if (toolbar) toolbar.style.display = 'flex';
}

function hideEditorUI() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

    destroyTiptapEditor();

    if (previewContent) previewContent.style.display = 'block';
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
}

async function openMarkdownInEditor(content, filePath) {
    const modulesReady = await initTiptapModules();

    if (!modulesReady) {
        console.error('[Tiptap] Failed to load Tiptap modules');
        return false;
    }

    showEditorUI();
    return createTiptapEditor(content, filePath);
}

window.TiptapEditorModule = {
    initTiptapModules,
    createTiptapEditor,
    destroyTiptapEditor,
    saveTiptapContent,
    openMarkdownInEditor,
    showEditorUI,
    hideEditorUI,
    getTiptapMarkdown: function() {
        if (!window.TiptapEditor.instance) return null;
        try {
            return window.TiptapEditor.instance.storage.markdown.getMarkdown();
        } catch (e) {
            return null;
        }
    }
};
