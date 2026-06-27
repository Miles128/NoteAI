/**
 * CLI Agent Module (前端)
 *
 * 在 Inspector 的独立 CLI Tab 中集成第三方 CLI agent（Claude Code / OpenCode / Codex / Gemini）。
 * 与小忆助手的 RAG 问答完全分离：AI Tab 只走内置助手，CLI Tab 只走外部 CLI agent。
 */
(function() {
    'use strict';

    var _availableAgents = [];
    var _selectedAgent = null;
    var _isRunning = false;
    var _bindingsDone = false;

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
     * 渲染 agent 选择器到 CLI Tab header
     */
    function renderAgentSelector() {
        var header = document.querySelector('#inspector-content-cli .ai-panel-header');
        if (!header) return;

        var existing = document.getElementById('cli-agent-selector');
        if (existing) existing.remove();

        var installedAgents = _availableAgents.filter(function(a) { return a.installed; });

        var selector = document.createElement('select');
        selector.id = 'cli-agent-selector';
        selector.className = 'cli-agent-selector';
        selector.title = window.t ? window.t('cliAgent.selectAgent') : '选择 AI Agent';

        // 未安装任何 agent 时仍然保留选择器占位，但提示未安装
        var defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = window.t ? window.t('cli.defaultName') : '小忆';
        selector.appendChild(defaultOption);

        installedAgents.forEach(function(agent) {
            var opt = document.createElement('option');
            opt.value = agent.id;
            opt.textContent = agent.name;
            if (agent.resolved_path) {
                opt.title = '已安装：' + agent.resolved_path;
            }
            selector.appendChild(opt);
        });

        if (installedAgents.length === 0) {
            selector.disabled = true;
            selector.title = window.t ? window.t('cli.noAgent') : '未检测到已安装的 CLI Agent';
        }

        selector.addEventListener('change', function() {
            _selectedAgent = this.value || null;
            _updateModeBadge();
            _updateInputPlaceholder();
        });

        header.appendChild(selector);

        // 生成 AGENTS.md 按钮
        var existingBtn = document.getElementById('cli-agent-generate-md');
        if (existingBtn) existingBtn.remove();

        var generateBtn = document.createElement('button');
        generateBtn.id = 'cli-agent-generate-md';
        generateBtn.className = 'cli-agent-generate-btn';
        generateBtn.title = window.t ? window.t('cliAgent.generateMd') : '生成 AGENTS.md';
        generateBtn.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
        generateBtn.addEventListener('click', function(e) {
            e.preventDefault();
            _generateAgentsMd();
        });

        header.appendChild(generateBtn);
    }

    function _updateModeBadge() {
        var badge = document.getElementById('cli-mode-badge');
        if (!badge) return;

        if (_selectedAgent) {
            var agent = _availableAgents.find(function(a) { return a.id === _selectedAgent; });
            badge.textContent = agent ? agent.name : _selectedAgent;
            badge.classList.add('cli-agent-active');
        } else {
            badge.textContent = window.t ? window.t('cli.defaultName') : '小忆';
            badge.classList.remove('cli-agent-active');
        }
    }

    function _updateInputPlaceholder() {
        var input = document.getElementById('cli-input');
        if (!input) return;
        if (_selectedAgent) {
            var agent = _availableAgents.find(function(a) { return a.id === _selectedAgent; });
            var name = agent ? agent.name : _selectedAgent;
            input.placeholder = window.t ? window.t('assistant.cli.placeholder', { agent: name }) : ('发送给 ' + name + '...');
        } else {
            input.placeholder = window.t ? window.t('cli.inputPlaceholder') : '输入指令...';
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
            window.ToastModule.show(window.t ? window.t('cliAgent.generating') : '正在生成 AGENTS.md...', 'info');
        }

        window.api.generateVaultAgentsMd().then(function(result) {
            if (result && result.success) {
                var msg = (window.t ? window.t('cliAgent.generateSuccess') : 'AGENTS.md 已生成') +
                    (result.note_count !== undefined ?
                    '（' + result.note_count + ' 篇笔记，' + result.topic_count + ' 个主题）' : '');
                if (window.ToastModule && window.ToastModule.show) {
                    window.ToastModule.show(msg, 'success');
                }
            } else {
                if (window.ToastModule && window.ToastModule.show) {
                    window.ToastModule.show(result && result.message || (window.t ? window.t('cliAgent.generateFailed') : '生成失败'), 'error');
                }
            }
        }).catch(function(err) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show((window.t ? window.t('cliAgent.generateFailed') : '生成失败') + ': ' + (err.message || ''), 'error');
            }
        });
    }

    function _getAgentName(agentId) {
        var agent = _availableAgents.find(function(a) { return a.id === agentId; });
        return agent ? agent.name : agentId;
    }

    function _appendCliMessage(role, content) {
        var messagesEl = document.getElementById('cli-panel-messages');
        if (!messagesEl) return;

        var msg = document.createElement('div');
        msg.className = 'ai-msg ai-' + role;
        if (role === 'user') {
            msg.innerHTML = '<div class="ai-msg-author">你</div><div class="ai-msg-content">' + _escapeHtml(content) + '</div>';
        } else if (role === 'error') {
            msg.innerHTML = '<div class="ai-msg-content">' + _escapeHtml(content) + '</div>';
        } else {
            var pre = document.createElement('pre');
            pre.className = 'cli-agent-output';
            pre.textContent = content;
            msg.appendChild(pre);
        }
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    /**
     * 发送消息（CLI Tab 专用）
     */
    function sendCliMessage(prompt) {
        if (_isRunning) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(window.t ? window.t('cliAgent.starting') : '上一个任务还在运行', 'warning');
            }
            return Promise.resolve({ success: false, message: '上一个任务还在运行' });
        }

        if (!_selectedAgent) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(window.t ? window.t('cliAgent.selectAgent') : '请先选择 CLI Agent', 'warning');
            }
            return Promise.resolve({ success: false, message: '未选择 CLI Agent' });
        }

        _isRunning = true;
        _appendCliMessage('user', prompt);
        _appendCliMessage('system', (window.t ? window.t('cliAgent.starting') : '正在启动') + ' ' + _getAgentName(_selectedAgent) + '...');

        return window.api.runCliAgent(_selectedAgent, prompt).then(function(result) {
            if (result && result.success && result.started) {
                return { success: true };
            }
            _isRunning = false;
            _appendCliMessage('error', (result && result.message) || (window.t ? window.t('cliAgent.failed') : '启动失败'));
            return { success: false, message: result && result.message };
        }).catch(function(err) {
            _isRunning = false;
            _appendCliMessage('error', err.message || '执行异常');
            return { success: false, message: err.message };
        });
    }

    /**
     * 处理 CLI agent 事件
     */
    function handleEvent(payload) {
        if (!payload || typeof payload !== 'object') return;

        var type = payload.type;

        if (type === 'cli_agent_start') {
            _appendCliMessage('system', '⚡ ' + (payload.agent_name || payload.agent) + ' ' + (window.t ? window.t('cliAgent.starting') : '已启动'));
        } else if (type === 'cli_agent_output') {
            if (payload.content) {
                var messagesEl = document.getElementById('cli-panel-messages');
                if (!messagesEl) return;
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
            _appendCliMessage('system', '✓ ' + (payload.agent_name || 'Agent') + ' ' + (window.t ? window.t('cliAgent.completed') : '完成'));
        } else if (type === 'cli_agent_error') {
            _isRunning = false;
            _appendCliMessage('error', payload.message || (window.t ? window.t('cliAgent.failed') : 'CLI agent 执行失败'));
        }
    }

    function _ensureBindings() {
        if (_bindingsDone) return;

        var input = document.getElementById('cli-input');
        var sendBtn = document.getElementById('cli-send-btn');
        if (!input || !sendBtn) return;

        input.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter') return;
            if (e.shiftKey) return;
            e.preventDefault();
            var prompt = input.value.trim();
            if (!prompt) return;
            input.value = '';
            sendCliMessage(prompt);
        });

        sendBtn.addEventListener('click', function() {
            var prompt = input.value.trim();
            if (!prompt) return;
            input.value = '';
            sendCliMessage(prompt);
        });

        _bindingsDone = true;
    }

    function init() {
        _ensureBindings();
        setTimeout(function() {
            loadAgents().then(function() {
                renderAgentSelector();
                _updateModeBadge();
                _updateInputPlaceholder();
            });
        }, 1000);
    }

    window.CliAgentModule = {
        init: init,
        loadAgents: loadAgents,
        renderAgentSelector: renderAgentSelector,
        sendMessage: sendCliMessage,
        handleEvent: handleEvent,
        getSelectedAgent: function() { return _selectedAgent; },
        isRunning: function() { return _isRunning; },
        isCliAgentMode: function() { return _selectedAgent !== null; }
    };

    document.addEventListener('DOMContentLoaded', function() {
        init();
    });
})();
