(function() { 'use strict';

window.AssistantModule = (function() {
    var _chatHistory = [];
    var _isStreaming = false;
    var _indexBuilt = false;
    var _panelVisible = false;
    /** 打开 AI 侧栏收窄等 {@link _thawAILayout} */
    var _aiLayoutSnap = null;
    var _AI_PANEL_DEFAULT_W = 380;

    /**
     * 打开前：侧栏若为展开则缩至约 75%；AI 列宽约等于让出的宽幅。#content-panel 不再写死宽度，避免溢出被裁剪。
     */
    function _freezeForAIPanel(panel) {
        var sidebar = document.getElementById('sidebar');
        var snap = {};

        if (sidebar) snap.prevSidebarWidthStyle = sidebar.style.width || '';

        /* 不把 content-panel 设为 flex:0（会导致总宽超限 + right-area overflow:hidden 裁掉整列 AI）；
         * 仅靠侧栏收窄 + AI 弹性宽度，中间区主要由 flex 自然分配。 */

        if (!panel) {
            _aiLayoutSnap = snap;
            return;
        }

        if (!sidebar || sidebar.classList.contains('collapsed') || sidebar.offsetWidth < 40) {
            panel.style.width = _AI_PANEL_DEFAULT_W + 'px';
            _aiLayoutSnap = snap;
            return;
        }

        var sw = sidebar.offsetWidth;
        var newSw = Math.max(180, Math.round(sw * 0.75));
        var freed = Math.max(0, sw - newSw);

        sidebar.style.width = newSw + 'px';
        snap.didShrinkSidebar = true;
        var baseW = freed > 0 ? freed : Math.round(sw * 0.25);
        panel.style.width = Math.min(520, Math.max(320, baseW)) + 'px';

        _aiLayoutSnap = snap;
    }

    /** 关闭时还原侧栏与 AI 列内联宽度 */
    function _thawAILayout(panel) {
        var snap = _aiLayoutSnap;
        _aiLayoutSnap = null;
        var sidebar = document.getElementById('sidebar');

        if (snap && snap.didShrinkSidebar && sidebar) {
            if (snap.prevSidebarWidthStyle) {
                sidebar.style.width = snap.prevSidebarWidthStyle;
            } else {
                sidebar.style.removeProperty('width');
            }
        }

        if (panel) panel.style.removeProperty('width');

    }

    function _setRightAreaAiOpen(open) {
        var ra = document.getElementById('right-area');
        if (!ra) return;
        if (open) ra.classList.add('ai-panel-open');
        else ra.classList.remove('ai-panel-open');
    }

    var _aiBindingsDone = false;
    var _resizersInstalled = false;

    function ensureAiBindings() {
        if (_aiBindingsDone) return true;

        var input = document.getElementById('ai-input');
        var sendBtn = document.getElementById('ai-send-btn');
        if (!input || !sendBtn) {
            console.warn('[Assistant] ai-input / ai-send-btn missing; will retry next open');
            return false;
        }

        input.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter') return;
            if (e.shiftKey) return;
            e.preventDefault();
            sendMessage();
        });

        sendBtn.addEventListener('click', function() {
            sendMessage();
        });

        _ensureResizersInstalled();
        _aiBindingsDone = true;
        return true;
    }

    function init() {
        ensureAiBindings();
        _ensureSavePreviewBindings();
    }

    function toggle() {
        var panel = document.getElementById('ai-panel');
        if (!panel) return;

        ensureAiBindings();

        _panelVisible = !_panelVisible;
        if (_panelVisible) {
            _freezeForAIPanel(panel);
            panel.classList.add('ai-panel-visible');
            _setRightAreaAiOpen(true);
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) {
                toggleBtn.classList.add('active');
                toggleBtn.setAttribute('aria-pressed', 'true');
            }
            _scrollToBottom();
            window.requestAnimationFrame(function() {
                var el = document.getElementById('ai-input');
                if (!el) return;
                try {
                    el.focus({ preventScroll: true });
                } catch (_err) {
                    el.focus();
                }
            });
        } else {
            _thawAILayout(panel);
            panel.classList.remove('ai-panel-visible');
            _setRightAreaAiOpen(false);
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) {
                toggleBtn.classList.remove('active');
                toggleBtn.setAttribute('aria-pressed', 'false');
            }
        }
    }

    function ensureOpen() {
        var panel = document.getElementById('ai-panel');
        if (!panel) return;
        ensureAiBindings();
        if (!_panelVisible) {
            toggle();
        }
    }

    function _ensureResizersInstalled() {
        if (_resizersInstalled) return;

        var panel = document.getElementById('ai-panel');
        if (!panel) return;

        var leftResizer = document.getElementById('ai-resizer-left');
        var rightResizer = document.getElementById('ai-resizer-right');
        var topResizer = document.getElementById('ai-resizer-top');

        if (leftResizer && !leftResizer.dataset.aiResizeBound) {
            _initResizer(leftResizer, panel, 'left');
            leftResizer.dataset.aiResizeBound = '1';
        }
        if (rightResizer) rightResizer.style.display = 'none';

        if (topResizer && !topResizer.dataset.aiResizeBound) {
            _initTopResizer(topResizer, panel);
            topResizer.dataset.aiResizeBound = '1';
        }

        _resizersInstalled = true;
    }

    function _initResizer(resizerEl, panel, side) {
        var startX, startWidth;

        function onMouseDown(e) {
            e.preventDefault();
            startX = e.clientX;
            startWidth = panel.offsetWidth;
            resizerEl.classList.add('ai-resizer-active');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            if (typeof Graph3Tier !== 'undefined') Graph3Tier.pauseResize();
        }

        function onMouseMove(e) {
            var dx = e.clientX - startX;
            var newWidth;
            if (side === 'left') {
                newWidth = startWidth - dx;
            } else {
                newWidth = startWidth + dx;
            }
            newWidth = Math.max(320, Math.min(640, newWidth));
            panel.style.width = newWidth + 'px';
        }

        function onMouseUp() {
            resizerEl.classList.remove('ai-resizer-active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            if (typeof Graph3Tier !== 'undefined') Graph3Tier.resumeResize();
        }

        resizerEl.addEventListener('mousedown', onMouseDown);
    }

    function _initTopResizer(resizerEl, panel) {
        var startY, startHeight;

        function onMouseDown(e) {
            e.preventDefault();
            startY = e.clientY;
            startHeight = panel.offsetHeight;
            resizerEl.classList.add('ai-resizer-active');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
            if (typeof Graph3Tier !== 'undefined') Graph3Tier.pauseResize();
        }

        function onMouseMove(e) {
            var dy = e.clientY - startY;
            var newHeight = startHeight - dy;
            var minH = 280;
            var maxH = window.innerHeight - panel.offsetTop;
            newHeight = Math.max(minH, Math.min(maxH, newHeight));
            panel.style.height = newHeight + 'px';
            panel.style.bottom = 'auto';
        }

        function onMouseUp() {
            resizerEl.classList.remove('ai-resizer-active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            if (typeof Graph3Tier !== 'undefined') Graph3Tier.resumeResize();
        }

        resizerEl.addEventListener('mousedown', onMouseDown);
    }

    var _currentStreamEl = null;
    var _streamRawText = '';
    var _lastArchive = null;
    var _savePreviewState = null;
    var _savePreviewBindingsDone = false;

    function _renderMarkdownHtml(text) {
        if (!text) return '';
        if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
            return window.EditorModule.renderMarkdownPreview(text);
        }
        return '<pre>' + window.escapeHtml(text) + '</pre>';
    }

    function _setAssistantMarkdown(contentEl, text) {
        if (!contentEl) return;
        contentEl.classList.add('ai-msg-md', 'ai-chat-md');
        contentEl.classList.remove('preview-content');
        contentEl.innerHTML = _renderMarkdownHtml(text);
    }

    function _setPlainText(contentEl, text) {
        if (!contentEl) return;
        contentEl.classList.remove('ai-msg-md', 'ai-chat-md', 'preview-content');
        contentEl.textContent = text || '';
    }

    function sendMessage(questionOverride, options) {
        if (_isStreaming) return;
        options = options || {};

        var input = document.getElementById('ai-input');
        if (!input) return;
        var question = String(questionOverride || input.value || '').trim();
        if (!question) return;

        if (!questionOverride) input.value = '';

        addUserMessage(question);
        var requestHistory = _chatHistory.slice(-6).map(function(message) {
            return {
                role: message.role,
                content: String(message.content || '').slice(0, 1200)
            };
        });
        _chatHistory.push({ role: 'user', content: question });
        _lastArchive = { question: question, answer: '', citations: [], contextFile: '', rowEl: null };

        _isStreaming = true;
        _streamRawText = '';
        var assistantEl = addAssistantMessage();
        _currentStreamEl = assistantEl;

        var topics = _extractTopics();
        var tags = _extractTags();
        var currentFile = _extractCurrentFile();
        _lastArchive.contextFile = currentFile;

        options.history = requestHistory;
        window.api.ragChat(question, topics, tags, currentFile, options).then(function(result) {
            if (result && result.started) {
                setTimeout(function() {
                    if (_isStreaming && _currentStreamEl === assistantEl && !_streamRawText) {
                        _isStreaming = false;
                        _setPlainText(assistantEl, window.t('assistant.timeout'));
                        assistantEl.classList.remove('ai-typing');
                        _currentStreamEl = null;
                    }
                }, 180000);
                return;
            }
            if (result && result.success === false) {
                _isStreaming = false;
                _setPlainText(assistantEl, result.message || window.t('assistant.requestFailed'));
                assistantEl.classList.remove('ai-typing');
            }
        }).catch(function(err) {
            _isStreaming = false;
            var msg = (err && err.message) ? err.message : String(err || window.t('common.unknownError'));
            _setPlainText(assistantEl, window.t('assistant.requestFailedMsg', { message: msg }));
            assistantEl.classList.remove('ai-typing');
        });
    }

    function ask(question) {
        ensureOpen();
        var input = document.getElementById('ai-input');
        if (input) input.value = '';
        sendMessage(question);
    }

    function askSelection(selection, options) {
        ensureOpen();
        var selected = String(selection || '').trim();
        if (!selected) return;
        sendMessage(selected, {
            selectionLookup: true,
            selectionRoute: (options && options.route) || 'auto',
            selectionContext: (options && options.context) || ''
        });
    }

    function _extractTopics() {
        if (!window.AppState || !window.AppState.lastTopicData) return null;
        var data = window.AppState.lastTopicData;
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (_e) { return null; }
        }
        if (!data || !data.topics) return null;
        return data.topics.map(function(t) { return t.name; });
    }

    function _extractTags() {
        if (!window.AppState || !window.AppState.lastTagsData) return null;
        var data = window.AppState.lastTagsData;
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (_e) { return null; }
        }
        if (!data || !data.tags) return null;
        return data.tags.map(function(t) { return t.name; });
    }

    function _extractCurrentFile() {
        if (!window.AppState || !window.AppState.selectedFilePath) return "";
        return window.AppState.selectedFilePath;
    }

    function _speakerLabel(role) {
        if (role === 'user') {
            return (window.t && window.t('assistant.userLabel')) || '你';
        }
        if (role === 'system') {
            return (window.t && window.t('assistant.system')) || '系统';
        }
        return (window.t && window.t('assistant.name')) || 'RAG助手';
    }

    function addUserMessage(text) {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return;
        var bubble = document.createElement('div');
        bubble.className = 'ai-chat-line ai-msg ai-user';
        bubble.setAttribute('aria-label', _speakerLabel('user'));
        var content = document.createElement('div');
        content.className = 'ai-msg-content';
        content.textContent = text;
        bubble.appendChild(content);
        container.appendChild(bubble);
        _scrollToBottom();
    }

    function addAssistantMessage() {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return null;
        var bubble = document.createElement('div');
        bubble.className = 'ai-chat-line ai-msg ai-assistant';
        bubble.setAttribute('aria-label', _speakerLabel('assistant'));
        var content = document.createElement('div');
        content.className = 'ai-msg-content ai-typing';
        bubble.appendChild(content);
        container.appendChild(bubble);
        _scrollToBottom();
        return content;
    }

    function addSystemMessage(text) {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return;
        var div = document.createElement('div');
        div.className = 'ai-chat-line ai-msg ai-system';
        var content = document.createElement('span');
        content.className = 'ai-msg-content';
        content.textContent = text;
        div.appendChild(content);
        container.appendChild(div);
        _scrollToBottom();
    }

    function _scrollToBottom() {
        /* 实际滚动容器是 .ai-panel-body（overflow-y:auto），不是 .ai-panel-messages */
        var sc = document.querySelector('#inspector-content-ai .ai-panel-body')
            || document.querySelector('#ai-panel .ai-panel-body');
        if (sc) sc.scrollTop = sc.scrollHeight;
    }

    function handleEvent(eventData) {
        if (!eventData) return;

        if (eventData.type === 'rag_chat_chunk') {
            if (_currentStreamEl) {
                _streamRawText += eventData.token || '';
                _setAssistantMarkdown(_currentStreamEl, _streamRawText);
                _scrollToBottom();
            }
        } else if (eventData.type === 'rag_chat_done') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _currentStreamEl.classList.remove('ai-typing');
                var answerText = eventData.answer || _streamRawText || '';
                _setAssistantMarkdown(_currentStreamEl, answerText);
                _chatHistory.push({ role: 'assistant', content: answerText });
                if (eventData.citations && eventData.citations.length > 0) {
                    _linkifyCitationRefs(_currentStreamEl, eventData.citations);
                    _renderCitations(_currentStreamEl, eventData.citations, eventData.citation_quality);
                }
                if (_lastArchive) {
                    _lastArchive.answer = answerText;
                    _lastArchive.citations = eventData.citations || [];
                    // Saving an answer is a user choice, not an LLM judgement.
                    // Every completed grounded answer therefore exposes the same
                    // explicit, non-destructive save action.
                    _attachSaveNoteActions(_currentStreamEl, _lastArchive);
                }
            }
            _streamRawText = '';
            _currentStreamEl = null;
        } else if (eventData.type === 'rag_error') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _setPlainText(_currentStreamEl, eventData.message || window.t('assistant.requestFailed'));
                _currentStreamEl.classList.remove('ai-typing');
            }
            _streamRawText = '';
            _currentStreamEl = null;
        } else if (eventData.type === 'rag_index_built') {
            var indexPayload = eventData.data || eventData;
            _indexBuilt = !!indexPayload.success;
            if (_indexBuilt) {
                addSystemMessage(window.t('assistant.indexBuildDone', { count: indexPayload.chunk_count || 0 }));
            } else {
                var failMessage = indexPayload.message || window.t('common.unknownError');
                addSystemMessage(window.t('assistant.indexBuildFailed', { message: failMessage }));
            }
        } else if (eventData.type === 'rag_index_needs_rebuild') {
            addSystemMessage(eventData.message || window.t('assistant.indexBuildFailed', { message: '' }));
        } else if (eventData.type === 'rag-index-progress') {
            var pct = eventData.data && eventData.data.percent || 0;
            var msg = eventData.data && eventData.data.message || '';
            addSystemMessage(window.t('assistant.indexProgress', { percent: pct, message: msg }));
        }

    }

    function _estimateIndexTime() {
        // Rough estimate: ~0.5s per file for chunking + embedding on M-series Mac
        var fileCount = window.AppState && window.AppState.files ? window.AppState.files.length : 100;
        var seconds = Math.max(10, fileCount * 0.5);
        if (seconds < 60) {
            return Math.ceil(seconds) + '秒';
        }
        return Math.ceil(seconds / 60) + '分钟';
    }

    function rebuildIndex() {
        addSystemMessage(window.t('assistant.indexBuilding', { estimate: _estimateIndexTime() }));
        window.api.ragRebuildIndex().catch(function(err) {
            addSystemMessage(window.t('assistant.indexRequestFailed', { message: err.message }));
        });
    }

    function _attachSaveNoteActions(contentEl, archive) {
        if (!contentEl || !archive || !archive.answer) return;
        var bubble = contentEl.closest('.ai-msg');
        if (!bubble || bubble.querySelector('.ai-msg-actions')) return;

        var actions = document.createElement('div');
        actions.className = 'ai-msg-actions';

        var hint = document.createElement('p');
        hint.className = 'ai-save-note-hint';
        hint.textContent = window.t('assistant.insightHint');
        actions.appendChild(hint);

        function addSaveButton(label, target) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ai-save-note-btn';
            btn.textContent = label;
            btn.addEventListener('click', function() {
                _openSavePreview(archive, target, btn, label, hint);
            });
            actions.appendChild(btn);
        }
        addSaveButton(window.t('assistant.saveAsNote'), 'note');
        addSaveButton(window.t('assistant.saveAsTask'), 'task');
        bubble.appendChild(actions);
        archive.rowEl = bubble;
    }

    function _archivePayload(archive, target, previewOnly) {
        return {
            question: archive.question,
            answer: archive.answer,
            target: target,
            context_file: archive.contextFile || '',
            citations: archive.citations || [],
            preview_only: previewOnly === true
        };
    }

    function _ensureSavePreviewBindings() {
        if (_savePreviewBindingsDone) return;
        var modal = document.getElementById('assistant-save-modal');
        var close = document.getElementById('assistant-save-close');
        var cancel = document.getElementById('assistant-save-cancel');
        var confirm = document.getElementById('assistant-save-confirm');
        if (!modal || !close || !cancel || !confirm) return;
        close.addEventListener('click', _closeSavePreview);
        cancel.addEventListener('click', _closeSavePreview);
        modal.addEventListener('click', function(event) {
            if (event.target === modal) _closeSavePreview();
        });
        confirm.addEventListener('click', _confirmSavePreview);
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape' && modal.style.display !== 'none') {
                _closeSavePreview();
            }
        });
        _savePreviewBindingsDone = true;
    }

    function _openSavePreview(archive, target, sourceButton, sourceLabel, hint) {
        if (!window.api || !window.api.archiveChatAnswer) return;
        _ensureSavePreviewBindings();
        sourceButton.disabled = true;
        sourceButton.textContent = window.t('assistant.loadingPreview');
        var payload = _archivePayload(archive, target, true);
        window.api.archiveChatAnswer(payload).then(function(res) {
            if (!res || !res.success) {
                throw new Error((res && res.message) || window.t('common.unknownError'));
            }
            var modal = document.getElementById('assistant-save-modal');
            var path = document.getElementById('assistant-save-path');
            var content = document.getElementById('assistant-save-content');
            var confirm = document.getElementById('assistant-save-confirm');
            if (!modal || !path || !content || !confirm) {
                throw new Error(window.t('assistant.previewUnavailable'));
            }
            path.textContent = res.path || '';
            content.textContent = res.content || '';
            confirm.disabled = false;
            confirm.textContent = window.t('assistant.confirmSave');
            modal.style.display = 'flex';
            _savePreviewState = {
                payload: _archivePayload(archive, target, false),
                sourceButton: sourceButton,
                sourceLabel: sourceLabel,
                hint: hint
            };
            window.requestAnimationFrame(function() { confirm.focus(); });
        }).catch(function(err) {
            sourceButton.disabled = false;
            sourceButton.textContent = sourceLabel;
            addSystemMessage(window.t('assistant.previewFailed', { message: err.message || String(err) }));
        });
    }

    function _closeSavePreview() {
        var modal = document.getElementById('assistant-save-modal');
        if (modal) modal.style.display = 'none';
        if (_savePreviewState && _savePreviewState.sourceButton) {
            _savePreviewState.sourceButton.disabled = false;
            _savePreviewState.sourceButton.textContent = _savePreviewState.sourceLabel;
        }
        _savePreviewState = null;
    }

    function _confirmSavePreview() {
        if (!_savePreviewState || !window.api || !window.api.archiveChatAnswer) return;
        var state = _savePreviewState;
        var confirm = document.getElementById('assistant-save-confirm');
        if (confirm) {
            confirm.disabled = true;
            confirm.textContent = window.t('assistant.saving');
        }
        window.api.archiveChatAnswer(state.payload).then(function(res) {
            if (!res || !res.success) {
                throw new Error((res && res.message) || window.t('common.unknownError'));
            }
            var modal = document.getElementById('assistant-save-modal');
            if (modal) modal.style.display = 'none';
            state.sourceButton.textContent = window.t('common.saved');
            state.hint.textContent = window.t('assistant.savedToPath', { path: res.path || '' });
            _savePreviewState = null;
            if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
                window.refreshWorkspaceViewsAfterChange();
            }
        }).catch(function(err) {
            if (confirm) {
                confirm.disabled = false;
                confirm.textContent = window.t('assistant.confirmSave');
            }
            addSystemMessage(window.t('assistant.saveFailed', { message: err.message || String(err) }));
        });
    }

    function _openNoteFromPath(filePath, displayName) {
        if (!filePath) return;
        var name = displayName || filePath.split('/').pop() || filePath;
        if (window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(filePath, name);
            return;
        }
        if (window.api && window.api.onFileSelected) {
            window.api.onFileSelected(filePath);
        }
    }

    function _linkifyCitationRefs(contentEl, citations) {
        if (!contentEl || !citations || !citations.length) return;

        var byIndex = {};
        citations.forEach(function(cite) {
            if (cite && cite.index != null && cite.file_path) {
                byIndex[cite.index] = cite;
            }
        });
        if (!Object.keys(byIndex).length) return;

        var re = /\[(\d+)\]/g;
        var walker = document.createTreeWalker(contentEl, NodeFilter.SHOW_TEXT, null);
        var textNodes = [];
        while (walker.nextNode()) {
            textNodes.push(walker.currentNode);
        }

        textNodes.forEach(function(node) {
            var text = node.textContent || '';
            if (!/\[\d+\]/.test(text)) return;

            var frag = document.createDocumentFragment();
            var last = 0;
            var match;
            re.lastIndex = 0;
            while ((match = re.exec(text)) !== null) {
                if (match.index > last) {
                    frag.appendChild(document.createTextNode(text.slice(last, match.index)));
                }
                var idx = parseInt(match[1], 10);
                var cite = byIndex[idx];
                if (cite) {
                    var ref = document.createElement('button');
                    ref.type = 'button';
                    ref.className = 'ai-citation-ref';
                    ref.textContent = match[0];
                    ref.title = cite.source_label || cite.file_name || cite.file_path;
                    (function(c) {
                        ref.addEventListener('click', function(e) {
                            e.preventDefault();
                            _openNoteFromPath(
                                c.file_path,
                                c.source_label || c.file_name || ''
                            );
                        });
                    })(cite);
                    frag.appendChild(ref);
                } else {
                    frag.appendChild(document.createTextNode(match[0]));
                }
                last = re.lastIndex;
            }
            if (last < text.length) {
                frag.appendChild(document.createTextNode(text.slice(last)));
            }
            node.parentNode.replaceChild(frag, node);
        });
    }

    function _citationQualityText(quality, citationCount) {
        var q = quality || {};
        var level = q.level || (citationCount ? 'balanced' : 'none');
        var count = q.source_count || citationCount || 0;
        var key = 'assistant.citationQuality.' + level;
        return window.t ? window.t(key, { count: count }) : '';
    }

    function _renderCitations(contentEl, citations, quality) {
        if (!contentEl || !citations || citations.length === 0) return;
        var bubble = contentEl.closest('.ai-msg');
        if (!bubble) return;

        var container = document.createElement('div');
        container.className = 'ai-citations';

        var header = document.createElement('div');
        header.className = 'ai-citations-header';
        var title = document.createElement('span');
        title.textContent = window.t('assistant.sources') || '参考来源';
        header.appendChild(title);
        var badge = document.createElement('span');
        badge.className = 'ai-citation-quality';
        badge.textContent = _citationQualityText(quality, citations.length);
        header.appendChild(badge);
        container.appendChild(header);

        var list = document.createElement('div');
        list.className = 'ai-citations-list';

        citations.forEach(function(cite) {
            var item = document.createElement('div');
            item.className = 'ai-citation-item';
            item.setAttribute('data-file-path', cite.file_path || '');

            var index = document.createElement('span');
            index.className = 'ai-citation-index';
            index.textContent = cite.index;
            item.appendChild(index);

            var info = document.createElement('div');
            info.className = 'ai-citation-info';

            var name = document.createElement('span');
            name.className = 'ai-citation-name';
            name.textContent = cite.source_label || cite.file_name || cite.file_path || ('[' + cite.index + ']');
            info.appendChild(name);

            if (cite.topic) {
                var topic = document.createElement('span');
                topic.className = 'ai-citation-topic';
                topic.textContent = cite.topic;
                info.appendChild(topic);
            }

            item.appendChild(info);

            item.addEventListener('click', function() {
                if (cite.url) {
                    window.open(cite.url, '_blank', 'noopener,noreferrer');
                } else {
                    _openNoteFromPath(
                        cite.file_path,
                        cite.source_label || cite.file_name || ''
                    );
                }
            });

            list.appendChild(item);
        });

        container.appendChild(list);
        bubble.appendChild(container);
    }

    return {
        init: init,
        handleEvent: handleEvent,
        rebuildIndex: rebuildIndex,
        toggle: toggle,
        ensureOpen: ensureOpen,
        ask: ask,
        askSelection: askSelection
    };
})();

function toggleAIPanel() {
    if (window.AssistantModule) window.AssistantModule.toggle();
}

window.toggleAIPanel = toggleAIPanel;

})();
