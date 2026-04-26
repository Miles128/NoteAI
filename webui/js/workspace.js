function updateStatus(text) {
    const statusBar = document.getElementById('status-bar');
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
                    <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
                        <path d="M3 7C3 5.89543 3.89543 5 5 5H8.17157C8.70201 5 9.21071 5.21071 9.58579 5.58579L10.4142 6.41421C10.7893 6.78929 11.298 7 11.8284 7H19C20.1046 7 21 7.89543 21 9V18C21 19.1046 20.1046 20 19 20H5C3.89543 20 3 19.1046 3 18V7Z"></path>
                    </svg>
                    <span class="workspace-path">${escapeHtml(workspacePath)}</span>
                </div>
            `;
        } else {
            container.innerHTML = `
                <button class="workspace-btn" onclick="window.WorkspaceModule.openWorkspace()" title="打开工作区">
                    <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
                        <path d="M3 7C3 5.89543 3.89543 5 5 5H8.17157C8.70201 5 9.21071 5.21071 9.58579 5.58579L10.4142 6.41421C10.7893 6.78929 11.298 7 11.8284 7H19C20.1046 7 21 7.89543 21 9V18C21 19.1046 20.1046 20 19 20H5C3.89543 20 3 19.1046 3 18V7Z"></path>
                    </svg>
                    <span>打开工作区</span>
                </button>
            `;
        }
    }
}

function showWorkspaceOptions() {
    if (!window.api) return;

    window.api.get_workspace_status().then(function(status) {
        if (status.is_set) {
            if (confirm('是否要更改工作区？\n\n当前工作区: ' + status.workspace_path)) {
                openWorkspace();
            }
        } else {
            openWorkspace();
        }
    });
}

async function checkWorkspaceStatus() {
    try {
        if (window.api) {
            const status = await window.api.get_workspace_status();
            updateWorkspaceDisplay(status.is_set ? status.workspace_path : null);
        } else {
            updateWorkspaceDisplay(null);
        }
    } catch (e) {
        console.error('检查工作区状态失败:', e);
        updateWorkspaceDisplay(null);
    }
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
