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
    var _streamPre = null;
    var _streamMsg = null;
    var _lineBuffer = '';
    var _toolCards = {};
    var _toolCtx = {};

    function _summary() {
        return window.CliToolSummary || {};
    }

    function _filterCliOutput(content) {
        if (!content) return '';
        var trimmed = content.trim();
        if (!trimmed) return '';

        if (/^\$\s/.test(trimmed)) return '';
        if (/^\[thinking\]/i.test(trimmed)) return '';
        if (/^\[tool:/i.test(trimmed)) return '';
        if (/^\[tool result\]/i.test(trimmed)) return '';
        if (/^Ignoring --/i.test(trimmed)) return '';
        if (/^Error:/i.test(trimmed)) return '';

        if (trimmed.charAt(0) === '{') {
            try {
                var parsed = JSON.parse(trimmed);
                if (!parsed) return '';
                if (parsed.type === 'system' || parsed.type === 'user') return '';
                if (parsed.type === 'tool_use' || parsed.type === 'tool_result') return '';
                if (parsed.tool_use || parsed.tool_result) return '';
                if (parsed.message && parsed.message.content) return '';
            } catch (_e) {
                if (/"type"\s*:\s*"(system|user|tool_use|tool_result|assistant|stream_event)"/.test(trimmed)) return '';
            }
        }
        return content;
    }

    function _tryParseToolLine(line) {
        var trimmed = (line || '').trim();
        if (!trimmed || trimmed.charAt(0) !== '{') return null;
        var obj;
        try { obj = JSON.parse(trimmed); } catch (_e) { return null; }
        if (!obj || typeof obj !== 'object') return null;

        if (obj.type === 'tool_use' || (obj.name && obj.input && !obj.type)) {
            return {
                phase: 'start',
                tool_id: obj.id || obj.tool_use_id || '',
                tool: obj.name || obj.tool,
                input: obj.input || {}
            };
        }
        if (obj.type === 'tool_result') {
            return {
                phase: 'done',
                tool_id: obj.tool_use_id || obj.id || '',
                tool: obj.name || obj.tool,
                input: obj.input || {},
                success: !obj.is_error,
                result: obj.content || obj.result || ''
            };
        }
        if (obj.type === 'assistant' && obj.message && obj.message.content) {
            var blocks = obj.message.content;
            for (var i = 0; i < blocks.length; i++) {
                if (blocks[i] && blocks[i].type === 'tool_use') {
                    return {
                        phase: 'start',
                        tool_id: blocks[i].id || '',
                        tool: blocks[i].name,
                        input: blocks[i].input || {}
                    };
                }
            }
        }
        if (obj.type === 'user' && obj.message && obj.message.content) {
            var ublocks = obj.message.content;
            for (var j = 0; j < ublocks.length; j++) {
                if (ublocks[j] && ublocks[j].type === 'tool_result') {
                    return {
                        phase: 'done',
                        tool_id: ublocks[j].tool_use_id || '',
                        success: !ublocks[j].is_error,
                        result: ublocks[j].content || ''
                    };
                }
            }
        }
        return null;
    }

    function _toolCardKey(payload) {
        return payload.tool_id || ((payload.tool || 'tool') + ':' + (payload.phase || 'start'));
    }

    function _buildToolCard(payload) {
        var sum = _summary();
        var toolName = payload.tool || 'tool';
        var isDone = payload.phase === 'done';
        var callText = isDone
            ? sum.describeCall(toolName, payload.input)
            : sum.describeRunning(toolName, payload.input);
        var detailText = isDone
            ? sum.describeResult(toolName, payload.input, payload.result, payload.success !== false)
            : sum.describeCall(toolName, payload.input);

        var details = document.createElement('details');
        details.className = 'cli-tool-activity' + (isDone ? ' is-done' : ' is-running');
        if (!isDone) details.open = false;

        var summary = document.createElement('summary');
        summary.className = 'cli-tool-summary';
        summary.textContent = callText;
        details.appendChild(summary);

        var body = document.createElement('div');
        body.className = 'cli-tool-detail';
        body.textContent = detailText;
        details.appendChild(body);

        return details;
    }

    function _updateToolCard(card, payload) {
        var sum = _summary();
        var toolName = payload.tool || card.dataset.tool || 'tool';
        var summaryEl = card.querySelector('.cli-tool-summary');
        var bodyEl = card.querySelector('.cli-tool-detail');
        card.classList.remove('is-running');
        card.classList.add('is-done');
        card.open = false;
        if (summaryEl) {
            summaryEl.textContent = sum.describeCall(toolName, payload.input);
        }
        if (bodyEl) {
            bodyEl.textContent = sum.describeResult(
                toolName,
                payload.input,
                payload.result,
                payload.success !== false
            );
        }
    }

    function _upsertToolCard(payload) {
        if (!payload || !payload.phase) return;
        var container = _ensureStreamContainer();
        if (!container) return;

        var key = _toolCardKey(payload);
        if (payload.phase === 'start') {
            if (payload.tool_id) {
                _toolCtx[payload.tool_id] = {
                    tool: payload.tool,
                    input: payload.input || {}
                };
            }
            var existing = payload.tool_id ? _toolCards[payload.tool_id] : null;
            if (existing && existing.isConnected) {
                if (payload.input_ready) {
                    var sumEl = existing.querySelector('.cli-tool-summary');
                    if (sumEl) {
                        sumEl.textContent = _summary().describeRunning(payload.tool, payload.input);
                    }
                }
                return;
            }
            var card = _buildToolCard(payload);
            card.dataset.tool = payload.tool || '';
            card.dataset.toolId = payload.tool_id || key;
            _toolCards[key] = card;
            if (payload.tool_id) {
                _toolCards[payload.tool_id] = card;
            }
            container.appendChild(card);
            _streamPre = null;
            _scrollCliMessages();
            return;
        }

        if (payload.phase === 'done') {
            var cardDone = (payload.tool_id && _toolCards[payload.tool_id]) || _toolCards[key];
            if (!payload.tool && payload.tool_id && _toolCtx[payload.tool_id]) {
                payload.tool = _toolCtx[payload.tool_id].tool;
            }
            if (!payload.input && payload.tool_id && _toolCtx[payload.tool_id]) {
                payload.input = _toolCtx[payload.tool_id].input;
            }
            if (!payload.tool && cardDone && cardDone.dataset.tool) {
                payload.tool = cardDone.dataset.tool;
            }
            if (cardDone && cardDone.isConnected) {
                _updateToolCard(cardDone, payload);
            } else {
                var doneCard = _buildToolCard(payload);
                doneCard.dataset.tool = payload.tool || '';
                _toolCards[key] = doneCard;
                container.appendChild(doneCard);
                _streamPre = null;
            }
            _scrollCliMessages();
        }
    }

    function _scrollCliMessages() {
        var sc = document.querySelector('#inspector-content-cli .ai-panel-body');
        if (sc) sc.scrollTop = sc.scrollHeight;
    }

    function _dismissEmptyHint() {
        var hint = document.getElementById('cli-empty-hint');
        if (hint) hint.remove();
    }

    function _resetStreamPre() {
        _streamPre = null;
        _streamMsg = null;
        _lineBuffer = '';
        _toolCards = {};
        _toolCtx = {};
    }

    function _ensureStreamContainer() {
        if (_streamMsg && _streamMsg.isConnected) return _streamMsg;

        var messagesEl = document.getElementById('cli-panel-messages');
        if (!messagesEl) return null;

        _streamMsg = document.createElement('div');
        _streamMsg.className = 'ai-chat-line ai-msg ai-assistant cli-agent-stream';
        var speaker = document.createElement('span');
        speaker.className = 'ai-msg-speaker';
        speaker.textContent = _cliSpeakerLabel('assistant') + '：';
        _streamMsg.appendChild(speaker);
        messagesEl.appendChild(_streamMsg);
        _scrollCliMessages();
        return _streamMsg;
    }

    function _ensureStreamPre() {
        var container = _ensureStreamContainer();
        if (!container) return null;
        if (_streamPre && _streamPre.isConnected && _streamPre.parentElement === container) {
            return _streamPre;
        }

        _streamPre = document.createElement('pre');
        _streamPre.className = 'cli-agent-output cli-agent-output-inline';
        container.appendChild(_streamPre);
        return _streamPre;
    }

    function _processOutputLine(line) {
        var toolPayload = _tryParseToolLine(line);
        if (toolPayload) {
            _upsertToolCard(toolPayload);
            return;
        }
        var filtered = _filterCliOutput(line ? line + '\n' : '');
        if (!filtered) return;
        var pre = _ensureStreamPre();
        if (!pre) return;
        pre.textContent += filtered;
    }

    function _appendAssistantOutput(content) {
        if (!content) return;
        _lineBuffer += content;
        var parts = _lineBuffer.split('\n');
        _lineBuffer = parts.pop() || '';
        for (var i = 0; i < parts.length; i++) {
            _processOutputLine(parts[i]);
        }
    }

    function _flushOutputBuffer() {
        if (!_lineBuffer) return;
        var rest = _lineBuffer;
        _lineBuffer = '';
        _processOutputLine(rest);
    }

    function _setRunningState(running) {
        _isRunning = running;
        var btn = document.getElementById('cli-send-btn');
        var badge = document.getElementById('cli-mode-badge');
        if (btn) btn.disabled = !!running;
        if (!badge || !_selectedAgent) return;

        if (running) {
            if (!badge.dataset.prevText) {
                badge.dataset.prevText = badge.textContent || '';
            }
            badge.textContent = window.t ? window.t('cliAgent.running') : '运行中…';
            badge.classList.add('cli-agent-running');
        } else {
            if (badge.dataset.prevText) {
                badge.textContent = badge.dataset.prevText;
                delete badge.dataset.prevText;
            }
            badge.classList.remove('cli-agent-running');
        }
    }

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
            var msg = (result && result.message) || 'list_cli_agents 返回异常';
            console.error('[CliAgent]', msg, result);
            return [];
        }).catch(function(err) {
            console.error('[CliAgent] listCliAgents failed:', err);
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(
                    (window.t ? window.t('cli.noAgent') : '未检测到 CLI Agent') + ': ' + (err.message || err),
                    'error'
                );
            }
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
        defaultOption.textContent = window.t ? window.t('cliAgent.selectAgent') : '选择 Agent';
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
            badge.hidden = false;
        } else {
            badge.textContent = window.t ? window.t('cliAgent.selectAgent') : '选择 Agent';
            badge.classList.remove('cli-agent-active');
            badge.hidden = true;
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

    function _cliSpeakerLabel(role) {
        if (role === 'user') {
            return (window.t && window.t('assistant.userLabel')) || '你';
        }
        if (role === 'error') {
            return (window.t && window.t('assistant.system')) || '系统';
        }
        return _getAgentName(_selectedAgent) || 'CLI';
    }

    function _appendCliMessage(role, content) {
        var messagesEl = document.getElementById('cli-panel-messages');
        if (!messagesEl) return;

        var msg = document.createElement('div');
        msg.className = 'ai-chat-line ai-msg ai-' + role;
        var speaker = document.createElement('span');
        speaker.className = 'ai-msg-speaker';
        speaker.textContent = _cliSpeakerLabel(role) + '：';

        if (role === 'user' || role === 'error') {
            var body = document.createElement('span');
            body.className = 'ai-msg-content';
            body.textContent = content;
            msg.appendChild(speaker);
            msg.appendChild(body);
        } else {
            var pre = document.createElement('pre');
            pre.className = 'cli-agent-output cli-agent-output-inline';
            pre.textContent = content;
            msg.appendChild(speaker);
            msg.appendChild(pre);
        }
        messagesEl.appendChild(msg);
        _scrollCliMessages();
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

        _dismissEmptyHint();
        _setRunningState(true);
        _resetStreamPre();
        _appendCliMessage('user', prompt);

        return window.api.runCliAgent(_selectedAgent, prompt).then(function(result) {
            if (result && result.success && result.started) {
                return { success: true };
            }
            _setRunningState(false);
            _appendCliMessage('error', (result && result.message) || (window.t ? window.t('cliAgent.failed') : '启动失败'));
            return { success: false, message: result && result.message };
        }).catch(function(err) {
            _setRunningState(false);
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
            _setRunningState(true);
        } else if (type === 'cli_agent_tool') {
            _upsertToolCard(payload);
        } else if (type === 'cli_agent_output') {
            _appendAssistantOutput(payload.content || '');
        } else if (type === 'cli_agent_done') {
            _flushOutputBuffer();
            _setRunningState(false);
            _resetStreamPre();
        } else if (type === 'cli_agent_error') {
            _flushOutputBuffer();
            _setRunningState(false);
            _resetStreamPre();
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
        _updateModeBadge();
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
