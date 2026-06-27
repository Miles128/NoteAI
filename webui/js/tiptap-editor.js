// ================================================================
// Tiptap 编辑器 - Markdown WYSIWYG
// 依赖: webui/lib/tiptap-bundle.js (通过 esbuild 从 npm 打包, 导出 window.TiptapModules)
// ================================================================

;(function() {
    'use strict';

    var SAVE_DELAY_MS = 1000;
    /** Idle-defer TipTap markdown parse above this size (chars or lines). */
    var DEFER_EDITOR_PARSE_CHARS = 16000;
    var DEFER_EDITOR_PARSE_LINES = 280;
    /** Apply CSS content-visibility hints on block nodes for long docs. */
    var VIRT_SCROLL_CHARS = 9000;
    var VIRT_SCROLL_LINES = 160;

    function updateSaveStatus(status, text) {
        var statusEl = document.getElementById('editor-status-bar');
        if (!statusEl) return;
        statusEl.className = 'editor-status-bar ' + (status || '');
        statusEl.textContent = text || '';
    }

    function getActiveFilePath() {
        return TiptapEditor.filePath || null;
    }

    function refreshPreviewState(content) {
        if (window.PreviewModule && window.PreviewModule.currentPreviewData) {
            window.PreviewModule.currentPreviewData.content = content;
        }
    }

    function splitFrontmatter(content) {
        var text = String(content || '');
        var match = text.match(/^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n)?/);
        if (!match) {
            return { yaml: '', body: text };
        }
        return {
            yaml: match[1] || '',
            body: text.slice(match[0].length),
        };
    }

    function composeMarkdown(yaml, body) {
        var cleanYaml = String(yaml || '').trim();
        if (!cleanYaml) {
            return body || '';
        }
        return '---\n' + cleanYaml + '\n---\n' + (body || '');
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
        userEdited: false,
        frontmatterText: '',
        _heavyIdleHandle: null,
        _heavyIdleKind: null,
        _heavyInitGen: 0,

        // 工具栏操作映射配置：action -> { method, hasParams, paramKey, defaultParam }
        toolbarActions: {
            'bold': { method: 'toggleBold' },
            'italic': { method: 'toggleItalic' },
            'strike': { method: 'toggleStrike' },
            'code': { method: 'toggleCode' },
            'heading': { method: 'toggleHeading', paramKey: 'level', defaultParam: 1 },
            'bulletList': { method: 'toggleBulletList' },
            'orderedList': { method: 'toggleOrderedList' },
            'blockquote': { method: 'toggleBlockquote' },
            'codeBlock': { method: 'toggleCodeBlock' },
            'undo': { method: 'undo' },
            'redo': { method: 'redo' }
        },

        _cancelHeavyIdle: function() {
            if (this._heavyIdleHandle == null) return;
            if (this._heavyIdleKind === 'idle' && typeof cancelIdleCallback === 'function') {
                cancelIdleCallback(this._heavyIdleHandle);
            } else {
                clearTimeout(this._heavyIdleHandle);
            }
            this._heavyIdleHandle = null;
            this._heavyIdleKind = null;
        },

        _scheduleHeavyIdle: function(onIdle) {
            var self = this;
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    if (typeof requestIdleCallback === 'function') {
                        self._heavyIdleKind = 'idle';
                        self._heavyIdleHandle = requestIdleCallback(function() {
                            self._heavyIdleHandle = null;
                            self._heavyIdleKind = null;
                            onIdle();
                        }, { timeout: 900 });
                    } else {
                        self._heavyIdleKind = 'timeout';
                        self._heavyIdleHandle = setTimeout(function() {
                            self._heavyIdleHandle = null;
                            self._heavyIdleKind = null;
                            onIdle();
                        }, 72);
                    }
                });
            });
        },

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

        /** Wait until tiptap-bundle.js has registered window.TiptapModules. */
        whenModulesReady: function(timeoutMs) {
            var limit = typeof timeoutMs === 'number' ? timeoutMs : 10000;
            return new Promise(function(resolve) {
                if (window.TiptapModules) {
                    resolve(true);
                    return;
                }
                var elapsed = 0;
                var step = 40;
                var timer = setInterval(function() {
                    elapsed += step;
                    if (window.TiptapModules) {
                        clearInterval(timer);
                        resolve(true);
                    } else if (elapsed >= limit) {
                        clearInterval(timer);
                        resolve(false);
                    }
                }, step);
            });
        },

        init: function(editorEl, content, filePath, callback) {
            var self = this;
            if (!editorEl) {
                console.error('[Tiptap] No editor element provided');
                return false;
            }

            this._heavyInitGen += 1;
            var gen = this._heavyInitGen;
            this._cancelHeavyIdle();

            var parts = splitFrontmatter(content || '');
            this.filePath = filePath || null;
            this.frontmatterText = parts.yaml;
            this.originalContent = composeMarkdown(this.frontmatterText, parts.body);
            this.fallbackTextarea = null;
            this.userEdited = false;

            if (this.editor) {
                this.editor.destroy();
                this.editor = null;
                this.instance = null;
            }
            editorEl.innerHTML = '';
            editorEl.classList.remove('tiptap-fallback-mode');
            this.renderFrontmatterPanel();

            var modules = this.getModules();
            if (!modules) {
                console.error('[Tiptap] Failed to load modules: TiptapModules not found');
                this._createTextareaFallback(editorEl, parts.body);
                return true;
            }

            var bodyStr = String(parts.body || '');
            var bodyLines = bodyStr.split(/\r?\n/).length;
            var deferHeavy = bodyStr.length >= DEFER_EDITOR_PARSE_CHARS || bodyLines >= DEFER_EDITOR_PARSE_LINES;
            var virtLarge = bodyStr.length >= VIRT_SCROLL_CHARS || bodyLines >= VIRT_SCROLL_LINES;
            var proseClass = virtLarge ? 'tiptap-prose tiptap-prose-large' : 'tiptap-prose';

            function mountEditor(syncParse) {
                if (gen !== self._heavyInitGen || !editorEl.isConnected) return;

                editorEl.innerHTML = '';

                try {
                    self.editor = new modules.Editor({
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
                        content: syncParse ? parts.body : '',
                        autofocus: false,
                        editorProps: {
                            attributes: {
                                class: proseClass,
                            },
                            handleDOMEvents: {
                                beforeinput: function() { self.userEdited = true; return false; },
                                paste: function() { self.userEdited = true; return false; },
                                drop: function() { self.userEdited = true; return false; },
                                cut: function() { self.userEdited = true; return false; },
                            },
                        },
                        onUpdate: function(_ref) {
                            var md = self.getContent();
                            if (self.userEdited && !window._rewritingFilePath) {
                                self.scheduleAutoSave(md || '');
                            }
                            if (window.StatusbarModule && window.StatusbarModule.updateFromContent) {
                                window.StatusbarModule.updateFromContent(md || '', null, null);
                            }
                            if (callback) {
                                callback(md || '');
                            }
                        },
                        onSelectionUpdate: function() {
                            self.updateToolbarState();
                            if (window.StatusbarModule && window.StatusbarModule.updateCursor) {
                                var pos = self.editor && self.editor.state && self.editor.state.selection
                                    ? self.editor.state.selection.from
                                    : 0;
                                var textBefore = '';
                                try {
                                    textBefore = self.editor.state.doc.textBetween(0, pos, '\n');
                                } catch (_e) {}
                                var lines = textBefore.split('\n');
                                var line = lines.length;
                                var col = lines[lines.length - 1].length + 1;
                                window.StatusbarModule.updateCursor(line, col);
                            }
                        },
                        onFocus: function() {
                            self.updateToolbarState();
                        },
                    });
                    self.instance = self.editor;
                    self.isActive = true;

                    if (!syncParse && parts.body) {
                        try {
                            self.editor.commands.setContent(parts.body);
                        } catch (setErr) {
                            console.warn('[Tiptap] deferred setContent failed:', setErr);
                        }
                    }
                } catch (e) {
                    console.error('[Tiptap] Init error:', e.message || e);
                    self._createTextareaFallback(editorEl, parts.body);
                    return;
                }

                self.bindToolbar();
                self.updateToolbarState();
                updateSaveStatus('saved', '已保存');
            }

            if (!deferHeavy) {
                mountEditor(true);
                return true;
            }

            editorEl.innerHTML = window.t('tiptapeditor.auto.tiptapeditor_auto_div_class_tiptap_deferred_moun');
            updateSaveStatus('', '解析排版…');

            this._scheduleHeavyIdle(function() {
                mountEditor(false);
            });

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
            this._heavyInitGen += 1;
            this._cancelHeavyIdle();
            await this.flushSave();
            if (this.editor) {
                this.editor.destroy();
                this.editor = null;
                this.instance = null;
            }
            this.fallbackTextarea = null;
            this.filePath = null;
            this.originalContent = '';
            this.frontmatterText = '';
            this.userEdited = false;
            this.isActive = false;
            this.clearFrontmatterPanel();

            var staleEl = document.getElementById('tiptap-editor');
            if (staleEl && !this.editor && !this.fallbackTextarea) {
                staleEl.innerHTML = '';
            }
        },

        getFullContent: function(body) {
            return composeMarkdown(this.frontmatterText, body || '');
        },

        renderFrontmatterPanel: function() {
            var panel = document.getElementById('frontmatter-panel');
            if (!panel) return;
            if (!this.frontmatterText.trim()) {
                panel.style.display = 'none';
                panel.innerHTML = '';
                return;
            }
            panel.style.display = 'block';
            panel.innerHTML = ''
                + '<details class="frontmatter-details">'
                + '<summary class="frontmatter-summary">元数据</summary>'
                + '<textarea class="frontmatter-textarea" spellcheck="false"></textarea>'
                + '</details>';
            var textarea = panel.querySelector('.frontmatter-textarea');
            if (!textarea) return;
            var self = this;
            textarea.value = this.frontmatterText;
            textarea.addEventListener('input', function() {
                self.frontmatterText = textarea.value;
                self.userEdited = true;
                self.scheduleAutoSave(self.getContent() || '');
            });
        },

        clearFrontmatterPanel: function() {
            var panel = document.getElementById('frontmatter-panel');
            if (!panel) return;
            panel.style.display = 'none';
            panel.innerHTML = '';
        },

        _createTextareaFallback: function(editorEl, content) {
            var self = this;
            var ta = document.createElement('textarea');
            ta.className = 'tiptap-fallback';
            ta.value = content || '';
            ta.style.cssText = 'width:100%;height:100%;border:none;padding:12px 12px calc(80px * var(--font-scale, 1));font-family:monospace;font-size:14px;line-height:1.7;resize:none;background:var(--bg, #fff);color:var(--text, #333);overflow-y:auto;';
            ta.addEventListener('input', function() {
                self.userEdited = true;
                self.scheduleAutoSave(ta.value);
            });
            editorEl.innerHTML = '';
            editorEl.classList.add('tiptap-fallback-mode');
            editorEl.appendChild(ta);
            this.fallbackTextarea = ta;
            this.isActive = true;
            updateSaveStatus('error', '编辑器未加载，请重启应用');
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
            if (!this.userEdited) {
                if (this.savePromise) {
                    await this.savePromise;
                }
                return;
            }
            var content = this.getContent();
            var fullContent = content === null ? null : this.getFullContent(content);
            if (fullContent !== null && fullContent !== this.originalContent) {
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
                    var fullContent = self.getFullContent(content);
                    var result = await window.api.saveFileContent(filePath, fullContent);
                    if (result && result.success) {
                        self.originalContent = fullContent;
                        refreshPreviewState(fullContent);
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
            this.userEdited = true;
            var action = btn.dataset.action;
            var cfg = this.toolbarActions[action];
            if (!cfg) {
                console.warn('[Tiptap] Unknown toolbar action:', action);
                this.updateToolbarState();
                return;
            }
            var chain = this.editor.chain().focus();
            try {
                var method = chain[cfg.method];
                if (typeof method !== 'function') {
                    console.warn('[Tiptap] Method not found:', cfg.method);
                } else if (cfg.paramKey) {
                    var val = parseInt(btn.dataset[cfg.paramKey] || cfg.defaultParam, 10);
                    method.call(chain, { level: val || cfg.defaultParam }).run();
                } else {
                    method.call(chain).run();
                }
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
            var previewPanel = document.getElementById('preview-panel');
            var splitBtn = document.getElementById('titlebar-split-btn');
            var editorEl = document.getElementById('tiptap-editor');

            await TiptapEditor.whenModulesReady(12000);

            await TiptapEditor.destroy();

            if (tiptapContainer) tiptapContainer.style.display = 'flex';
            if (toolbar) toolbar.style.display = 'flex';
            if (previewContent) previewContent.style.display = 'none';
            if (previewPanel) previewPanel.classList.add('editor-active');
            if (splitBtn) splitBtn.classList.add('active');

            if (!editorEl) {
                return false;
            }

            return new Promise(function(resolve) {
                requestAnimationFrame(function() {
                    var ok = TiptapEditor.init(editorEl, content, path, function() {});
                    resolve(!!ok && !TiptapEditor.fallbackTextarea);
                });
            });
        },

        hideEditorUI: async function() {
            await TiptapEditor.destroy();

            var tiptapContainer = document.getElementById('tiptap-editor-container');
            var toolbar = document.getElementById('tiptap-toolbar');
            var previewContent = document.getElementById('preview-content');
            var previewPanel = document.getElementById('preview-panel');

            if (tiptapContainer) tiptapContainer.style.display = 'none';
            if (toolbar) toolbar.style.display = 'none';
            if (previewContent) previewContent.style.display = 'block';
            if (previewPanel) previewPanel.classList.remove('editor-active');
        },

        preloadModules: function() {
            return TiptapEditor.whenModulesReady(15000);
        },

        flushSave: async function() {
            await TiptapEditor.flushSave();
        },
    };

    window.TiptapEditor = TiptapEditor;
    window.TiptapEditorModule = TiptapEditorModule;
})();