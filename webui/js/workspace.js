function updateStatus(text) {
    var statusBar = document.getElementById('status-bar') || document.getElementById('editor-status-bar');
    if (statusBar) {
        statusBar.textContent = text;
    }
}

function updateProgress(elementId, progress, text) {
    const fillEl = document.getElementById(elementId + '-fill');
    const statusEl = document.getElementById(elementId.replace('progress', 'status'));
    
    if (fillEl) {
        fillEl.style.width = (progress * 100) + '%';
    }
    if (statusEl) {
        statusEl.textContent = text;
    }
    
    const modalFillEl = document.getElementById('modal-' + elementId + '-fill');
    const modalStatusEl = document.getElementById('modal-' + elementId.replace('progress', 'status'));
    const modalProgressContainer = document.getElementById('modal-progress-container');
    
    if (modalProgressContainer) {
        if (progress > 0 || text) {
            modalProgressContainer.style.display = 'block';
        }
    }
    
    if (modalFillEl) {
        modalFillEl.style.width = (progress * 100) + '%';
    }
    if (modalStatusEl) {
        modalStatusEl.textContent = text;
    }
}

async function openWorkspace() {
    const result = await window.api.open_workspace();
    if (result && result.success) {
        updateWorkspaceDisplay(result.workspace_path);
        updateStatus(result.message);
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
    }
}

function updateWorkspaceDisplay(workspacePath) {
    const container = document.getElementById('workspace-container');
    const titlebarDisplay = document.getElementById('workspace-name-display');

    if (titlebarDisplay) {
        if (workspacePath) {
            const workspaceName = workspacePath.split(/[/\\]/).pop();
            titlebarDisplay.textContent = workspaceName;
        } else {
            titlebarDisplay.textContent = '';
        }
    }

    if (container) {
        if (workspacePath) {
            container.innerHTML = `
                <div class="workspace-folder-display">
                    ${window.Icons.get('folderFilled')}
                    <span class="workspace-path">${escapeHtml(workspacePath)}</span>
                </div>
            `;
        } else {
            container.innerHTML = `
                <button class="workspace-btn" onclick="window.WorkspaceModule.openWorkspace()" title="打开工作区">
                    ${window.Icons.get('folderFilled')}
                    <span>打开工作区</span>
                </button>
            `;
        }
    }
}

function showWorkspaceOptions() {
    if (!window.api) return;

    window.api.get_workspace_status().then(status => {
        if (status.is_set) {
            if (confirm('是否要更改工作区？\n\n当前工作区: ' + status.workspace_path)) {
                openWorkspace();
            }
        } else {
            openWorkspace();
        }
    }).catch(e => {
        console.error('[Workspace] get_workspace_status error:', e);
        openWorkspace();
    });
}

async function checkWorkspaceStatus() {
    try {
        if (window.api) {
            const status = await window.api.get_workspace_status();
            updateWorkspaceDisplay(status.is_set ? status.workspace_path : null);
            if (status.is_set && window.api.rag_rebuild_index) {
                window.api.rag_rebuild_index().catch(function() {});
            }
            if (status.is_set) {
                checkProjectRules();
            }
        } else {
            updateWorkspaceDisplay(null);
        }
    } catch (e) {
        console.error('检查工作区状态失败:', e);
        updateWorkspaceDisplay(null);
    }
}

async function checkProjectRules() {
    try {
        var result = await window.api.get_project_rules();
        if (result && result.success && !result.rules) {
            showProjectRulesModal();
        }
    } catch (e) {
        console.error('[Workspace] check project rules error:', e);
    }
}

function showProjectRulesModal() {
    var modal = document.getElementById('project-rules-modal');
    if (modal) modal.style.display = '';
}

function closeProjectRulesModal() {
    var modal = document.getElementById('project-rules-modal');
    if (modal) modal.style.display = 'none';
}

async function saveProjectRulesModal() {
    var input = document.getElementById('project-rules-input');
    var rules = input ? input.value : '';
    try {
        await window.api.save_project_rules(rules);
    } catch (e) {
        console.error('[Workspace] save project rules error:', e);
    }
    closeProjectRulesModal();
}

async function addFiles() {
    const files = await window.api.add_files();
    if (files && files.length > 0) {
        const select = document.getElementById('file-list');
        if (select) {
            files.forEach(f => {
                const option = document.createElement('option');
                option.value = f;
                option.textContent = f;
                select.appendChild(option);
            });
        }
    }
}

async function addFolder() {
    const folder = await window.api.browse_folder();
    if (folder) {
        const select = document.getElementById('file-list');
        if (select) {
            const option = document.createElement('option');
            option.value = folder;
            option.textContent = folder;
            select.appendChild(option);
        }
    }
}

function clearFiles() {
    const select = document.getElementById('file-list');
    if (select) {
        select.innerHTML = '';
    }
}

async function showAbout() {
    if (window.ThemeModule && window.ThemeModule.showAboutPanel) {
        window.ThemeModule.showAboutPanel();
    }
}

function showSettings() {
    const aboutPanel = document.getElementById('about-panel');
    const logPanel = document.getElementById('log-panel');
    const settingsPanel = document.getElementById('settings-panel');

    if (aboutPanel) aboutPanel.classList.remove('active');
    if (logPanel) logPanel.classList.remove('active');
    if (settingsPanel) settingsPanel.classList.add('active');

    if (window.SettingsModule && window.SettingsModule.loadApiConfigToForm) {
        window.SettingsModule.loadApiConfigToForm();
    }
    if (window.SettingsModule && window.SettingsModule.loadUserProfile) {
        window.SettingsModule.loadUserProfile();
    }
}

function showLog() {
    const aboutPanel = document.getElementById('about-panel');
    const settingsPanel = document.getElementById('settings-panel');
    const logPanel = document.getElementById('log-panel');

    if (aboutPanel) aboutPanel.classList.remove('active');
    if (settingsPanel) settingsPanel.classList.remove('active');
    if (logPanel) logPanel.classList.add('active');

    if (window.SettingsModule && window.SettingsModule.refreshLog) {
        window.SettingsModule.refreshLog();
    }
}

window.WorkspaceModule = {
    updateStatus,
    updateProgress,
    openWorkspace,
    updateWorkspaceDisplay,
    showWorkspaceOptions,
    checkWorkspaceStatus,
    addFiles,
    addFolder,
    clearFiles,
    showAbout,
    showSettings,
    showLog
};
