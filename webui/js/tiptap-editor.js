window.TiptapEditor = {
    editor: null,
    filePath: null,
    saveTimer: null,
    isActive: false,
    originalContent: null,
    initPromise: null,
    isInitialized: false
};

function initTiptapEditor() {
    if (window.TiptapEditor.isInitialized) {
        return window.TiptapEditor.initPromise;
    }

    window.TiptapEditor.initPromise = (async () => {
        if (window.TiptapLoader && window.TiptapLoader.ready) {
            window.TiptapEditor.isInitialized = true;
            return true;
        }

        if (window.TiptapLoader && window.TiptapLoader.initPromise) {
            await window.TiptapLoader.initPromise;
            if (window.TiptapLoader.ready) {
                window.TiptapEditor.isInitialized = true;
                return true;
            }
        }

        return new Promise((resolve) => {
            const checkInterval = setInterval(() => {
                if (window.TiptapLoader && window.TiptapLoader.ready) {
                    clearInterval(checkInterval);
                    window.TiptapEditor.isInitialized = true;
                    resolve(true);
                }
            }, 100);

            setTimeout(() => {
                clearInterval(checkInterval);
                console.warn('[Tiptap] Editor load timeout');
                resolve(false);
            }, 10000);
        });
    })();

    return window.TiptapEditor.initPromise;
}

function createTiptapEditor(content, filePath) {
    const container = document.getElementById('tiptap-editor');
    if (!container) {
        console.error('[Tiptap] Editor container not found');
        return false;
    }

    if (window.TiptapEditor.editor) {
        destroyTiptapEditor();
    }

    window.TiptapEditor.filePath = filePath;
    window.TiptapEditor.originalContent = content;
    window.TiptapEditor.isActive = true;

    try {
        const L = window.TiptapLoader;

        if (!L.Editor || !L.StarterKit || !L.Markdown) {
            console.error('[Tiptap] Required modules not loaded');
            return false;
        }

        const extensions = [
            L.StarterKit.configure({
                heading: {
                    levels: [1, 2, 3, 4, 5, 6]
                },
                codeBlock: false
            }),
            L.Markdown.configure({
                html: true,
                tightLists: true,
                bulletListMarker: '-',
                linkify: false,
                breaks: true,
                transformPastedText: true
            }),
            L.Highlight,
            L.CodeBlockLowlight.configure({
                lowlight: L.lowlight
            }),
            L.Image.configure({
                inline: true,
                allowBase64: true
            }),
            L.TaskList,
            L.TaskItem.configure({
                nested: true,
                HTMLAttributes: {
                    class: 'task-item'
                }
            }),
            L.ListItem
        ];

        window.TiptapEditor.editor = new L.Editor({
            element: container,
            extensions: extensions,
            content: content,
            contentType: 'markdown',
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
            onSelectionUpdate: ({ editor }) => {
                updateToolbarState(editor);
            },
            onFocus: () => {
                const toolbar = document.getElementById('tiptap-toolbar');
                if (toolbar) toolbar.classList.add('active');
            },
            onBlur: () => {
                const toolbar = document.getElementById('tiptap-toolbar');
                if (toolbar) toolbar.classList.remove('active');
            }
        });

        setupToolbarEvents();
        updateToolbarState(window.TiptapEditor.editor);

        console.log('[Tiptap] Editor initialized for:', filePath);
        return true;
    } catch (e) {
        console.error('[Tiptap] Failed to create editor:', e);
        return false;
    }
}

function setupToolbarEvents() {
    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    const buttons = toolbar.querySelectorAll('.tiptap-btn[data-action]');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.dataset.action;
            const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
            executeToolbarAction(action, level);
        });
    });
}

function executeToolbarAction(action, level) {
    const editor = window.TiptapEditor.editor;
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
            insertImage();
            break;
        case 'undo':
            editor.chain().focus().undo().run();
            break;
        case 'redo':
            editor.chain().focus().redo().run();
            break;
    }

    updateToolbarState(editor);
}

function insertImage() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const base64 = event.target.result;
            const editor = window.TiptapEditor.editor;
            if (editor) {
                editor.chain().focus().setImage({ src: base64 }).run();
            }
        };
        reader.readAsDataURL(file);
    };
    input.click();
}

function updateToolbarState(editor) {
    if (!editor) return;

    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    const states = {
        bold: editor.isActive('bold'),
        italic: editor.isActive('italic'),
        strike: editor.isActive('strike'),
        code: editor.isActive('code'),
        heading1: editor.isActive('heading', { level: 1 }),
        heading2: editor.isActive('heading', { level: 2 }),
        heading3: editor.isActive('heading', { level: 3 }),
        bulletList: editor.isActive('bulletList'),
        orderedList: editor.isActive('orderedList'),
        taskList: editor.isActive('taskList'),
        blockquote: editor.isActive('blockquote'),
        codeBlock: editor.isActive('codeBlock'),
        link: editor.isActive('link'),
        canUndo: editor.can().undo(),
        canRedo: editor.can().redo()
    };

    const buttons = toolbar.querySelectorAll('.tiptap-btn[data-action]');
    buttons.forEach(btn => {
        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
        let isActive = false;

        if (action === 'heading' && level) {
            isActive = states[`heading${level}`];
        } else {
            isActive = states[action];
        }

        if (isActive) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }

        if (action === 'undo') {
            btn.disabled = !states.canUndo;
        } else if (action === 'redo') {
            btn.disabled = !states.canRedo;
        }
    });
}

async function saveTiptapContent() {
    if (!window.TiptapEditor.editor || !window.TiptapEditor.filePath) {
        return;
    }

    try {
        const markdown = window.TiptapEditor.editor.storage.markdown.getMarkdown();
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

    if (window.TiptapEditor.editor) {
        saveTiptapContent();
        window.TiptapEditor.editor.destroy();
        window.TiptapEditor.editor = null;
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
    if (!window.TiptapEditor.editor) {
        return null;
    }
    return window.TiptapEditor.editor.storage.markdown.getMarkdown();
}

function enterTiptapEditMode(content, filePath) {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

    if (previewContent) previewContent.style.display = 'none';
    if (tiptapContainer) tiptapContainer.style.display = 'flex';
    if (toolbar) toolbar.style.display = 'flex';

    return createTiptapEditor(content, filePath);
}

function exitTiptapEditMode() {
    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

    destroyTiptapEditor();

    if (previewContent) previewContent.style.display = 'block';
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
}

window.TiptapEditorModule = {
    initTiptapEditor,
    createTiptapEditor,
    destroyTiptapEditor,
    saveTiptapContent,
    getTiptapMarkdown,
    enterTiptapEditMode,
    exitTiptapEditMode
};
