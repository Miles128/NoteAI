(function() { 'use strict';

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

    function toggle() {
        var panel = document.getElementById('ai-panel');
        if (!panel) return;

        _panelVisible = !_panelVisible;
        if (_panelVisible) {
            panel.style.display = 'flex';
            panel.style.width = '30%';
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) toggleBtn.classList.add('active');
            if (_chatHistory.length === 0) {
                addSystemMessage('嗨，我是小忆，你的贴心个人助理～有什么可以帮你的吗？');
            }
            _scrollToBottom();
        } else {
            panel.style.display = 'none';
            var toggleBtn = document.getElementById('titlebar-ai-toggle-btn');
            if (toggleBtn) toggleBtn.classList.remove('active');
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
        var currentFile = _extractCurrentFile();

        window.api.ragChat(question, topics, tags, currentFile).then(function(result) {
            if (result && result.success === false) {
                _isStreaming = false;
                assistantEl.textContent = result.message || '请求失败';
                assistantEl.classList.remove('ai-typing');
            } else {
                setTimeout(function() {
                    if (_isStreaming && _currentStreamEl === assistantEl && !assistantEl.textContent) {
                        _isStreaming = false;
                        assistantEl.textContent = '响应超时，请检查后端服务是否正常运行';
                        assistantEl.classList.remove('ai-typing');
                        _currentStreamEl = null;
                    }
                }, 30000);
            }
        }).catch(function(err) {
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

    function _extractCurrentFile() {
        if (!window.AppState || !window.AppState.selectedFilePath) return "";
        return window.AppState.selectedFilePath;
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
        window.api.ragRebuildIndex().catch(function(err) {
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

window.toggleAIPanel = toggleAIPanel;

})();
