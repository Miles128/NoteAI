// ================================================================
// Tiptap 编辑器 - Markdown WYSIWYG
// 依赖: webui/lib/tiptap-bundle.js (通过 esbuild 从 npm 打包, 导出 window.TiptapModules)
// ================================================================

;(function() {
    'use strict';

    var SAVE_DELAY_MS = 1000;

    function updateSaveStatus(status, text) {
        var statusEl = document.getElementById('editor-status-bar');
        if (!statusEl) return;
        statusEl.className = 'editor-status-bar ' + (status || '');
        statusEl.textContent = text || '';
    }

    function getActiveFilePath() {
        return TiptapEditor.filePath || (window.AppState && window.AppState.selectedFilePath) || null;
    }

    function refreshPreviewState(content) {
        if (window.PreviewModule && window.PreviewModule.currentPreviewData) {
            window.PreviewModule.currentPreviewData.content = content;
        }
    }

    var TiptapEditor = {
        editor: null,
        instance: null,
        filePath: null,
        originalContent: '',
        saveTimer: null,
        savePromise: null,
        fallbackTextarea: null,
        isActive: false,

        getModules: function() {
            if (window.TiptapModules) {
                return {
                    Editor: window.TiptapModules.Editor,
                    StarterKit: window.TiptapModules.StarterKit,
                    Markdown: window.TiptapModules.Markdown,
                };
            }
            return null;
        },

        init: function(editorEl, content, filePath, callback) {
            var self = this;
            if (!editorEl) {
                console.error('[Tiptap] No editor element provided');
                return false;
            }

            this.filePath = filePath || null;
            this.originalContent = content || '';
            this.fallbackTextarea = null;

            var modules = this.getModules();
            if (!modules) {
                console.error('[Tiptap] Failed to load modules: TiptapModules not found');
                this._createTextareaFallback(editorEl, content || '');
                return true;
            }

            if (this.editor) {
                this.editor.destroy();
                this.editor = null;
            }

            try {
                this.editor = new modules.Editor({
                    element: editorEl,
                    extensions: [
                        modules.StarterKit.configure({
                            codeBlock: {
                                HTMLAttributes: { class: 'language-javascript' },
                            },
                        }),
                        modules.Markdown.configure({
                            html: true,
                        }),
                    ],
                    content: content || '',
                    autofocus: false,
                    editorProps: {
                        attributes: {
                            class: 'tiptap-prose',
                        },
                    },
                    onUpdate: function(_ref) {
                        var md = self.getContent();
                        if (md && window.updateYamlFrontMatter) {
                            window.updateYamlFrontMatter(md);
                        }
                        if (!window._rewritingFilePath) {
                            self.scheduleAutoSave(md || '');
                        }
                        if (callback) {
                            callback(md || '');
                        }
                    },
                    onSelectionUpdate: function() {
                        self.updateToolbarState();
                    },
                    onFocus: function() {
                        self.updateToolbarState();
                    },
                });
                this.instance = this.editor;
                this.isActive = true;
            } catch (e) {
                console.error('[Tiptap] Init error:', e.message || e);
                this._createTextareaFallback(editorEl, content || '');
                return true;
            }

            this.bindToolbar();
            this.updateToolbarState();
            updateSaveStatus('saved', '已保存');
            return true;
        },

        getContent: function() {
            if (this.editor) {
                try {
                    if (this.editor.storage && this.editor.storage.markdown) {
                        return this.editor.storage.markdown.getMarkdown();
                    }
                } catch (e) {
                    console.warn('[Tiptap] getContent error:', e);
                }
            }
            if (this.fallbackTextarea) {
                return this.fallbackTextarea.value;
            }
            return null;
        },

        setContent: function(content) {
            if (this.editor) {
                try {
                    this.editor.commands.setContent(content);
                } catch (e) {
                    console.warn('[Tiptap] setContent error:', e);
                }
            } else if (this.fallbackTextarea) {
                this.fallbackTextarea.value = content || '';
            }
        },

        setEditable: function(editable) {
            if (this.editor) {
                this.editor.setEditable(editable);
            } else if (this.fallbackTextarea) {
                this.fallbackTextarea.disabled = !editable;
            }
        },

        focus: function() {
            if (this.editor) {
                this.editor.commands.focus();
            } else if (this.fallbackTextarea) {
                this.fallbackTextarea.focus();
            }
        },

        destroy: async function() {
            await this.flushSave();
            if (this.editor) {
                this.editor.destroy();
                this.editor = null;
                this.instance = null;
            }
            this.fallbackTextarea = null;
            this.filePath = null;
            this.originalContent = '';
            this.isActive = false;
        },

        _createTextareaFallback: function(editorEl, content) {
            var self = this;
            var ta = document.createElement('textarea');
            ta.className = 'tiptap-fallback';
            ta.value = content || '';
            ta.style.cssText = 'width:100%;height:100%;border:none;padding:12px;font-family:monospace;font-size:14px;resize:none;background:var(--bg, #fff);color:var(--text, #333);';
            ta.addEventListener('input', function() {
                self.scheduleAutoSave(ta.value);
            });
            editorEl.innerHTML = '';
            editorEl.appendChild(ta);
            this.fallbackTextarea = ta;
            this.isActive = true;
            updateSaveStatus('saved', '已保存(简易模式)');
        },

        scheduleAutoSave: function(content) {
            var self = this;
            if (this.saveTimer) {
                clearTimeout(this.saveTimer);
            }
            updateSaveStatus('saving', '有未保存更改...');
            this.saveTimer = setTimeout(function() {
                self.performSave(content);
            }, SAVE_DELAY_MS);
        },

        flushSave: async function() {
            if (this.saveTimer) {
                clearTimeout(this.saveTimer);
                this.saveTimer = null;
            }
            var content = this.getContent();
            if (content !== null && content !== this.originalContent) {
                await this.performSave(content);
            } else if (this.savePromise) {
                await this.savePromise;
            }
        },

        performSave: async function(content) {
            var filePath = getActiveFilePath();
            if (!filePath || !window.api || !window.api.saveFileContent) return;

            while (this.savePromise) {
                await this.savePromise;
            }

            var self = this;
            this.savePromise = (async function() {
                updateSaveStatus('saving', '保存中...');
                try {
                    var result = await window.api.saveFileContent(filePath, content);
                    if (result && result.success) {
                        self.originalContent = content;
                        refreshPreviewState(content);
                        updateSaveStatus('saved', '已保存');
                    } else {
                        updateSaveStatus('error', '保存失败');
                    }
                } catch (e) {
                    updateSaveStatus('error', '保存失败');
                } finally {
                    self.savePromise = null;
                }
            })();

            await this.savePromise;
        },

        bindToolbar: function() {
            var self = this;
            var toolbar = document.getElementById('tiptap-toolbar');
            if (!toolbar || toolbar.dataset.bound === 'true') return;
            toolbar.dataset.bound = 'true';
            toolbar.addEventListener('click', function(event) {
                var btn = event.target.closest('.tiptap-btn[data-action]');
                if (!btn || btn.disabled) return;
                event.preventDefault();
                self.runToolbarAction(btn);
            });
        },

        runToolbarAction: function(btn) {
            if (!this.editor) return;
            var action = btn.dataset.action;
            var level = parseInt(btn.dataset.level || '0', 10);
            var chain = this.editor.chain().focus();

            try {
                if (action === 'bold') chain.toggleBold().run();
                else if (action === 'italic') chain.toggleItalic().run();
                else if (action === 'strike') chain.toggleStrike().run();
                else if (action === 'code') chain.toggleCode().run();
                else if (action === 'heading') chain.toggleHeading({ level: level || 1 }).run();
                else if (action === 'bulletList') chain.toggleBulletList().run();
                else if (action === 'orderedList') chain.toggleOrderedList().run();
                else if (action === 'blockquote') chain.toggleBlockquote().run();
                else if (action === 'codeBlock') chain.toggleCodeBlock().run();
                else if (action === 'undo') chain.undo().run();
                else if (action === 'redo') chain.redo().run();
            } catch (e) {
                console.warn('[Tiptap] toolbar action failed:', action, e);
            }
            this.updateToolbarState();
        },

        updateToolbarState: function() {
            if (!this.editor) return;
            var self = this;
            var unsupported = { taskList: true, link: true, image: true };
            document.querySelectorAll('#tiptap-toolbar .tiptap-btn[data-action]').forEach(function(btn) {
                var action = btn.dataset.action;
                var level = parseInt(btn.dataset.level || '0', 10);
                btn.disabled = !!unsupported[action];
                btn.classList.remove('active');
                if (action === 'bold' && self.editor.isActive('bold')) btn.classList.add('active');
                if (action === 'italic' && self.editor.isActive('italic')) btn.classList.add('active');
                if (action === 'strike' && self.editor.isActive('strike')) btn.classList.add('active');
                if (action === 'code' && self.editor.isActive('code')) btn.classList.add('active');
                if (action === 'heading' && self.editor.isActive('heading', { level: level || 1 })) btn.classList.add('active');
                if (action === 'bulletList' && self.editor.isActive('bulletList')) btn.classList.add('active');
                if (action === 'orderedList' && self.editor.isActive('orderedList')) btn.classList.add('active');
                if (action === 'blockquote' && self.editor.isActive('blockquote')) btn.classList.add('active');
                if (action === 'codeBlock' && self.editor.isActive('codeBlock')) btn.classList.add('active');
            });
        },
    };

    var TiptapEditorModule = {
        openMarkdownInEditor: async function(content, path) {
            var tiptapContainer = document.getElementById('tiptap-editor-container');
            var toolbar = document.getElementById('tiptap-toolbar');
            var previewContent = document.getElementById('preview-content');
            var splitBtn = document.getElementById('titlebar-split-btn');
            var editorEl = document.getElementById('tiptap-editor');

            if (tiptapContainer) tiptapContainer.style.display = 'flex';
            if (toolbar) toolbar.style.display = 'flex';
            if (previewContent) previewContent.style.display = 'none';
            if (splitBtn) splitBtn.classList.add('active');

            return new Promise(function(resolve) {
                if (!editorEl) {
                    resolve(false);
                    return;
                }
                resolve(TiptapEditor.init(editorEl, content, path, function() {}));
            });
        },

        hideEditorUI: async function() {
            await TiptapEditor.destroy();

            var tiptapContainer = document.getElementById('tiptap-editor-container');
            var toolbar = document.getElementById('tiptap-toolbar');
            var previewContent = document.getElementById('preview-content');

            if (tiptapContainer) tiptapContainer.style.display = 'none';
            if (toolbar) toolbar.style.display = 'none';
            if (previewContent) previewContent.style.display = 'block';
        },

        preloadModules: function() {
            TiptapEditor.getModules();
        },

        flushSave: async function() {
            await TiptapEditor.flushSave();
        },
    };

    window.TiptapEditor = TiptapEditor;
    window.TiptapEditorModule = TiptapEditorModule;
})();