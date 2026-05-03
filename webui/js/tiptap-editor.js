window.TiptapEditor = {
    instance: null,
    filePath: null,
    saveTimer: null,
    isActive: false,
    originalContent: null,
    modules: {},
    modulesReady: false,
    initPromise: null,
    toolbarBound: false,
    destroying: false,
    allTags: []
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
    if (window.TiptapEditor.toolbarBound) return;

    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    toolbar.addEventListener('click', (e) => {
        const btn = e.target.closest('.tiptap-btn[data-action]');
        if (!btn || btn.disabled) return;

        const action = btn.dataset.action;
        const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;
        executeTiptapAction(action, level);
    });

    window.TiptapEditor.toolbarBound = true;
}

function executeTiptapAction(action, level) {
    const editor = window.TiptapEditor.instance;
    if (!editor || window.TiptapEditor.destroying) return;

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
    if (!editor || window.TiptapEditor.destroying) return;

    const toolbar = document.getElementById('tiptap-toolbar');
    if (!toolbar) return;

    try {
        const buttons = toolbar.querySelectorAll('.tiptap-btn[data-action]');
        buttons.forEach(btn => {
            const action = btn.dataset.action;
            const level = btn.dataset.level ? parseInt(btn.dataset.level) : null;

            if (action === 'undo') {
                try { btn.disabled = !editor.can().undo(); } catch (e) { btn.disabled = false; }
            } else if (action === 'redo') {
                try { btn.disabled = !editor.can().redo(); } catch (e) { btn.disabled = false; }
            } else {
                btn.disabled = false;
            }

            let isActive = false;
            try {
                if (action === 'heading' && level) isActive = editor.isActive('heading', { level });
                else if (action === 'bulletList') isActive = editor.isActive('bulletList');
                else if (action === 'orderedList') isActive = editor.isActive('orderedList');
                else if (action === 'blockquote') isActive = editor.isActive('blockquote');
                else if (action === 'codeBlock') isActive = editor.isActive('codeBlock');
                else if (action === 'bold') isActive = editor.isActive('bold');
                else if (action === 'italic') isActive = editor.isActive('italic');
                else if (action === 'strike') isActive = editor.isActive('strike');
                else if (action === 'code') isActive = editor.isActive('code');
            } catch (e) {}

            if (isActive) btn.classList.add('active');
            else btn.classList.remove('active');
        });
    } catch (e) {}
}

function parseYamlFrontmatter(content) {
    var trimmed = content.replace(/^\uFEFF/, '');
    var match = trimmed.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
    if (!match) return { frontmatter: null, body: content };
    var yaml = match[1];
    var body = trimmed.slice(match[0].length);
    var props = {};
    var currentKey = null;
    var currentArr = null;
    yaml.split('\n').forEach(function(line) {
        if (line.match(/^\s+-\s+/)) {
            if (currentKey && currentArr) {
                currentArr.push(line.replace(/^\s+-\s+/, '').trim().replace(/^['"]|['"]$/g, ''));
            }
            return;
        }
        if (currentKey && currentArr) {
            props[currentKey] = currentArr;
            currentKey = null;
            currentArr = null;
        }
        var idx = line.indexOf(':');
        if (idx < 0) return;
        var key = line.slice(0, idx).trim();
        var val = line.slice(idx + 1).trim();
        if (!val) {
            currentKey = key;
            currentArr = [];
            return;
        }
        if (val.startsWith('[') && val.endsWith(']')) {
            val = val.slice(1, -1).split(',').map(function(s) { return s.trim().replace(/^['"]|['"]$/g, ''); });
        }
        props[key] = val;
    });
    if (currentKey && currentArr) {
        props[currentKey] = currentArr;
    }
    return { frontmatter: props, body: body };
}

function renderFrontmatterPanel(frontmatter) {
    if (!frontmatter) return '';
    var hideKeys = ['title'];
    var keys = Object.keys(frontmatter).filter(function(k) { return hideKeys.indexOf(k) < 0; });
    if (!keys.length) return '';
    var html = '<div class="obsidian-properties">';
    keys.forEach(function(key) {
        var val = frontmatter[key];
        html += '<div class="obsidian-prop-row">';
        html += '<span class="obsidian-prop-key">' + key + '</span>';
        if (Array.isArray(val) && val.length > 0) {
            html += '<span class="obsidian-prop-val obsidian-prop-tags">';
            val.forEach(function(item) {
                html += '<span class="obsidian-tag-chip">' + String(item).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') + '</span>';
            });
            html += '</span>';
        } else {
            var displayVal = val || '';
            html += '<span class="obsidian-prop-val" contenteditable="true" data-fm-key="' + key + '">' + displayVal + '</span>';
        }
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function createTiptapEditor(markdownContent, filePath) {
    const container = document.getElementById('tiptap-editor');
    if (!container) return false;

    if (window.TiptapEditor.instance) {
        destroyTiptapEditor();
    }

    const M = window.TiptapEditor.modules;
    if (!M.Editor || !M.StarterKit || !M.Markdown) return false;

    container.innerHTML = '';

    var parsed = parseYamlFrontmatter(markdownContent);
    var fmHtml = renderFrontmatterPanel(parsed.frontmatter);

    var fmContainer = document.getElementById('frontmatter-panel');
    if (fmContainer) {
        fmContainer.innerHTML = fmHtml;
        fmContainer.style.display = fmHtml ? 'block' : 'none';
        fmContainer.querySelectorAll('.obsidian-prop-val[contenteditable]').forEach(function(el) {
            el.addEventListener('blur', function() {
                var key = this.getAttribute('data-fm-key');
                var newVal = this.textContent.trim();
                if (key && window.TiptapEditor.frontmatterData) {
                    var origVal = window.TiptapEditor.frontmatterData[key];
                    if (Array.isArray(origVal)) {
                        window.TiptapEditor.frontmatterData[key] = newVal.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
                    } else {
                        window.TiptapEditor.frontmatterData[key] = newVal;
                    }
                    saveTiptapContent();
                }
            });
            el.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.blur();
                }
            });
        });

        fmContainer.querySelectorAll('.obsidian-prop-tags').forEach(function(el) {
            el.addEventListener('dblclick', function() {
                var key = el.previousElementSibling;
                var keyName = key ? key.textContent.trim() : '';
                if (!keyName || !window.TiptapEditor.frontmatterData) return;
                var origVal = window.TiptapEditor.frontmatterData[keyName];
                if (!Array.isArray(origVal)) return;
                el.innerHTML = '';
                el.textContent = origVal.join(', ');
                el.classList.remove('obsidian-prop-tags');
                el.setAttribute('contenteditable', 'true');
                el.setAttribute('data-fm-key', keyName);
                el.focus();
                var range = document.createRange();
                range.selectNodeContents(el);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                setupTagAutocomplete(el, keyName);
            });
            el.addEventListener('blur', function() {
                var key = this.getAttribute('data-fm-key');
                var newVal = this.textContent.trim();
                if (key && window.TiptapEditor.frontmatterData) {
                    var origVal = window.TiptapEditor.frontmatterData[key];
                    if (Array.isArray(origVal)) {
                        window.TiptapEditor.frontmatterData[key] = newVal.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
                    } else {
                        window.TiptapEditor.frontmatterData[key] = newVal;
                    }
                    saveTiptapContent();
                    var fmContainer = document.getElementById('frontmatter-panel');
                    if (fmContainer) {
                        fmContainer.innerHTML = renderFrontmatterPanel(window.TiptapEditor.frontmatterData);
                        fmContainer.style.display = fmContainer.innerHTML ? 'block' : 'none';
                        bindFrontmatterEvents(fmContainer);
                    }
                }
            });
        });
    }

    window.TiptapEditor.filePath = filePath;
    window.TiptapEditor.originalContent = markdownContent;
    window.TiptapEditor.frontmatterData = parsed.frontmatter;
    window.TiptapEditor.isActive = true;
    window.TiptapEditor.destroying = false;

    try {
        const extensions = [
            M.StarterKit.configure({
                heading: { levels: [1, 2, 3, 4, 5, 6] }
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
            content: parsed.body || '',
            editorProps: {
                attributes: {
                    class: 'tiptap-prose',
                    spellcheck: 'true'
                }
            },
            onUpdate: ({ editor }) => {
                if (window.TiptapEditor.destroying) return;
                if (window.TiptapEditor.saveTimer) {
                    clearTimeout(window.TiptapEditor.saveTimer);
                }
                window.TiptapEditor.saveTimer = setTimeout(() => {
                    saveTiptapContent();
                }, 1000);
            },
            onSelectionUpdate: () => {
                if (!window.TiptapEditor.destroying) {
                    updateTiptapToolbarState();
                }
            }
        });

        bindTiptapToolbarEvents();
        updateTiptapToolbarState();

        console.log('[Tiptap] Editor created for:', filePath);
        return true;
    } catch (e) {
        console.error('[Tiptap] Failed to create editor:', e);
        window.TiptapEditor.isActive = false;
        return false;
    }
}

async function saveTiptapContent() {
    if (!window.TiptapEditor.instance || !window.TiptapEditor.filePath || window.TiptapEditor.destroying) {
        return;
    }

    try {
        var markdown = window.TiptapEditor.instance.storage.markdown.getMarkdown();
        var fmContainer = document.getElementById('frontmatter-panel');
        if (fmContainer && fmContainer.style.display !== 'none') {
            var fmData = window.TiptapEditor.frontmatterData;
            if (fmData && Object.keys(fmData).length > 0) {
                var yaml = '---\n';
                Object.keys(fmData).forEach(function(key) {
                    var val = fmData[key];
                    if (Array.isArray(val)) {
                        yaml += key + ':\n';
                        val.forEach(function(item) { yaml += '  - ' + item + '\n'; });
                    } else {
                        yaml += key + ': ' + val + '\n';
                    }
                });
                yaml += '---\n';
                markdown = yaml + markdown;
            }
        }
        const result = await window.api.save_note_file(window.TiptapEditor.filePath, markdown);

        if (result && result.success) {
            window.TiptapEditor.originalContent = markdown;
        }
    } catch (e) {
        console.error('[Tiptap] Save error:', e);
    }
}

function destroyTiptapEditor() {
    if (window.TiptapEditor.destroying) return;
    window.TiptapEditor.destroying = true;

    if (window.TiptapEditor.saveTimer) {
        clearTimeout(window.TiptapEditor.saveTimer);
        window.TiptapEditor.saveTimer = null;
    }

    if (window.TiptapEditor.instance) {
        try {
            window.TiptapEditor.instance.destroy();
        } catch (e) {
            console.error('[Tiptap] Destroy error:', e);
        }
        window.TiptapEditor.instance = null;
    }

    window.TiptapEditor.filePath = null;
    window.TiptapEditor.originalContent = null;
    window.TiptapEditor.isActive = false;
    window.TiptapEditor.destroying = false;

    const container = document.getElementById('tiptap-editor');
    if (container) {
        container.innerHTML = '';
    }
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
    destroyTiptapEditor();

    const previewContent = document.getElementById('preview-content');
    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');

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

function setupTagAutocomplete(el, keyName) {
    if (keyName !== 'tags') return;

    loadAllTags();

    var dropdown = document.createElement('div');
    dropdown.className = 'tag-autocomplete-dropdown';
    dropdown.style.display = 'none';
    el.parentNode.style.position = 'relative';
    el.parentNode.appendChild(dropdown);

    function updateDropdown() {
        var text = el.textContent.trim();
        var parts = text.split(',').map(function(s) { return s.trim(); });
        var currentPart = parts[parts.length - 1].toLowerCase();

        if (!currentPart) {
            dropdown.style.display = 'none';
            return;
        }

        var existing = parts.slice(0, -1).map(function(s) { return s.toLowerCase(); });
        var matches = window.TiptapEditor.allTags.filter(function(tag) {
            return tag.toLowerCase().indexOf(currentPart) >= 0 &&
                existing.indexOf(tag.toLowerCase()) < 0;
        }).slice(0, 8);

        if (matches.length === 0) {
            dropdown.style.display = 'none';
            return;
        }

        dropdown.innerHTML = matches.map(function(tag) {
            return '<div class="tag-autocomplete-item" data-tag="' + tag.replace(/"/g, '&quot;') + '">' + tag.replace(/</g, '&lt;') + '</div>';
        }).join('');
        dropdown.style.display = 'block';

        dropdown.querySelectorAll('.tag-autocomplete-item').forEach(function(item) {
            item.addEventListener('mousedown', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var selectedTag = this.getAttribute('data-tag');
                parts[parts.length - 1] = selectedTag;
                el.textContent = parts.join(', ') + ', ';
                dropdown.style.display = 'none';
                var range = document.createRange();
                range.selectNodeContents(el);
                range.collapse(false);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            });
        });
    }

    el.addEventListener('input', updateDropdown);

    el.addEventListener('keydown', function(e) {
        if (e.key === 'Tab' && dropdown.style.display !== 'none') {
            e.preventDefault();
            var first = dropdown.querySelector('.tag-autocomplete-item');
            if (first) {
                first.dispatchEvent(new MouseEvent('mousedown'));
            }
        }
    });

    el.addEventListener('blur', function() {
        setTimeout(function() { dropdown.remove(); }, 200);
    });
}

async function loadAllTags() {
    if (window.TiptapEditor.allTags.length > 0) return;
    try {
        var result = await window.api.get_all_tags();
        if (result && result.tags) {
            window.TiptapEditor.allTags = result.tags.map(function(t) { return t.name; });
        }
    } catch (e) {
        console.error('[Tiptap] load tags error:', e);
    }
}

function bindFrontmatterEvents(fmContainer) {
    fmContainer.querySelectorAll('.obsidian-prop-val[contenteditable]').forEach(function(el) {
        el.addEventListener('blur', function() {
            var key = this.getAttribute('data-fm-key');
            var newVal = this.textContent.trim();
            if (key && window.TiptapEditor.frontmatterData) {
                var origVal = window.TiptapEditor.frontmatterData[key];
                if (Array.isArray(origVal)) {
                    window.TiptapEditor.frontmatterData[key] = newVal.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
                } else {
                    window.TiptapEditor.frontmatterData[key] = newVal;
                }
                saveTiptapContent();
            }
        });
        el.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.blur();
            }
        });
    });

    fmContainer.querySelectorAll('.obsidian-prop-tags').forEach(function(el) {
        el.addEventListener('dblclick', function() {
            var key = el.previousElementSibling;
            var keyName = key ? key.textContent.trim() : '';
            if (!keyName || !window.TiptapEditor.frontmatterData) return;
            var origVal = window.TiptapEditor.frontmatterData[keyName];
            if (!Array.isArray(origVal)) return;
            el.innerHTML = '';
            el.textContent = origVal.join(', ');
            el.classList.remove('obsidian-prop-tags');
            el.setAttribute('contenteditable', 'true');
            el.setAttribute('data-fm-key', keyName);
            el.focus();
            var range = document.createRange();
            range.selectNodeContents(el);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            setupTagAutocomplete(el, keyName);
        });
        el.addEventListener('blur', function() {
            var key = this.getAttribute('data-fm-key');
            var newVal = this.textContent.trim();
            if (key && window.TiptapEditor.frontmatterData) {
                var origVal = window.TiptapEditor.frontmatterData[key];
                if (Array.isArray(origVal)) {
                    window.TiptapEditor.frontmatterData[key] = newVal.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
                } else {
                    window.TiptapEditor.frontmatterData[key] = newVal;
                }
                saveTiptapContent();
                var fmC = document.getElementById('frontmatter-panel');
                if (fmC) {
                    fmC.innerHTML = renderFrontmatterPanel(window.TiptapEditor.frontmatterData);
                    fmC.style.display = fmC.innerHTML ? 'block' : 'none';
                    bindFrontmatterEvents(fmC);
                }
            }
        });
    });
}

window.TiptapEditorModule = {
    initTiptapModules,
    createTiptapEditor,
    destroyTiptapEditor,
    saveTiptapContent,
    openMarkdownInEditor,
    showEditorUI,
    hideEditorUI,
    preloadModules: function() {
        initTiptapModules();
    },
    getTiptapMarkdown: function() {
        if (!window.TiptapEditor.instance) return null;
        try {
            return window.TiptapEditor.instance.storage.markdown.getMarkdown();
        } catch (e) {
            return null;
        }
    }
};
