window.AssistantModule = (function() {
    var _chatHistory = [];
    var _isStreaming = false;
    var _indexBuilt = false;
    var _panelVisible = false;

    function init() {
        var input = document.getElementById('ai-input');
        var sendBtn = document.getElementById('ai-send-btn');
        if (!input || !sendBtn) return;

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        sendBtn.addEventListener('click', function() {
            sendMessage();
        });

        _setupResizers();
    }

    var _sidebarOriginalWidth = null;
    var _windowExpanded = false;

    function _resizeWindow(deltaWidth) {
        var win = (typeof getTauriWindow === 'function') ? getTauriWindow() : null;
        if (!win) return;
        win.isMaximized().then(function(maximized) {
            if (maximized) {
                win.unmaximize();
            }
            Promise.all([win.innerSize(), win.scaleFactor()]).then(function(results) {
                var size = results[0];
                var sf = results[1];
                var LogicalSize = window.__TAURI__.window.LogicalSize
                    || (window.__TAURI__.dpi && window.__TAURI__.dpi.LogicalSize);
                var logicalWidth = size.width / sf + deltaWidth;
                var logicalHeight = size.height / sf;
                if (LogicalSize) {
                    win.setSize(new LogicalSize(logicalWidth, logicalHeight));
                } else {
                    win.setSize({ type: 'Logical', width: logicalWidth, height: logicalHeight });
                }
            });
        });
    }

    function toggle() {
        var panel = document.getElementById('ai-panel');
        if (!panel) return;

        _panelVisible = !_panelVisible;
        if (_panelVisible) {
            panel.style.display = 'flex';
            panel.style.width = '480px';
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) toggleBtn.classList.add('active');
            if (_chatHistory.length === 0) {
                addSystemMessage('嗨，我是小忆，你的贴心个人助理～有什么可以帮你的吗？');
            }
            _scrollToBottom();

            var sidebar = document.getElementById('sidebar');
            if (sidebar && _sidebarOriginalWidth === null) {
                _sidebarOriginalWidth = sidebar.offsetWidth;
                var newSidebarWidth = Math.max(180, _sidebarOriginalWidth - 160);
                sidebar.style.width = newSidebarWidth + 'px';
            }

            if (!_windowExpanded) {
                _resizeWindow(320);
                _windowExpanded = true;
            }
        } else {
            panel.style.display = 'none';
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) toggleBtn.classList.remove('active');

            var sidebar = document.getElementById('sidebar');
            if (sidebar && _sidebarOriginalWidth !== null) {
                sidebar.style.width = _sidebarOriginalWidth + 'px';
                _sidebarOriginalWidth = null;
            }

            if (_windowExpanded) {
                _resizeWindow(-320);
                _windowExpanded = false;
            }
        }
    }

    function _setupResizers() {
        var panel = document.getElementById('ai-panel');
        if (!panel) return;

        var leftResizer = document.getElementById('ai-resizer-left');
        var rightResizer = document.getElementById('ai-resizer-right');

        if (leftResizer) {
            _initResizer(leftResizer, panel, 'left');
        }
        if (rightResizer) {
            rightResizer.style.display = 'none';
        }
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
        }

        function onMouseMove(e) {
            var dx = e.clientX - startX;
            var newWidth;
            if (side === 'left') {
                newWidth = startWidth - dx;
            } else {
                newWidth = startWidth + dx;
            }
            newWidth = Math.max(280, Math.min(700, newWidth));
            panel.style.width = newWidth + 'px';

            if (side === 'left') {
                var widthDiff = newWidth - startWidth;
                _resizeWindow(widthDiff);
                startX = e.clientX;
                startWidth = newWidth;
            }
        }

        function onMouseUp() {
            resizerEl.classList.remove('ai-resizer-active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }

        resizerEl.addEventListener('mousedown', onMouseDown);
    }

    var _currentStreamEl = null;

    function sendMessage() {
        if (_isStreaming) return;

        var input = document.getElementById('ai-input');
        if (!input) return;
        var question = input.value.trim();
        if (!question) return;

        input.value = '';
        addUserMessage(question);
        _chatHistory.push({ role: 'user', content: question });

        _isStreaming = true;
        var assistantEl = addAssistantMessage();
        _currentStreamEl = assistantEl;

        var topics = _extractTopics();
        var tags = _extractTags();

        window.api.rag_chat(question, topics, tags).catch(function(err) {
            _isStreaming = false;
            var msg = (err && err.message) ? err.message : String(err || '未知错误');
            assistantEl.textContent = '请求失败: ' + msg;
            assistantEl.classList.remove('ai-typing');
        });
    }

    function _extractTopics() {
        if (!window.AppState || !window.AppState.lastTopicData) return null;
        var data = window.AppState.lastTopicData;
        if (!data || !data.topics) return null;
        return data.topics.map(function(t) { return t.name; });
    }

    function _extractTags() {
        if (!window.AppState || !window.AppState.lastTagsData) return null;
        var data = window.AppState.lastTagsData;
        if (!data || !data.tags) return null;
        return data.tags.map(function(t) { return t.name; });
    }

    function _createAvatar(type) {
        var avatar = document.createElement('div');
        avatar.className = 'ai-avatar ai-avatar-' + type;
        if (type === 'bot') {
            avatar.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="8" width="14" height="10" rx="3"/><circle cx="9.5" cy="13" r="1.2" fill="currentColor"/><circle cx="14.5" cy="13" r="1.2" fill="currentColor"/><line x1="12" y1="4" x2="12" y2="8"/><circle cx="12" cy="3.5" r="1.2" fill="currentColor"/><line x1="8" y1="18" x2="8" y2="20"/><line x1="16" y1="18" x2="16" y2="20"/></svg>';
        } else {
            avatar.textContent = '你';
        }
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
        label.textContent = '系统';
        var content = document.createElement('div');
        content.textContent = text;
        div.appendChild(label);
        div.appendChild(content);
        container.appendChild(div);
        _scrollToBottom();
    }

    function _scrollToBottom() {
        var container = document.getElementById('ai-panel-messages');
        if (container) container.scrollTop = container.scrollHeight;
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
                _chatHistory.push({ role: 'assistant', content: _currentStreamEl.textContent });
            }
            _currentStreamEl = null;
        } else if (eventData.type === 'rag_index_built') {
            _indexBuilt = eventData.data && eventData.data.success;
            if (_indexBuilt) {
                addSystemMessage('知识库索引构建完成，共 ' + (eventData.data.chunk_count || 0) + ' 个片段');
            } else {
                addSystemMessage('索引构建失败: ' + (eventData.data.message || '未知错误'));
            }
        }
    }

    function rebuildIndex() {
        addSystemMessage('正在构建知识库索引...');
        window.api.rag_rebuild_index().catch(function(err) {
            addSystemMessage('索引构建请求失败: ' + err.message);
        });
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
