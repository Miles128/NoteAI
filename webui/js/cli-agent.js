/**
 * CLI Agent Module (前端)
 *
 * 在 Inspector 的独立 CLI Tab 中集成第三方 CLI agent（Claude Code / OpenCode / Codex / Gemini）。
 * 与 RAG 助手的问答完全分离：AI Tab 只走内置 RAG，CLI Tab 只走外部 CLI agent。
 */
(function() {
    'use strict';

    var _availableAgents = [];
    var _selectedAgent = null;
    var _savedCliAgentId = '';
    var _isRunning = false;
    var _bindingsDone = false;
    var _streamContentEl = null;
    var _streamRawText = '';
    var _streamMsg = null;
    var _lineBuffer = '';
    var _toolCards = {};
    var _toolCtx = {};
    var _workflowDetails = null;
    var _workflowCount = 0;
    var _workflowLatestText = '';
    var _timeoutNoticeEl = null;
    var _sessionActive = false;
    var _sendBtnDefaultHtml = '';

    var _SEND_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>';
    var _STOP_ICON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="1"></rect></svg>';

    function _summary() {
        return window.CliToolSummary || {};
    }

    function _stripAnsi(text) {
        if (!text) return '';
        return String(text)
            .replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '')
            .replace(/\x9B[0-?]*[ -/]*[@-~]/g, '')
            .replace(/\[(?:\d{1,3}(?:;\d{1,3})*)?m/g, '');
    }

    function _isOpenCodeWorkflowLine(trimmed) {
        if (!trimmed || _selectedAgent !== 'opencode') return false;
        if (/^>\s/.test(trimmed)) return true;
        if (/^[⚙✱✗→•✓]/.test(trimmed)) return true;
        if (/^noteai-vault_/i.test(trimmed)) return true;
        if (/^\$\s/.test(trimmed)) return true;
        if (/\b(Explore Agent|General Agent|Build Agent)\b/.test(trimmed)) return true;
        if (/^Error:/i.test(trimmed)) return true;
        if (/^Glob "/i.test(trimmed)) return true;
        if (/^\d+ matches?$/.test(trimmed)) return true;
        if (/^Read .+ failed$/i.test(trimmed)) return true;
        return false;
    }

    function _updateSessionBadge() {
        var badge = document.getElementById('cli-session-badge');
        if (!badge) return;
        if (_sessionActive && _selectedAgent) {
            badge.textContent = window.t ? window.t('cliAgent.sessionContinue') : '续聊中';
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    function startNewCliSession() {
        if (!_selectedAgent || !window.api || !window.api.clearCliAgentSession) {
            return Promise.resolve({ success: false });
        }
        return window.api.clearCliAgentSession(_selectedAgent).then(function(result) {
            _sessionActive = false;
            _updateSessionBadge();
            if (result && result.success && window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(
                    window.t ? window.t('cliAgent.newSessionDone') : '已开始新对话',
                    'info'
                );
            }
            return result;
        });
    }

    function _truncateText(text, maxLen) {
        var s = String(text || '').trim();
        if (s.length <= maxLen) return s;
        return s.slice(0, maxLen - 1) + '…';
    }

    function _workflowStatusLabel() {
        if (_workflowCount > 0) {
            return (window.t ? window.t('cliAgent.workflowRunning') : '运行中') +
                ' · ' + (window.t ? window.t('cliAgent.workflowStepsShort', { count: _workflowCount }) : (_workflowCount + ' 步'));
        }
        return window.t ? window.t('cliAgent.workflowRunning') : '运行中';
    }

    function _updateWorkflowSummary() {
        if (!_workflowDetails || !_workflowDetails.isConnected) return;
        var labelEl = _workflowDetails.querySelector('.cli-workflow-status-label');
        var hintEl = _workflowDetails.querySelector('.cli-workflow-status-hint');
        if (labelEl) labelEl.textContent = _workflowStatusLabel();
        if (hintEl) {
            hintEl.textContent = _workflowLatestText ? _truncateText(_workflowLatestText, 72) : '';
            hintEl.hidden = !_workflowLatestText;
        }
    }

    function _ensureWorkflowDetails() {
        var container = _ensureStreamContainer();
        if (!container) return null;
        if (_workflowDetails && _workflowDetails.isConnected) {
            return _workflowDetails;
        }

        _workflowDetails = document.createElement('details');
        _workflowDetails.className = 'cli-workflow-block cli-tool-activity cli-workflow-activity is-running';
        _workflowDetails.open = false;

        var summary = document.createElement('summary');
        summary.className = 'cli-workflow-status cli-tool-summary';

        var pulse = document.createElement('span');
        pulse.className = 'cli-workflow-pulse';
        pulse.setAttribute('aria-hidden', 'true');
        summary.appendChild(pulse);

        var label = document.createElement('span');
        label.className = 'cli-workflow-status-label';
        label.textContent = _workflowStatusLabel();
        summary.appendChild(label);

        var hint = document.createElement('span');
        hint.className = 'cli-workflow-status-hint';
        hint.hidden = true;
        summary.appendChild(hint);

        var chevron = document.createElement('span');
        chevron.className = 'cli-workflow-status-chevron';
        chevron.textContent = window.t ? window.t('cliAgent.workflowDetails') : '详情';
        summary.appendChild(chevron);

        _workflowDetails.appendChild(summary);

        var body = document.createElement('div');
        body.className = 'cli-workflow-steps';
        _workflowDetails.appendChild(body);

        container.appendChild(_workflowDetails);
        _streamContentEl = null;
        return _workflowDetails;
    }

    function _showRunningWorkflow() {
        _ensureWorkflowDetails();
        _updateWorkflowSummary();
    }

    function _appendWorkflowStep(text) {
        var details = _ensureWorkflowDetails();
        if (!details) return;

        _workflowCount += 1;
        _workflowLatestText = text;
        var body = details.querySelector('.cli-workflow-steps');
        if (!body) return;

        var step = document.createElement('div');
        step.className = 'cli-workflow-step';
        if (/^✗|^Error:/i.test(text)) {
            step.classList.add('is-error');
        } else if (/^✓/.test(text)) {
            step.classList.add('is-done');
        }
        step.textContent = text;
        body.appendChild(step);
        body.scrollTop = body.scrollHeight;

        details.classList.add('is-running');
        details.classList.remove('is-done');
        _updateWorkflowSummary();
        _scrollCliMessages();
    }

    function _finalizeWorkflow() {
        if (!_workflowDetails || !_workflowDetails.isConnected) return;
        _workflowDetails.classList.remove('is-running');
        _workflowDetails.classList.add('is-done');
        _workflowDetails.open = false;
        _updateWorkflowSummary();
    }

    function _ensureTimeoutNotice() {
        var body = document.querySelector('#inspector-content-cli .ai-panel-body');
        if (!body) return null;
        if (_timeoutNoticeEl && _timeoutNoticeEl.isConnected) {
            return _timeoutNoticeEl;
        }
        _timeoutNoticeEl = document.createElement('div');
        _timeoutNoticeEl.className = 'cli-timeout-notice';
        _timeoutNoticeEl.hidden = true;
        body.insertBefore(_timeoutNoticeEl, body.firstChild);
        return _timeoutNoticeEl;
    }

    function _showTimeoutNotice(payload) {
        var notice = _ensureTimeoutNotice();
        if (!notice) return;
        var seconds = payload.seconds || 0;
        var key = payload.kind === 'idle' ? 'cliAgent.timeoutWarningIdle' : 'cliAgent.timeoutWarningTotal';
        var fallback = payload.kind === 'idle'
            ? ('已超过 ' + seconds + ' 秒无新输出，Agent 可能仍在处理。可随时点击停止。')
            : ('任务已运行超过 ' + seconds + ' 秒，仍在继续。可随时点击停止。');
        notice.textContent = window.t ? window.t(key, { seconds: seconds }) : fallback;
        notice.hidden = false;
    }

    function _hideTimeoutNotice() {
        if (_timeoutNoticeEl) {
            _timeoutNoticeEl.hidden = true;
            _timeoutNoticeEl.textContent = '';
        }
    }

    function _filterCliOutput(content) {
        if (!content) return '';
        var trimmed = content.trim();
        if (!trimmed) return '';

        if (_isOpenCodeWorkflowLine(trimmed)) return '';
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
            _streamContentEl = null;
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
                _streamContentEl = null;
            }
            _scrollCliMessages();
        }
    }

    function _renderMarkdownHtml(text) {
        if (!text) return '';
        if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
            return window.EditorModule.renderMarkdownPreview(text);
        }
        if (typeof marked !== 'undefined') {
            try {
                var rawHtml = marked.parse(text);
                return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : _escapeHtml(text);
            } catch (e) {
                console.error('[CliAgent] Markdown parse error:', e);
            }
        }
        return '<pre>' + _escapeHtml(text) + '</pre>';
    }

    function _setCliMarkdown(contentEl, text) {
        if (!contentEl) return;
        contentEl.classList.add('ai-msg-content', 'ai-msg-md', 'preview-content');
        contentEl.innerHTML = _renderMarkdownHtml(text);
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
        _streamContentEl = null;
        _streamRawText = '';
        _streamMsg = null;
        _lineBuffer = '';
        _toolCards = {};
        _toolCtx = {};
        _workflowDetails = null;
        _workflowCount = 0;
        _workflowLatestText = '';
        _hideTimeoutNotice();
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

    function _ensureStreamContent() {
        var container = _ensureStreamContainer();
        if (!container) return null;
        if (_streamContentEl && _streamContentEl.isConnected && _streamContentEl.parentElement === container) {
            return _streamContentEl;
        }

        _streamContentEl = document.createElement('div');
        _streamContentEl.className = 'cli-agent-output cli-agent-output-inline';
        container.appendChild(_streamContentEl);
        return _streamContentEl;
    }

    function _processOutputLine(line) {
        line = _stripAnsi(line || '');
        var trimmed = line.trim();
        if (!trimmed) return;

        var toolPayload = _tryParseToolLine(trimmed);
        if (toolPayload) {
            _upsertToolCard(toolPayload);
            return;
        }
        if (_isOpenCodeWorkflowLine(trimmed)) {
            _appendWorkflowStep(trimmed);
            return;
        }
        var filtered = _filterCliOutput(line ? line + '\n' : '');
        if (!filtered) return;
        var contentEl = _ensureStreamContent();
        if (!contentEl) return;
        _streamRawText += _stripAnsi(filtered);
        _setCliMarkdown(contentEl, _streamRawText);
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
        var input = document.getElementById('cli-input');

        if (btn) {
            if (!_sendBtnDefaultHtml) {
                _sendBtnDefaultHtml = btn.innerHTML;
            }
            btn.disabled = false;
            btn.classList.toggle('cli-stop-btn', !!running);
            btn.innerHTML = running ? _STOP_ICON : (_sendBtnDefaultHtml || _SEND_ICON);
            btn.title = running
                ? ((window.t && window.t('cliAgent.stop')) || '停止')
                : ((window.t && window.t('assistant.send')) || '发送');
            btn.setAttribute('aria-label', btn.title);
        }
        if (input) {
            input.disabled = !!running;
        }

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

    function stopCliAgent() {
        if (!_isRunning || !window.api || !window.api.stopCliAgent) {
            return Promise.resolve({ success: false });
        }
        return window.api.stopCliAgent().then(function(result) {
            if (result && !result.success && window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(result.message || '无法停止', 'warning');
            }
            return result;
        }).catch(function(err) {
            if (window.ToastModule && window.ToastModule.show) {
                window.ToastModule.show(err.message || '停止失败', 'error');
            }
            return { success: false };
        });
    }

    function _escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _loadSavedCliAgentId() {
        if (window.state && window.state.getState) {
            var cached = window.state.getState().uiConfig;
            if (cached && cached.cli_agent_id) {
                return Promise.resolve(String(cached.cli_agent_id));
            }
        }
        if (!window.api || !window.api.getUiConfig) {
            return Promise.resolve('');
        }
        return window.api.getUiConfig().then(function(cfg) {
            return (cfg && cfg.cli_agent_id) ? String(cfg.cli_agent_id) : '';
        }).catch(function(err) {
            console.warn('[CliAgent] load cli_agent_id failed:', err);
            return '';
        });
    }

    function _persistCliAgentSelection(agentId) {
        var nextId = agentId || '';
        _savedCliAgentId = nextId;
        if (nextId) {
            _dismissEmptyHint();
        }
        if (window.SettingsModule && window.SettingsModule.persistCliAgentId) {
            return window.SettingsModule.persistCliAgentId(nextId);
        }
        if (!window.api || !window.api.saveUiConfig) return Promise.resolve(null);
        var saver = (window.state && window.state.saveUiConfig)
            ? window.state.saveUiConfig.bind(window.state)
            : window.api.saveUiConfig.bind(window.api);
        return saver({ cli_agent_id: nextId }).catch(function(err) {
            console.warn('[CliAgent] save cli_agent_id failed:', err);
            return null;
        });
    }

    function applySavedAgentId(agentId) {
        var nextId = agentId || '';
        _savedCliAgentId = nextId;
        if (nextId) {
            _applyCliAgentSelection(_resolveSavedCliAgentId() || nextId);
            _dismissEmptyHint();
            return;
        }
        _applyCliAgentSelection(null);
    }

    function _resolveSavedCliAgentId() {
        if (!_savedCliAgentId) return null;
        var match = _availableAgents.find(function(a) {
            return a.id === _savedCliAgentId && a.installed;
        });
        return match ? match.id : null;
    }

    function _applyCliAgentSelection(agentId) {
        _selectedAgent = agentId || null;
        _sessionActive = false;
        var selector = document.getElementById('cli-agent-selector');
        if (selector) {
            selector.value = _selectedAgent || '';
        }
        _updateModeBadge();
        _updateSessionBadge();
        _updateInputPlaceholder();
        if (_selectedAgent || _savedCliAgentId) {
            _dismissEmptyHint();
        }
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
            _applyCliAgentSelection(this.value || null);
            _persistCliAgentSelection(_selectedAgent || '');
        });

        header.appendChild(selector);

        var existingSessionBadge = document.getElementById('cli-session-badge');
        if (existingSessionBadge) existingSessionBadge.remove();
        var sessionBadge = document.createElement('span');
        sessionBadge.id = 'cli-session-badge';
        sessionBadge.className = 'cli-session-badge';
        sessionBadge.hidden = true;
        header.appendChild(sessionBadge);

        var existingNewBtn = document.getElementById('cli-agent-new-session');
        if (existingNewBtn) existingNewBtn.remove();
        var newSessionBtn = document.createElement('button');
        newSessionBtn.id = 'cli-agent-new-session';
        newSessionBtn.type = 'button';
        newSessionBtn.className = 'cli-agent-generate-btn cli-agent-new-session-btn';
        newSessionBtn.title = window.t ? window.t('cliAgent.newSession') : '新对话';
        newSessionBtn.textContent = window.t ? window.t('cliAgent.newSession') : '新对话';
        newSessionBtn.addEventListener('click', function(e) {
            e.preventDefault();
            startNewCliSession();
        });
        header.appendChild(newSessionBtn);

        var restored = _resolveSavedCliAgentId();
        if (restored) {
            _applyCliAgentSelection(restored);
        }

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
        if (role === 'error' || role === 'system') {
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

        if (role === 'user' || role === 'error' || role === 'system') {
            var body = document.createElement('span');
            body.className = 'ai-msg-content';
            body.textContent = content;
            msg.appendChild(speaker);
            msg.appendChild(body);
        } else {
            var body = document.createElement('div');
            body.className = 'cli-agent-output cli-agent-output-inline';
            _setCliMarkdown(body, content);
            msg.appendChild(speaker);
            msg.appendChild(body);
        }
        messagesEl.appendChild(msg);
        _scrollCliMessages();
    }

    /**
     * 发送消息（CLI Tab 专用）
     */
    function sendCliMessage(prompt, options) {
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

        var opts = options || {};

        _dismissEmptyHint();
        _setRunningState(true);
        _resetStreamPre();
        _appendCliMessage('user', prompt);

        return window.api.runCliAgent(_selectedAgent, prompt, '', {
            newSession: !!opts.newSession
        }).then(function(result) {
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
            _showRunningWorkflow();
            if (payload.continue_session) {
                _sessionActive = true;
                _updateSessionBadge();
            }
        } else if (type === 'cli_agent_tool') {
            _upsertToolCard(payload);
        } else if (type === 'cli_agent_output') {
            _appendAssistantOutput(payload.content || '');
        } else if (type === 'cli_agent_timeout_warning') {
            _showTimeoutNotice(payload);
        } else if (type === 'cli_agent_done') {
            _flushOutputBuffer();
            _finalizeWorkflow();
            _hideTimeoutNotice();
            _sessionActive = true;
            _updateSessionBadge();
            _setRunningState(false);
            _resetStreamPre();
        } else if (type === 'cli_agent_error') {
            _flushOutputBuffer();
            _finalizeWorkflow();
            _hideTimeoutNotice();
            _setRunningState(false);
            _resetStreamPre();
            if (payload.stopped_by_user) {
                _appendCliMessage('system', window.t ? window.t('cliAgent.stopped') : '任务已停止');
            } else {
                _sessionActive = false;
                _updateSessionBadge();
                _appendCliMessage('error', payload.message || (window.t ? window.t('cliAgent.failed') : 'CLI agent 执行失败'));
            }
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
            if (_isRunning) {
                stopCliAgent();
                return;
            }
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
        _loadSavedCliAgentId().then(function(savedId) {
            _savedCliAgentId = savedId || '';
            if (_savedCliAgentId) {
                _dismissEmptyHint();
            }
        });
        setTimeout(function() {
            Promise.all([loadAgents(), _loadSavedCliAgentId()]).then(function(results) {
                _savedCliAgentId = results[1] || '';
                if (_savedCliAgentId) {
                    _dismissEmptyHint();
                }
                renderAgentSelector();
            });
        }, 1000);
    }

    window.CliAgentModule = {
        init: init,
        loadAgents: loadAgents,
        renderAgentSelector: renderAgentSelector,
        sendMessage: sendCliMessage,
        stopMessage: stopCliAgent,
        startNewSession: startNewCliSession,
        handleEvent: handleEvent,
        applySavedAgentId: applySavedAgentId,
        getSelectedAgent: function() { return _selectedAgent; },
        isRunning: function() { return _isRunning; },
        isCliAgentMode: function() { return _selectedAgent !== null; }
    };

    document.addEventListener('DOMContentLoaded', function() {
        init();
    });
})();
