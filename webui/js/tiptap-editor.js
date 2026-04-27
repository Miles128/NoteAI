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
                    { TaskList },
                    { TaskItem },
                    { Link }
                ] = await Promise.all([
                    import('https://esm.sh/@tiptap/core@2.6.6'),
                    import('https://esm.sh/@tiptap/starter-kit@2.6.6'),
                    import('https://esm.sh/tiptap-markdown@0.8.0'),
                    import('https://esm.sh/@tiptap/extension-highlight@2.6.6'),
                    import('https://esm.sh/@tiptap/extension-code-block-lowlight@2.6.6'),
                    import('https://esm.sh/lowlight@3.1.0'),
                    import('https://esm.sh/@tiptap/extension-image@2.6.6'),
                    import('https://esm.sh/@tiptap/extension-task-list@2.6.6'),
                    import('https://esm.sh/@tiptap/extension-task-item@2.6.6'),
                    import('https://esm.sh/@tiptap/extension-link@2.6.6')
                ]);

                const allLangs = {
                    css: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/css.js')).default,
                    js: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/javascript.js')).default,
                    ts: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/typescript.js')).default,
                    python: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/python.js')).default,
                    json: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/json.js')).default,
                    xml: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/xml.js')).default,
                    markdown: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/markdown.js')).default,
                    bash: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/bash.js')).default,
                    sql: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/sql.js')).default,
                    rust: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/rust.js')).default,
                    java: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/java.js')).default,
                    cpp: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/cpp.js')).default,
                    go: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/go.js')).default,
                    yaml: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/yaml.js')).default,
                    ini: (await import('https://esm.sh/highlight.js@11.9.0/lib/languages/ini.js')).default
                };

                for (const [name, lang] of Object.entries(allLangs)) {
                    try {
                        lowlight.registerLanguage(name, lang);
                    } catch (e) {}
                }

                window.TiptapModule.modules = {
                    Editor,
                    StarterKit,
                    Markdown,
                    Highlight,
                    CodeBlockLowlight,
                    lowlight,
                    Image,
                    TaskList,
                    TaskItem,
                    Link
                };

                window.TiptapModule.isReady = true;
                window.TiptapModule.resolveReady(true);
                window.dispatchEvent(new CustomEvent('tiptap-ready'));
                console.log('[Tiptap] All modules loaded successfully');
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
        e.stopPropagation();
        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
        executeTiptapAction(action, level);
    });

    window.TiptapEditor.eventsBound = true;
    console.log('[Tiptap] Toolbar events bound');
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

    try {
        const buttons = toolbar.querySelectorAll('.tiptap-btn[data-action]');
        buttons.forEach(btn => {
            const action = btn.dataset.action;
            const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;

            if (action === 'undo') {
                btn.disabled = !editor.can().undo();
                return;
            }
            if (action === 'redo') {
                btn.disabled = !editor.can().redo();
                return;
            }

            btn.disabled = false;

            let isActive = false;
            if (action === 'heading' && level) {
                isActive = editor.isActive('heading', { level });
            } else if (action === 'bulletList') {
                isActive = editor.isActive('bulletList');
            } else if (action === 'orderedList') {
                isActive = editor.isActive('orderedList');
            } else if (action === 'taskList') {
                isActive = editor.isActive('taskList');
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
            } else if (action === 'link') {
                isActive = editor.isActive('link');
            }

            if (isActive) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    } catch (e) {
        console.error('[Tiptap] Toolbar state update error:', e);
    }
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
                },
                codeBlock: false
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
            M.Link.configure({
                openOnClick: false,
                HTMLAttributes: {
                    rel: 'noopener noreferrer',
                    target: '_blank'
                }
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

        bindTiptapToolbarEventsOnce();
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
