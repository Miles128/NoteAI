/**
 * CLI Agent Module (前端)
 *
 * 在 Inspector AI Tab 中集成第三方 CLI agent（Claude Code / OpenCode / Codex / Gemini）。
 * 对标 Tolaria 的 AiPanel + CLI agent 选择器。
 */
(function() {
    'use strict';

    var _availableAgents = [];
    var _selectedAgent = null; // null = 使用内置小忆；否则为 agent id
    var _isRunning = false;

    function _escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /**
     * 加载可用的 CLI agent 列表
     */
    function loadAgents() {
        if (!window.api || !window.api.listCliAgents) return Promise.resolve([]);

        return window.api.listCliAgents().then(function(result) {
            if (result && result.success && Array.isArray(result.agents)) {
                _availableAgents = result.agents;
                return _availableAgents;
            }
            return [];
        }).catch(function() {
            return [];
        });
    }

    /**
     * 渲染 agent 选择器到 AI Panel header
     */
    function renderAgentSelector() {
        var header = document.querySelector('#inspector-content-ai .ai-panel-header');
        if (!header) return;

        // 移除已有的选择器
        var existing = document.getElementById('cli-agent-selector');
        if (existing) existing.remove();

        var installedAgents = _availableAgents.filter(function(a) { return a.installed; });
        if (installedAgents.length === 0) return; // 没有已安装的 agent 则不显示选择器

        var selector = document.createElement('select');
        selector.id = 'cli-agent-selector';
        selector.className = 'cli-agent-selector';
        selector.title = '选择 AI Agent';

        // 内置小忆选项
        var defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '小忆';
        selector.appendChild(defaultOption);

        // 已安装的 CLI agent
        installedAgents.forEach(function(agent) {
            var opt = document.createElement('option');
            opt.value = agent.id;
            opt.textContent = agent.name;
            selector.appendChild(opt);
        });

        selector.addEventListener('change', function() {
            _selectedAgent = this.value || null;
            _updateModeBadge();
        });

        header.appendChild(selector);

        // 添加生成 AGENTS.md 按钮
        var generateBtn = document.createElement('button');
        generateBtn.id = 'cli-agent-generate-md';
        generateBtn.className = 'cli-agent-generate-btn';
        generateBtn.title = '生成 AGENTS.md（供 CLI agent 读取）';
        generateBtn.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
        generateBtn.addEventListener('click', function(e) {
            e.preventDefault();
            _generateAgentsMd();
        });

        header.appendChild(generateBtn);
    }

    function _updateModeBadge() {
        var badge = document.getElementById('ai-mode-badge');
        if (!badge) return;

        if (_selectedAgent) {
            var agent = _availableAgents.find(function(a) { return a.id === _selectedAgent; });
            if (agent) {
                badge.textContent = agent.name;
                badge.classList.add('cli-agent-active');
                return;
            }
        }
        badge.classList.remove('cli-agent-active');
        // 恢复原有模式显示
        if (window.AssistantModule && window.AssistantModule.getMode) {
            var mode = window.AssistantModule.getMode();
            badge.textContent = mode === 'agent' ?
                (window.t ? window.t('assistant.mode.agent') : '助手模式') :
                (window.t ? window.t('assistant.mode.qa') : '问答模式');
        }
    }

    /**
     * 生成 Vault AGENTS.md
     */
    function _generateAgentsMd() {
        if (!window.api || !window.api.generateVaultAgentsMd) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show('API 不可用', 'error');
            }
            return;
        }

        if (window.ToastModule && window.ToastModule.show) {
            window.ToastModule.show('正在生成 AGENTS.md...', 'info');
        }

        window.api.generateVaultAgentsMd().then(function(result) {
            if (result && result.success) {
                var msg = 'AGENTS.md 已生成' + (result.note_count !== undefined ?
                    '（' + result.note_count + ' 篇笔记，' + result.topic_count + ' 个主题）' : '');
                if (window.ToastModule && window.ToastModule.show) {
                    window.ToastModule.show(msg, 'success');
                }
            } else {
                if (window.ToastModule && window.ToastModule.show) {
                    window.ToastModule.show(result && result.message || '生成失败', 'error');
                }
            }
        }).catch(function(err) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show('生成失败: ' + (err.message || ''), 'error');
            }
        });
    }

    /**
     * 发送消息（根据选择的 agent 分发）
     */
    function sendMessage(prompt) {
        if (_isRunning) {
            return Promise.resolve({ success: false, message: '上一个任务还在运行' });
        }

        if (!_selectedAgent) {
            // 使用内置小忆
            return Promise.resolve({ success: true, use_builtin: true });
        }

        // 使用 CLI agent
        _isRunning = true;
        var messagesEl = document.getElementById('ai-panel-messages');
        if (messagesEl) {
            _appendCliMessage('user', prompt);
            _appendCliMessage('system', '正在启动 ' + _getAgentName(_selectedAgent) + '...');
        }

        return window.api.runCliAgent(_selectedAgent, prompt).then(function(result) {
            if (result && result.success && result.started) {
                // 流式输出通过事件回调处理
                return { success: true };
            }
            _isRunning = false;
            if (messagesEl) {
                _appendCliMessage('error', (result && result.message) || '启动失败');
            }
            return { success: false, message: result && result.message };
        }).catch(function(err) {
            _isRunning = false;
            if (messagesEl) {
                _appendCliMessage('error', err.message || '执行异常');
            }
            return { success: false, message: err.message };
        });
    }

    function _getAgentName(agentId) {
        var agent = _availableAgents.find(function(a) { return a.id === agentId; });
        return agent ? agent.name : agentId;
    }

    function _appendCliMessage(role, content) {
        var messagesEl = document.getElementById('ai-panel-messages');
        if (!messagesEl) return;

        var msg = document.createElement('div');
        msg.className = 'ai-msg ai-' + role;
        if (role === 'user') {
            msg.innerHTML = '<div class="ai-msg-author">你</div><div class="ai-msg-content">' + _escapeHtml(content) + '</div>';
        } else if (role === 'error') {
            msg.innerHTML = '<div class="ai-msg-content">' + _escapeHtml(content) + '</div>';
        } else {
            // CLI agent 输出（可能含多行）
            var pre = document.createElement('pre');
            pre.className = 'cli-agent-output';
            pre.textContent = content;
            msg.appendChild(pre);
        }
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    /**
     * 处理 CLI agent 事件（由 assistant.js 的事件监听器调用）
     */
    function handleEvent(payload) {
        if (!payload || typeof payload !== 'object') return;

        var type = payload.type;
        var messagesEl = document.getElementById('ai-panel-messages');

        if (type === 'cli_agent_start') {
            if (messagesEl) {
                _appendCliMessage('system', '⚡ ' + (payload.agent_name || payload.agent) + ' 已启动');
            }
        } else if (type === 'cli_agent_output') {
            if (messagesEl && payload.content) {
                // 追加到最后一个 CLI 输出消息，或创建新的
                var lastMsg = messagesEl.lastElementChild;
                var lastPre = lastMsg && lastMsg.querySelector('pre.cli-agent-output');
                if (lastPre) {
                    lastPre.textContent += payload.content;
                } else {
                    _appendCliMessage('assistant', payload.content);
                }
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
        } else if (type === 'cli_agent_done') {
            _isRunning = false;
            if (messagesEl) {
                _appendCliMessage('system', '✓ ' + (payload.agent_name || 'Agent') + ' 完成');
            }
        } else if (type === 'cli_agent_error') {
            _isRunning = false;
            if (messagesEl) {
                _appendCliMessage('error', payload.message || 'CLI agent 执行失败');
            }
        }
    }

    function getSelectedAgent() {
        return _selectedAgent;
    }

    function isRunning() {
        return _isRunning;
    }

    function init() {
        // 延迟加载，等待 AI panel 渲染完成
        setTimeout(function() {
            loadAgents().then(function() {
                renderAgentSelector();
            });
        }, 1000);
    }

    window.CliAgentModule = {
        init: init,
        loadAgents: loadAgents,
        renderAgentSelector: renderAgentSelector,
        sendMessage: sendMessage,
        handleEvent: handleEvent,
        getSelectedAgent: getSelectedAgent,
        isRunning: isRunning,
        isCliAgentMode: function() { return _selectedAgent !== null; }
    };

    document.addEventListener('DOMContentLoaded', function() {
        init();
    });
})();
