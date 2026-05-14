// ================================================================
// Tiptap 编辑器 - Markdown WYSIWYG
// 依赖: webui/lib/tiptap-bundle.js (通过 esbuild 从 npm 打包, 导出 window.TiptapModules)
// ================================================================

;(function() {
    'use strict';

    var TiptapEditor = {
        editor: null,

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

        init: function(editorEl, content, callback) {
            var self = this;
            if (!editorEl) {
                console.error('[Tiptap] No editor element provided');
                return;
            }

            var modules = this.getModules();
            if (!modules) {
                console.error('[Tiptap] Failed to load modules: TiptapModules not found');
                // 降级: 显示 textarea
                var ta = document.createElement('textarea');
                ta.className = 'tiptap-fallback';
                ta.value = content || '';
                ta.style.cssText = 'width:100%;height:100%;border:none;padding:12px;font-family:monospace;font-size:14px;resize:none;background:var(--bg, #fff);color:var(--text, #333);';
                editorEl.innerHTML = '';
                editorEl.appendChild(ta);
                return;
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
                        if (callback) {
                            // 每次内容变化回调
                        }
                    },
                });
            } catch (e) {
                console.error('[Tiptap] Init error:', e.message || e);
                // 降级
                var ta = document.createElement('textarea');
                ta.className = 'tiptap-fallback';
                ta.value = content || '';
                ta.style.cssText = 'width:100%;height:100%;border:none;padding:12px;font-family:monospace;font-size:14px;resize:none;background:var(--bg, #fff);color:var(--text, #333);';
                editorEl.innerHTML = '';
                editorEl.appendChild(ta);
                return;
            }

            // 监听 YAML 前端块变化
            this._watchYamlChanges();
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
            return null;
        },

        setContent: function(content) {
            if (this.editor && content) {
                try {
                    this.editor.commands.setContent(content);
                } catch (e) {
                    console.warn('[Tiptap] setContent error:', e);
                }
            }
        },

        focus: function() {
            if (this.editor) {
                this.editor.commands.focus();
            }
        },

        destroy: function() {
            if (this.editor) {
                this.editor.destroy();
                this.editor = null;
            }
        },

        _watchYamlChanges: function() {
            var self = this;
            if (this.editor) {
                this.editor.on('update', function() {
                    var md = self.getContent();
                    if (md && window.updateYamlFrontMatter) {
                        window.updateYamlFrontMatter(md);
                    }
                });
            }
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
                TiptapEditor.init(editorEl, content, function() {});
                TiptapEditor.isActive = true;
                resolve(true);
            });
        },

        hideEditorUI: function() {
            TiptapEditor.isActive = false;
            TiptapEditor.destroy();

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
    };

    window.TiptapEditor = TiptapEditor;
    window.TiptapEditorModule = TiptapEditorModule;
})();