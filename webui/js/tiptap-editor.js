window.TiptapModule = {
    isReady: false,
    readyPromise: null,
    modules: {},
    resolveReady: null
};

window.TiptapModule.readyPromise = new Promise((resolve) => {
    window.TiptapModule.resolveReady = resolve;
});

window.TiptapEditor = {
    instance: null,
    filePath: null,
    saveTimer: null,
    isActive: false,
    originalContent: null,
    eventsBound: false
};

function loadTiptapModules() {
    if (window.TiptapModule.isReady) {
        return window.TiptapModule.readyPromise;
    }

    const script = document.createElement('script');
    script.type = 'module';
    script.textContent = `
        (async () => {
            try {
                const [
                    { Editor },
                    { default: StarterKit },
                    { Markdown },
                    { Highlight },
                    { CodeBlockLowlight },
                    { default: lowlight },
                    { Image },
                    { ListItem },
                    { TaskList },
                    { TaskItem }
                ] = await Promise.all([
                    import('https://esm.sh/@tiptap/core'),
                    import('https://esm.sh/@tiptap/starter-kit'),
                    import('https://esm.sh/tiptap-markdown'),
                    import('https://esm.sh/@tiptap/extension-highlight'),
                    import('https://esm.sh/@tiptap/extension-code-block-lowlight'),
                    import('https://esm.sh/lowlight/lib/common.js'),
                    import('https://esm.sh/@tiptap/extension-image'),
                    import('https://esm.sh/@tiptap/extension-list-item'),
                    import('https://esm.sh/@tiptap/extension-task-list'),
                    import('https://esm.sh/@tiptap/extension-task-item')
                ]);

                window.TiptapModule.modules = {
                    Editor,
                    StarterKit,
                    Markdown,
                    Highlight,
                    CodeBlockLowlight,
                    lowlight,
                    Image,
                    ListItem,
                    TaskList,
                    TaskItem
                };

                window.TiptapModule.isReady = true;
                window.TiptapModule.resolveReady(true);
                window.dispatchEvent(new CustomEvent('tiptap-ready'));
                console.log('[Tiptap] Modules loaded successfully');
            } catch (e) {
                console.error('[Tiptap] Failed to load modules:', e);
                window.TiptapModule.resolveReady(false);
            }
        })();
    `;
    document.head.appendChild(script);

    return window.TiptapModule.readyPromise;
}

function bindTiptapToolbarEventsOnce() {
    if (window.TiptapEditor.eventsBound) {
        return;
    }

    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    toolbar.addEventListener('click', (e) => {
        const btn = e.target.closest('.tiptap-btn[data-action]');
        if (!btn || btn.disabled) return;

        e.preventDefault();
        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
        executeTiptapAction(action, level);
    });

    window.TiptapEditor.eventsBound = true;
    console.log('[Tiptap] Toolbar events bound');
}

function executeTiptapAction(action, level) {
    const editor = window.TiptapEditor.instance;
    if (!editor) return;

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
        case 'taskList':
            editor.chain().focus().toggleTaskList().run();
            break;
        case 'blockquote':
            editor.chain().focus().toggleBlockquote().run();
            break;
        case 'codeBlock':
            editor.chain().focus().toggleCodeBlock().run();
            break;
        case 'link':
            const url = prompt('输入链接 URL:', 'https://');
            if (url) {
                editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
            }
            break;
        case 'image':
            insertTiptapImage();
            break;
        case 'undo':
            if (editor.can().undo()) {
                editor.chain().focus().undo().run();
            }
            break;
        case 'redo':
            if (editor.can().redo()) {
                editor.chain().focus().redo().run();
            }
            break;
    }

    updateTiptapToolbarState();
}

function insertTiptapImage() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const base64 = event.target.result;
            const editor = window.TiptapEditor.instance;
            if (editor) {
                editor.chain().focus().setImage({ src: base64 }).run();
            }
        };
        reader.readAsDataURL(file);
    };
    input.click();
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
            btn.disabled = !editor.can().undo();
        } else if (action === 'redo') {
            btn.disabled = !editor.can().redo();
        } else {
            btn.disabled = false;
        }

        let isActive = false;
        if (action === 'heading' && level) {
            isActive = editor.isActive('heading', { level });
        } else if (action !== 'undo' && action !== 'redo') {
            isActive = editor.isActive(action);
        }

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

    window.TiptapEditor.filePath = filePath;
    window.TiptapEditor.originalContent = markdownContent;
    window.TiptapEditor.isActive = true;

    const M = window.TiptapModule.modules;

    if (!M.Editor || !M.StarterKit || !M.Markdown) {
        console.error('[Tiptap] Required modules not available');
        return false;
    }

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
                breaks: true,
                transformPastedText: true
            }),
            M.Highlight,
            M.CodeBlockLowlight.configure({
                lowlight: M.lowlight
            }),
            M.Image.configure({
                inline: true,
                allowBase64: true
            }),
            M.TaskList,
            M.TaskItem.configure({
                nested: true
            }),
            M.ListItem
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

        bindTiptapToolbarEventsOnce();
        updateTiptapToolbarState();

        console.log('[Tiptap] Editor created for:', filePath, 'content length:', (markdownContent || '').length);
        return true;
    } catch (e) {
        console.error('[Tiptap] Failed to create editor:', e);
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
        window.TiptapEditor.instance.destroy();
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

function getTiptapMarkdown() {
    if (!window.TiptapEditor.instance) {
        return null;
    }
    return window.TiptapEditor.instance.storage.markdown.getMarkdown();
}

function showTiptapEditor() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');
    const editBtn = document.getElementById('titlebar-split-btn');

    if (previewContent) previewContent.style.display = 'none';
    if (tiptapContainer) tiptapContainer.style.display = 'flex';
    if (toolbar) toolbar.style.display = 'flex';
    if (editBtn) editBtn.style.display = 'none';
}

function hideTiptapEditor() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

    destroyTiptapEditor();

    if (previewContent) previewContent.style.display = 'block';
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
}

async function openMarkdownInEditor(content, filePath) {
    const ready = await loadTiptapModules();

    if (!ready) {
        console.error('[Tiptap] Failed to load Tiptap modules');
        return false;
    }

    showTiptapEditor();
    return createTiptapEditor(content, filePath);
}

window.TiptapEditorModule = {
    loadTiptapModules,
    createTiptapEditor,
    destroyTiptapEditor,
    saveTiptapContent,
    getTiptapMarkdown,
    openMarkdownInEditor,
    showTiptapEditor,
    hideTiptapEditor
};
