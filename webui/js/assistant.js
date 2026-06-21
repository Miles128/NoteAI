(function() { 'use strict';

window.AssistantModule = (function() {
    var _chatHistory = [];
    var _isStreaming = false;
    var _indexBuilt = false;
    var _panelVisible = false;
    /** 打开 AI 侧栏收窄等 {@link _thawAILayout} */
    var _aiLayoutSnap = null;
    var _AI_PANEL_DEFAULT_W = 300;

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
        panel.style.width = Math.min(420, Math.max(260, baseW)) + 'px';

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
            if (toggleBtn) toggleBtn.classList.add('active');
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
            if (toggleBtn) toggleBtn.classList.remove('active');
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
            newWidth = Math.max(260, Math.min(520, newWidth));
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
    var _lastArchive = null;

    function sendMessage() {
        if (_isStreaming) return;

        var input = document.getElementById('ai-input');
        if (!input) return;
        var question = input.value.trim();
        if (!question) return;

        input.value = '';

        // CLI Agent 模式：转发到 CliAgentModule
        if (window.CliAgentModule && window.CliAgentModule.isCliAgentMode && window.CliAgentModule.isCliAgentMode()) {
            window.CliAgentModule.sendMessage(question);
            return;
        }

        addUserMessage(question);
        _chatHistory.push({ role: 'user', content: question });
        _lastArchive = { question: question, answer: '', rowEl: null };

        _isStreaming = true;
        var assistantEl = addAssistantMessage();
        _currentStreamEl = assistantEl;

        var topics = _extractTopics();
        var tags = _extractTags();
        var currentFile = _extractCurrentFile();

        window.api.ragChat(question, topics, tags, currentFile).then(function(result) {
            if (result && result.started) {
                setTimeout(function() {
                    if (_isStreaming && _currentStreamEl === assistantEl && !assistantEl.textContent) {
                        _isStreaming = false;
                        assistantEl.textContent = window.t('assistant.timeout');
                        assistantEl.classList.remove('ai-typing');
                        _currentStreamEl = null;
                    }
                }, 180000);
                return;
            }
            if (result && result.success === false) {
                _isStreaming = false;
                assistantEl.textContent = result.message || window.t('assistant.requestFailed');
                assistantEl.classList.remove('ai-typing');
            }
        }).catch(function(err) {
            _isStreaming = false;
            var msg = (err && err.message) ? err.message : String(err || window.t('common.unknownError'));
            assistantEl.textContent = window.t('assistant.requestFailedMsg', { message: msg });
            assistantEl.classList.remove('ai-typing');
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

    /* 小忆：萌妹子半身像 */
    var _BOT_AVATAR_SVG = '<svg class="ai-avatar-svg" viewBox="0 0 48 48" aria-hidden="true">'
        + '<defs><linearGradient id="xy-hair" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#5b3d7a"/><stop offset="100%" stop-color="#3d2858"/></linearGradient></defs>'
        + '<path d="M8 22 C8 10 16 4 24 4 C32 4 40 10 40 22 L40 30 C40 38 34 44 24 44 C14 44 8 38 8 30 Z" fill="url(#xy-hair)"/>'
        + '<path d="M12 18 C12 12 17 8 24 8 C31 8 36 12 36 18 L36 26 C36 32 31 36 24 36 C17 36 12 32 12 26 Z" fill="#ffe8dc"/>'
        + '<ellipse cx="17" cy="22" rx="3.2" ry="4" fill="#2d1f3d"/>'
        + '<ellipse cx="31" cy="22" rx="3.2" ry="4" fill="#2d1f3d"/>'
        + '<circle cx="18" cy="20.5" r="1.3" fill="#fff"/>'
        + '<circle cx="32" cy="20.5" r="1.3" fill="#fff"/>'
        + '<circle cx="18.8" cy="21.2" r="0.5" fill="#f9a8d4"/>'
        + '<circle cx="32.8" cy="21.2" r="0.5" fill="#f9a8d4"/>'
        + '<ellipse cx="14" cy="26" rx="2.2" ry="1.2" fill="#fda4c8" opacity="0.75"/>'
        + '<ellipse cx="34" cy="26" rx="2.2" ry="1.2" fill="#fda4c8" opacity="0.75"/>'
        + '<path d="M21 28 Q24 30.5 27 28" stroke="#d9468f" stroke-width="1.2" fill="none" stroke-linecap="round"/>'
        + '<path d="M10 14 Q24 6 38 14" fill="url(#xy-hair)"/>'
        + '<path d="M6 20 L10 16 L12 22 Z" fill="#7c5cbf"/>'
        + '<path d="M42 20 L38 16 L36 22 Z" fill="#7c5cbf"/>'
        + '<ellipse cx="24" cy="10" rx="4" ry="2.5" fill="#f472b6" opacity="0.9"/>'
        + '</svg>';

    /* 用户：机器狗 */
    var _USER_AVATAR_SVG = '<svg class="ai-avatar-svg" viewBox="0 0 48 48" aria-hidden="true">'
        + '<defs><linearGradient id="dog-metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#94a3b8"/><stop offset="100%" stop-color="#64748b"/></linearGradient></defs>'
        + '<rect x="10" y="14" width="28" height="24" rx="8" fill="url(#dog-metal)" stroke="#475569" stroke-width="1"/>'
        + '<path d="M8 18 L4 10 L12 16 Z" fill="#64748b" stroke="#475569" stroke-width="0.8"/>'
        + '<path d="M40 18 L44 10 L36 16 Z" fill="#64748b" stroke="#475569" stroke-width="0.8"/>'
        + '<line x1="24" y1="8" x2="24" y2="14" stroke="#475569" stroke-width="1.5" stroke-linecap="round"/>'
        + '<circle cx="24" cy="6" r="2.5" fill="#38bdf8" stroke="#0ea5e9" stroke-width="0.8"/>'
        + '<rect x="15" y="20" width="7" height="6" rx="2" fill="#0f172a"/>'
        + '<rect x="26" y="20" width="7" height="6" rx="2" fill="#0f172a"/>'
        + '<circle cx="18.5" cy="23" r="1.8" fill="#22d3ee"/>'
        + '<circle cx="29.5" cy="23" r="1.8" fill="#22d3ee"/>'
        + '<rect x="20" y="30" width="8" height="4" rx="2" fill="#334155"/>'
        + '<circle cx="24" cy="32" r="1.2" fill="#f97316"/>'
        + '<path d="M14 36 L18 40 M34 36 L30 40" stroke="#475569" stroke-width="1.5" stroke-linecap="round"/>'
        + '<rect x="6" y="34" width="6" height="3" rx="1" fill="#94a3b8"/>'
        + '<rect x="36" y="34" width="6" height="3" rx="1" fill="#94a3b8"/>'
        + '</svg>';

    function _createAvatar(type) {
        var uid = 'av' + String(Math.random()).slice(2, 8);
        var svg = type === 'bot' ? _BOT_AVATAR_SVG : _USER_AVATAR_SVG;
        svg = svg.replace(/id="xy-hair"/g, 'id="xy-hair-' + uid + '"')
            .replace(/url\(#xy-hair\)/g, 'url(#xy-hair-' + uid + ')')
            .replace(/id="dog-metal"/g, 'id="dog-metal-' + uid + '"')
            .replace(/url\(#dog-metal\)/g, 'url(#dog-metal-' + uid + ')');
        var avatar = document.createElement('div');
        avatar.className = 'ai-avatar ai-avatar-' + type;
        avatar.setAttribute('title', type === 'bot' ? window.t('assistant.name') : window.t('assistant.userAvatar'));
        avatar.innerHTML = svg;
        return avatar;
    }

    function addUserMessage(text) {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return;
        var row = document.createElement('div');
        row.className = 'ai-msg-row ai-msg-row-user';
        var bubble = document.createElement('div');
        bubble.className = 'ai-msg ai-user';
        var content = document.createElement('div');
        content.textContent = text;
        bubble.appendChild(content);
        row.appendChild(bubble);
        row.appendChild(_createAvatar('user'));
        container.appendChild(row);
        _scrollToBottom();
    }

    function addAssistantMessage() {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return null;
        var row = document.createElement('div');
        row.className = 'ai-msg-row ai-msg-row-bot';
        row.appendChild(_createAvatar('bot'));
        var bubble = document.createElement('div');
        bubble.className = 'ai-msg ai-assistant';
        var content = document.createElement('div');
        content.className = 'ai-msg-content ai-typing';
        bubble.appendChild(content);
        row.appendChild(bubble);
        container.appendChild(row);
        _scrollToBottom();
        return content;
    }

    function addSystemMessage(text) {
        var container = document.getElementById('ai-panel-messages');
        if (!container) return;
        var div = document.createElement('div');
        div.className = 'ai-msg ai-system';
        var label = document.createElement('div');
        label.className = 'ai-msg-label';
        label.textContent = window.t('assistant.system');
        var content = document.createElement('div');
        content.textContent = text;
        div.appendChild(label);
        div.appendChild(content);
        container.appendChild(div);
        _scrollToBottom();
    }

    function _scrollToBottom() {
        /* 实际滚动容器是 .ai-panel-body（overflow-y:auto），不是 .ai-panel-messages */
        var sc = document.querySelector('#ai-panel .ai-panel-body');
        if (sc) sc.scrollTop = sc.scrollHeight;
    }

    function handleEvent(eventData) {
        if (!eventData) return;

        if (eventData.type === 'rag_chat_chunk') {
            if (_currentStreamEl) {
                _currentStreamEl.textContent += eventData.token || '';
                _scrollToBottom();
            }
        } else if (eventData.type === 'rag_chat_done') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _currentStreamEl.classList.remove('ai-typing');
                var answerText = eventData.answer || _currentStreamEl.textContent || '';
                _currentStreamEl.textContent = answerText;
                _chatHistory.push({ role: 'assistant', content: answerText });
                if (eventData.citations && eventData.citations.length > 0) {
                    _renderCitations(_currentStreamEl, eventData.citations);
                }
                if (_lastArchive) {
                    _lastArchive.answer = answerText;
                    if (eventData.suggest_save_note) {
                        _attachSaveNoteActions(_currentStreamEl, _lastArchive);
                    }
                }
            }
            _currentStreamEl = null;
        } else if (eventData.type === 'rag_error') {
            _isStreaming = false;
            if (_currentStreamEl) {
                _currentStreamEl.textContent = eventData.message || window.t('assistant.requestFailed');
                _currentStreamEl.classList.remove('ai-typing');
            }
            _currentStreamEl = null;
        } else if (eventData.type === 'rag_index_built') {
            _indexBuilt = eventData.data && eventData.data.success;
            if (_indexBuilt) {
                addSystemMessage(window.t('assistant.indexBuildDone', { count: eventData.data.chunk_count || 0 }));
            } else {
                var failMessage = (eventData.data && eventData.data.message) || window.t('common.unknownError');
                addSystemMessage(window.t('assistant.indexBuildFailed', { message: failMessage }));
            }
        } else if (eventData.type === 'rag-index-progress') {
            var pct = eventData.data && eventData.data.percent || 0;
            var msg = eventData.data && eventData.data.message || '';
            addSystemMessage(window.t('assistant.indexProgress', { percent: pct, message: msg }));
        }

        // CLI Agent 事件转发
        if (eventData.type && eventData.type.indexOf('cli_agent_') === 0) {
            if (window.CliAgentModule && window.CliAgentModule.handleEvent) {
                window.CliAgentModule.handleEvent(eventData);
            }
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

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ai-save-note-btn';
        btn.textContent = window.t('assistant.saveAsNote');
        btn.addEventListener('click', function() {
            if (!window.api || !window.api.archiveChatAnswer) return;
            btn.disabled = true;
            btn.textContent = window.t('assistant.saving');
            window.api.archiveChatAnswer({
                question: archive.question,
                answer: archive.answer
            }).then(function(res) {
                if (res && res.success) {
                    btn.textContent = window.t('common.saved');
                    hint.textContent = window.t('assistant.savedToNotes');
                    if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
                        window.refreshWorkspaceViewsAfterChange();
                    }
                } else {
                    btn.disabled = false;
                    btn.textContent = window.t('assistant.saveAsNote');
                    addSystemMessage(window.t('assistant.saveFailed', { message: (res && res.message) || window.t('common.unknownError') }));
                }
            }).catch(function(err) {
                btn.disabled = false;
                btn.textContent = window.t('assistant.saveAsNote');
                addSystemMessage(window.t('assistant.saveFailed', { message: err.message || String(err) }));
            });
        });
        actions.appendChild(btn);
        bubble.appendChild(actions);
        archive.rowEl = bubble;
    }

    function _renderCitations(contentEl, citations) {
        if (!contentEl || !citations || citations.length === 0) return;
        var bubble = contentEl.closest('.ai-msg');
        if (!bubble) return;

        var container = document.createElement('div');
        container.className = 'ai-citations';

        var header = document.createElement('div');
        header.className = 'ai-citations-header';
        header.textContent = window.t('assistant.sources') || '参考来源';
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
                var filePath = cite.file_path;
                if (filePath && window.api && window.api.onFileSelected) {
                    window.api.onFileSelected(filePath);
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
        toggle: toggle
    };
})();

function toggleAIPanel() {
    if (window.AssistantModule) window.AssistantModule.toggle();
}

window.toggleAIPanel = toggleAIPanel;

})();
