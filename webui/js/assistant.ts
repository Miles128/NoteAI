(function() { 'use strict';

window.AssistantModule = (function() {
    var _chatHistory: any[] = [];
    var _isStreaming = false;
    var _indexBuilt = false;
    var _panelVisible = false;
    /** 打开 AI 侧栏收窄等 {@link _thawAILayout} */
    var _aiLayoutSnap: any = null;
    var _AI_PANEL_DEFAULT_W = 380;

    /**
     * 打开前：侧栏若为展开则缩至约 75%；AI 列宽约等于让出的宽幅。#content-panel 不再写死宽度，避免溢出被裁剪。
     */
    function _freezeForAIPanel(panel: any) {
        var sidebar = document.getElementById('sidebar');
        var snap: any = {};

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
    function _thawAILayout(panel: any) {
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

    function _setRightAreaAiOpen(open: any) {
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

    function _initResizer(resizerEl: any, panel: any, side: any) {
        var startX: any, startWidth: any;

        function onMouseDown(e: any) {
            e.preventDefault();
            startX = e.clientX;
            startWidth = panel.offsetWidth;
            resizerEl.classList.add('ai-resizer-active');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            if (window.Graph3Tier) window.Graph3Tier!.pauseResize!();
        }

        function onMouseMove(e: any) {
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
            if (window.Graph3Tier) window.Graph3Tier!.resumeResize!();
        }

        resizerEl.addEventListener('mousedown', onMouseDown);
    }

    function _initTopResizer(resizerEl: any, panel: any) {
        var startY: any, startHeight: any;

        function onMouseDown(e: any) {
            e.preventDefault();
            startY = e.clientY;
            startHeight = panel.offsetHeight;
            resizerEl.classList.add('ai-resizer-active');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
            if (window.Graph3Tier) window.Graph3Tier!.pauseResize!();
        }

        function onMouseMove(e: any) {
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
            if (window.Graph3Tier) window.Graph3Tier!.resumeResize!();
        }

        resizerEl.addEventListener('mousedown', onMouseDown);
    }

    var _currentStreamEl: any = null;
    var _streamRawText = '';
    /** 本轮 rag_retrieval 元信息（先于回答流到达），用于检索过程面板 */
    var _pendingRetrieval: any = null;
    /** 检索面板是否已插入当前占位 bubble，避免重复挂载 */
    var _retrievalAttached = false;

    function _renderMarkdownHtml(text: any) {
        if (!text) return '';
        if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
            return window.EditorModule.renderMarkdownPreview(text);
        }
        return '<pre>' + window.escapeHtml(text) + '</pre>';
    }

    function _setAssistantMarkdown(contentEl: any, text: any) {
        if (!contentEl) return;
        contentEl.classList.add('ai-msg-md', 'ai-chat-md');
        contentEl.classList.remove('preview-content');
        contentEl.innerHTML = _renderMarkdownHtml(text);
    }

    function _setPlainText(contentEl: any, text: any) {
        if (!contentEl) return;
        contentEl.classList.remove('ai-msg-md', 'ai-chat-md', 'preview-content');
        contentEl.textContent = text || '';
    }

    function sendMessage(questionOverride?: any, options?: any) {
        if (_isStreaming) return;
        options = options || {};

        var input = document.getElementById('ai-input') as HTMLInputElement | null;
        if (!input) return;
        var question = String(questionOverride || input.value || '').trim();
        if (!question) return;

        if (!questionOverride) input.value = '';

        /* 新一轮提问开始：清除上一轮追问 chips 与检索元信息 */
        _clearSuggestionChips();
        _pendingRetrieval = null;
        _retrievalAttached = false;

        addUserMessage(question);
        /* 上送最近 12 条：后端主题锚定需要 >6 条历史才能提取锚点词（P4），
           prompt 内历史仍由后端 _limited_history 截取最近 6 条，互不影响 */
        var requestHistory = _chatHistory.slice(-12).map(function(message) {
            return {
                role: message.role,
                content: String(message.content || '').slice(0, 1200)
            };
        });
        _chatHistory.push({ role: 'user', content: question });

        _isStreaming = true;
        _streamRawText = '';
        const assistantEl = addAssistantMessage()!;
        _currentStreamEl = assistantEl;

        var topics = _extractTopics();
        var tags = _extractTags();
        var currentFile = _extractCurrentFile();

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

    function ask(question: any) {
        ensureOpen();
        var input = document.getElementById('ai-input') as HTMLInputElement | null;
        if (input) input.value = '';
        sendMessage(question);
    }

    function askSelection(selection: any, options: any) {
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
        return data.topics.map(function(t: any) { return t.name; });
    }

    function _extractTags() {
        if (!window.AppState || !window.AppState.lastTagsData) return null;
        var data = window.AppState.lastTagsData;
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (_e) { return null; }
        }
        if (!data || !data.tags) return null;
        return data.tags.map(function(t: any) { return t.name; });
    }

    function _extractCurrentFile() {
        if (!window.AppState || !window.AppState.selectedFilePath) return "";
        return window.AppState.selectedFilePath;
    }

    function _speakerLabel(role: any) {
        if (role === 'user') {
            return (window.t && window.t('assistant.userLabel')) || '你';
        }
        if (role === 'system') {
            return (window.t && window.t('assistant.system')) || '系统';
        }
        return (window.t && window.t('assistant.name')) || 'RAG助手';
    }

    function addUserMessage(text: any) {
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

    function addSystemMessage(text: any) {
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

    function _scrollToBottomIfNearBottom() {
        /* 用户上翻阅读时不要打断滚动；仅接近底部才跟随 */
        var sc = document.querySelector('#inspector-content-ai .ai-panel-body')
            || document.querySelector('#ai-panel .ai-panel-body');
        if (!sc) return;
        var nearBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 120;
        if (nearBottom) sc.scrollTop = sc.scrollHeight;
    }

    /* 流式渲染节流：逐 token 全量 parse+innerHTML 是 O(n²)，改为 200ms 节流
       重渲染 + 结束强制 flush（长回答渲染次数从 token 数降到秒级） */
    var _streamRenderTimer: any = null;
    var _streamRenderPending = false;

    function _scheduleStreamRender() {
        if (_streamRenderPending) return;
        _streamRenderPending = true;
        _streamRenderTimer = setTimeout(function() {
            _streamRenderPending = false;
            _streamRenderTimer = null;
            if (_currentStreamEl) {
                _setAssistantMarkdown(_currentStreamEl, _streamRawText);
                _scrollToBottomIfNearBottom();
            }
        }, 200);
    }

    function _flushStreamRender() {
        if (_streamRenderTimer) {
            clearTimeout(_streamRenderTimer);
            _streamRenderTimer = null;
        }
        _streamRenderPending = false;
        if (_currentStreamEl) {
            _setAssistantMarkdown(_currentStreamEl, _streamRawText);
            _scrollToBottom();
        }
    }

    function handleEvent(eventData: any) {
        if (!eventData) return;

        if (eventData.type === 'rag_retrieval') {
            /* 检索元信息先于 chunk 到达：缓存并立即挂到占位 bubble 上（折叠面板骨架） */
            _pendingRetrieval = eventData.data || {};
            if (_currentStreamEl && !_retrievalAttached) {
                _attachRetrievalPanel(_currentStreamEl, _pendingRetrieval);
                _retrievalAttached = true;
            }
        } else if (eventData.type === 'rag_chat_chunk') {
            if (_currentStreamEl) {
                _streamRawText += eventData.token || '';
                _scheduleStreamRender();
            }
        } else if (eventData.type === 'rag_chat_done') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _currentStreamEl.classList.remove('ai-typing');
                var answerText = eventData.answer || _streamRawText || '';
                _flushStreamRender();
                /* 用最终 answerText 覆盖节流渲染结果（可能比 _streamRawText 更完整） */
                _currentStreamEl.innerHTML = _renderMarkdownHtml(answerText);
                _chatHistory.push({ role: 'assistant', content: answerText });
                if (eventData.citations && eventData.citations.length > 0) {
                    _linkifyCitationRefs(_currentStreamEl, eventData.citations);
                    _renderCitations(_currentStreamEl, eventData.citations, eventData.citation_quality);
                }
                /* 兜底：若检索事件晚于 bubble 创建后仍未挂载，则在回答完成时补挂（位置仍在顶部） */
                if (_pendingRetrieval && !_retrievalAttached) {
                    _attachRetrievalPanel(_currentStreamEl, _pendingRetrieval);
                    _retrievalAttached = true;
                }
                /* P4：引用区之下渲染追问 chips */
                _renderSuggestionChips(_currentStreamEl, eventData.suggestions);
            }
            _streamRawText = '';
            _currentStreamEl = null;
            _pendingRetrieval = null;
            _retrievalAttached = false;
        } else if (eventData.type === 'rag_error') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _setPlainText(_currentStreamEl, eventData.message || window.t('assistant.requestFailed'));
                _currentStreamEl.classList.remove('ai-typing');
            }
            _streamRawText = '';
            _currentStreamEl = null;
            _pendingRetrieval = null;
            _retrievalAttached = false;
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

    /** window.t 对缺失 key 会返回 key 本身，这里提供中文兜底文案 */
    function _tr(key: any, fallback: any) {
        var v = window.t ? window.t(key) : '';
        return (v && v !== key) ? v : fallback;
    }

    function _scoreText(value: any) {
        var n = Number(value);
        return isFinite(n) ? n.toFixed(3) : '-';
    }

    function _clearSuggestionChips() {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return;
        var rows = container.querySelectorAll('.ai-suggestion-chips');
        for (var i = 0; i < rows.length; i++) {
            rows[i].parentNode!.removeChild(rows[i]);
        }
    }

    /** P4：在当前回答 bubble 的引用区下方渲染一行追问 chips，点击即以该文本发起新一轮提问 */
    function _renderSuggestionChips(contentEl: any, suggestions: any) {
        if (!contentEl || !suggestions || !suggestions.length) return;
        var bubble = contentEl.closest('.ai-msg');
        if (!bubble || bubble.querySelector('.ai-suggestion-chips')) return;

        var items = [];
        for (var i = 0; i < suggestions.length && items.length < 3; i++) {
            var text = String(suggestions[i] == null ? '' : suggestions[i]).trim();
            if (text) items.push(text);
        }
        if (!items.length) return;

        var row = document.createElement('div');
        row.className = 'ai-suggestion-chips';
        items.forEach(function(suggestion) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'ai-suggestion-chip';
            chip.textContent = suggestion; /* textContent 天然转义 */
            chip.title = suggestion;
            chip.addEventListener('click', function() {
                if (_isStreaming) return;
                sendMessage(suggestion);
            });
            row.appendChild(chip);
        });
        bubble.appendChild(row);
    }

    /** P9：在回答 bubble 顶部（引用区之上）插入默认折叠的检索过程面板 */
    function _attachRetrievalPanel(contentEl: any, data: any) {
        if (!contentEl || !data) return;
        var bubble = contentEl.closest('.ai-msg');
        if (!bubble || bubble.querySelector('.ai-retrieval-details')) return;

        var esc = window.escapeHtml;
        var escAttr = window.escapeAttr || window.escapeHtml;
        var debug = data.retrieval_debug || {};

        var badges = '';
        if (debug.cached) {
            badges += '<span class="ai-retrieval-badge ai-retrieval-badge-cached">'
                + esc(_tr('assistant.retrievalCached', '缓存命中')) + '</span>';
        }
        if (debug.degraded) {
            badges += '<span class="ai-retrieval-badge ai-retrieval-badge-degraded">'
                + esc(_tr('assistant.retrievalDegraded', '部分中间数据缺失')) + '</span>';
        }

        var rows = '';
        function addRow(label: any, value: any) {
            if (value === '' || value == null) return;
            rows += '<div class="ai-retrieval-row"><span class="ai-retrieval-label">' + esc(label) + '</span>'
                + '<span class="ai-retrieval-value">' + esc(value) + '</span></div>';
        }

        addRow(_tr('assistant.retrievalIntent', '意图分类'), data.intent || '-');

        var hydeOn = !!(debug.hyde_enabled != null ? debug.hyde_enabled : data.hyde_enabled);
        var hydeQuery = debug.hyde_query != null ? debug.hyde_query : data.hyde_query;
        var hydeText = hydeOn
            ? (_tr('assistant.retrievalHydeOn', '已触发') + (hydeQuery ? ' · ' + hydeQuery : ''))
            : _tr('assistant.retrievalHydeOff', '未触发');
        addRow('HyDE', hydeText);

        var funnel = [debug.raw_hits, debug.mmr_kept, debug.final].map(function(n) {
            return n == null ? '-' : esc(String(n));
        }).join(' <span class="ai-retrieval-arrow">→</span> ');
        rows += '<div class="ai-retrieval-row"><span class="ai-retrieval-label">'
            + esc(_tr('assistant.retrievalFunnel', '候选收敛')) + '</span>'
            + '<span class="ai-retrieval-value">' + funnel + '</span></div>';

        if (debug.anchor_terms && debug.anchor_terms.length) {
            var terms = '';
            debug.anchor_terms.forEach(function(term: any) {
                terms += '<span class="ai-retrieval-term">' + esc(String(term == null ? '' : term)) + '</span>';
            });
            rows += '<div class="ai-retrieval-row"><span class="ai-retrieval-label">'
                + esc(_tr('assistant.retrievalAnchors', '锚点词')) + '</span>'
                + '<span class="ai-retrieval-value ai-retrieval-terms">' + terms + '</span></div>';
        }

        var sources = data.top_sources || [];
        if (sources.length) {
            var listHtml = '';
            sources.forEach(function(src: any) {
                src = src || {};
                var path = String(src.path || '');
                var section = String(src.section_title || '');
                listHtml += '<div class="ai-retrieval-source">'
                    + '<span class="ai-retrieval-source-path" title="' + escAttr(path) + '">' + esc(path) + '</span>'
                    + (section ? '<span class="ai-retrieval-source-section">' + esc(section) + '</span>' : '')
                    + '<span class="ai-retrieval-source-score">'
                    + esc(_scoreText(src.score)) + ' / ' + esc(_scoreText(src.rerank_score)) + '</span>'
                    + '</div>';
            });
            rows += '<div class="ai-retrieval-sources">'
                + '<div class="ai-retrieval-label">' + esc(_tr('assistant.retrievalSources', 'Top 片段')) + '</div>'
                + listHtml + '</div>';
        }

        var details = document.createElement('details');
        details.className = 'ai-retrieval-details';
        details.innerHTML = '<summary class="ai-retrieval-summary">'
            + '<span class="ai-retrieval-title">' + esc(_tr('assistant.retrievalTitle', '检索过程')) + '</span>'
            + badges + '</summary>'
            + '<div class="ai-retrieval-body">' + rows + '</div>';
        /* 顶部插入：回答流式渲染只重写 content 元素 innerHTML，面板位置保持稳定 */
        bubble.insertBefore(details, bubble.firstChild);
    }

    function _openNoteFromPath(filePath: any, displayName: any, sectionTitle: any) {
        if (!filePath) return;
        var name = displayName || filePath.split('/').pop() || filePath;
        window._pendingSectionLocate = sectionTitle || '';
        if (window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(filePath, name);
            _locatePendingSection();
            return;
        }
        if (window.api && window.api.onFileSelected) {
            window.api.onFileSelected(filePath);
        }
    }

    // P0: locate a cited answer back to the exact section in the opened note.
    // The note renders asynchronously (preview markdown or tiptap editor), so we
    // poll for the heading for a short window and scroll/highlight it when found.
    function _locatePendingSection() {
        var sectionTitle = window._pendingSectionLocate || '';
        window._pendingSectionLocate = '';
        if (!sectionTitle) return;
        var attempts = 0;
        var timer = setInterval(function() {
            attempts += 1;
            if (_locateSectionInDocument(sectionTitle) || attempts > 12) {
                clearInterval(timer);
            }
        }, 300);
    }

    function _locateSectionInDocument(sectionTitle: any) {
        var segments = String(sectionTitle).split('>').map(function(s) { return s.trim(); }).filter(Boolean);
        var wanted = segments[segments.length - 1];
        if (!wanted) return false;
        var containers = [];
        var preview = document.getElementById('preview-content');
        if (preview && preview.style.display !== 'none') containers.push(preview);
        var tiptapWrap = document.getElementById('tiptap-editor-container');
        if (tiptapWrap && tiptapWrap.style.display !== 'none') {
            containers.push(tiptapWrap.querySelector('.tiptap') || tiptapWrap);
        }
        if (!containers.length) return false;
        var i, j;
        for (i = 0; i < containers.length; i++) {
            var heads = containers[i].querySelectorAll('h1, h2, h3, h4, h5, h6');
            for (j = 0; j < heads.length; j++) {
                var text = (heads[j].textContent || '').replace(/\s+/g, ' ').trim();
                if (text === wanted || text.indexOf(wanted + ' ') === 0) {
                    heads[j].scrollIntoView({ behavior: 'smooth', block: 'center' });
                    heads[j].classList.add('ai-locate-flash');
                    (function(el) {
                        setTimeout(function() { el.classList.remove('ai-locate-flash'); }, 2200);
                    })(heads[j]);
                    return true;
                }
            }
        }
        return false;
    }

    function _linkifyCitationRefs(contentEl: any, citations: any) {
        if (!contentEl || !citations || !citations.length) return;

        var byIndex: Record<number, any> = {};
        citations.forEach(function(cite: any) {
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
                                c.source_label || c.file_name || '',
                                c.section_title || ''
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
            node.parentNode!.replaceChild(frag, node);
        });
    }

    function _citationQualityText(quality: any, citationCount: any) {
        var q = quality || {};
        var level = q.level || (citationCount ? 'balanced' : 'none');
        var count = q.source_count || citationCount || 0;
        var key = 'assistant.citationQuality.' + level;
        return window.t ? window.t(key, { count: count }) : '';
    }

    function _renderCitations(contentEl: any, citations: any, quality: any) {
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

        citations.forEach(function(cite: any) {
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
                        cite.source_label || cite.file_name || '',
                        cite.section_title || ''
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
