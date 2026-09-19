// CLI Agent 设置（从 settings-components.ts 下沉）

// ---------------------------------------------------------------------------
// CLI Agent 设置
// ---------------------------------------------------------------------------

export function applyCliSettingsToForm(uiConfig: any) {
    var selectEl = document.getElementById('settings-cli-agent-select') as HTMLSelectElement | null;
    if (selectEl && uiConfig && uiConfig.cli_agent_id) {
        if (selectEl.querySelector('option[value="' + uiConfig.cli_agent_id + '"]')) {
            selectEl.value = uiConfig.cli_agent_id;
        }
    }
}

function _showCliAgentSaveStatus(message: any, isError: any) {
    var statusEl = document.getElementById('settings-cli-save-status');
    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.style.color = isError ? '#e53e3e' : 'var(--text-muted)';
        statusEl.textContent = message;
    }
    if (window.ToastModule && window.ToastModule.show && isError) {
        window.ToastModule.show(message, 'error');
    }
}

export function _syncCliAgentSelectors(agentId: any) {
    var nextId = agentId || '';
    var settingsSel = document.getElementById('settings-cli-agent-select') as HTMLSelectElement | null;
    var tabSel = document.getElementById('cli-agent-selector') as HTMLSelectElement | null;
    if (settingsSel) {
        if (nextId && settingsSel.querySelector('option[value="' + nextId + '"]')) {
            settingsSel.value = nextId;
        } else if (!nextId) {
            settingsSel.value = '';
        }
    }
    if (tabSel) {
        if (nextId && tabSel.querySelector('option[value="' + nextId + '"]')) {
            tabSel.value = nextId;
        } else if (!nextId) {
            tabSel.value = '';
        }
    }
    if (window.CliAgentModule && window.CliAgentModule.applySavedAgentId) {
        window.CliAgentModule.applySavedAgentId(nextId);
    }
}

export async function persistCliAgentId(agentId: any) {
    var nextId = String(agentId || '').trim();
    try {
        var saver = (window.state && window.state.saveUiConfig)
            ? window.state.saveUiConfig.bind(window.state)
            : window.api.saveUiConfig.bind(window.api);
        var result = await saver({ cli_agent_id: nextId });
        if (result && result.success) {
            _syncCliAgentSelectors(nextId);
            _showCliAgentSaveStatus(window.t('settings.autoSaved'), false);
            window.updateStatus(window.t('settings.autoSaved'));
            return result;
        }
        var failMsg = window.t('settings.autoSaveFailed', {
            message: (result && result.message) || window.t('common.unknownError'),
        });
        _showCliAgentSaveStatus(failMsg, true);
        window.updateStatus(failMsg);
        return result;
    } catch (e) {
        console.error('[Settings] persist cli_agent_id error:', e);
        var errMsg = window.t('settings.autoSaveFailed', { message: (e as Error).message || String(e) });
        _showCliAgentSaveStatus(errMsg, true);
        window.updateStatus(errMsg);
        return null;
    }
}

var _cliAgentsRefreshGen = 0;

export async function refreshCliAgentsSettings() {
    const listEl = document.getElementById('settings-cli-agents-list');
    const selectEl = document.getElementById('settings-cli-agent-select') as HTMLSelectElement | null;
    if (!listEl || !window.api || !window.api.listCliAgents) return;

    var refreshGen = ++_cliAgentsRefreshGen;
    listEl.innerHTML = '<p class="settings-hint">' + window.escapeHtml(window.t('settings.cliAgentsLoading')) + '</p>';

    try {
        var result = await window.api.listCliAgents();
        if (refreshGen !== _cliAgentsRefreshGen) return;

        var agents = (result && result.success && Array.isArray(result.agents)) ? result.agents : [];
        var uiConfig: any = {};
        if (window.state && window.state.get) {
            uiConfig = window.state.get().uiConfig || {};
        }
        if (!uiConfig.cli_agent_id && window.api.getUiConfig) {
            uiConfig = await window.api.getUiConfig();
        }
        if (refreshGen !== _cliAgentsRefreshGen) return;

        var pendingId = (selectEl && selectEl.dataset.pendingValue) ? String(selectEl.dataset.pendingValue) : '';
        var savedId = pendingId || ((uiConfig && uiConfig.cli_agent_id) ? String(uiConfig.cli_agent_id) : '');

        if (selectEl) {
            selectEl.innerHTML = '';
            var placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = window.t('settings.cliDefaultPlaceholder');
            selectEl.appendChild(placeholder);
            agents.forEach(function(agent: any) {
                var opt = document.createElement('option');
                opt.value = agent.id;
                opt.textContent = agent.name + (agent.installed ? '' : ' (' + window.t('settings.cliAgentNotInstalled') + ')');
                opt.disabled = !agent.installed;
                if (agent.resolved_path) {
                    opt.title = agent.resolved_path;
                }
                selectEl.appendChild(opt);
            });
            if (savedId && agents.some(function(a: any) { return a.id === savedId && a.installed; })) {
                selectEl.value = savedId;
            }
        }

        if (!agents.length) {
            listEl.innerHTML = '<p class="settings-hint">' + window.escapeHtml(window.t('settings.cliAgentsEmpty')) + '</p>';
            return;
        }

        listEl.innerHTML = '';
        agents.forEach(function(agent: any) {
            var row = document.createElement('div');
            row.className = 'settings-component-row settings-cli-agent-row';

            var info = document.createElement('div');
            info.className = 'settings-component-info';

            var name = document.createElement('div');
            name.className = 'settings-component-name';
            name.textContent = agent.name;

            var desc = document.createElement('p');
            desc.className = 'settings-hint';
            desc.textContent = agent.description || agent.command || '';

            var badge = document.createElement('span');
            badge.className = 'settings-component-badge' + (agent.installed ? ' is-ok' : '');
            badge.textContent = agent.installed
                ? window.t('settings.cliAgentInstalled')
                : window.t('settings.cliAgentNotInstalled');

            info.appendChild(name);
            info.appendChild(desc);
            info.appendChild(badge);
            if (agent.resolved_path) {
                var pathHint = document.createElement('p');
                pathHint.className = 'settings-hint';
                pathHint.style.fontSize = '11px';
                pathHint.textContent = agent.resolved_path;
                info.appendChild(pathHint);
            }
            row.appendChild(info);
            listEl.appendChild(row);
        });
    } catch (e) {
        listEl.innerHTML = '<p class="settings-hint" style="color:var(--danger,#c0392b)">' +
            window.escapeHtml(window.t('settings.cliAgentsLoadFailed', { message: (e as Error).message || String(e) })) + '</p>';
    }
}

export function initCliSettings() {
    const selectEl = document.getElementById('settings-cli-agent-select') as HTMLSelectElement | null;
    if (selectEl && !selectEl.dataset.bound) {
        selectEl.dataset.bound = '1';
        selectEl.addEventListener('change', function() {
            var nextId = selectEl.value || '';
            selectEl.dataset.pendingValue = nextId;
            persistCliAgentId(nextId).finally(function() {
                if (selectEl.dataset.pendingValue === nextId) {
                    delete selectEl.dataset.pendingValue;
                }
            });
        });
    }

    var refreshBtn = document.getElementById('settings-cli-refresh-btn');
    if (refreshBtn && !refreshBtn.dataset.bound) {
        refreshBtn.dataset.bound = '1';
        refreshBtn.addEventListener('click', refreshCliAgentsSettings);
    }

    const mdBtn = document.getElementById('settings-cli-generate-md-btn') as HTMLButtonElement | null;
    if (mdBtn && !mdBtn.dataset.bound) {
        mdBtn.dataset.bound = '1';
        mdBtn.addEventListener('click', async function() {
            var statusEl = document.getElementById('settings-cli-md-status');
            if (!window.api || !window.api.generateVaultAgentsMd) return;
            mdBtn.disabled = true;
            if (statusEl) {
                statusEl.style.display = 'block';
                statusEl.textContent = window.t('settings.cliGenerateMdRunning');
            }
            try {
                var result = await window.api.generateVaultAgentsMd();
                if (statusEl) {
                    statusEl.textContent = (result && result.success)
                        ? window.t('settings.cliGenerateMdDone', { path: result.path || 'AGENTS.md' })
                        : window.t('settings.cliGenerateMdFailed', {
                            message: (result && result.message) || window.t('common.unknownError')
                        });
                }
            } catch (e) {
                if (statusEl) {
                    statusEl.textContent = window.t('settings.cliGenerateMdFailed', { message: (e as Error).message || String(e) });
                }
            } finally {
                mdBtn.disabled = false;
            }
        });
    }
}
