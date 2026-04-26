let treeExpandedState = {};
let selectedFilePath = null;
let selectedFileName = null;

function loadTreeState() {
    try {
        const saved = localStorage.getItem('tree-expanded-state');
        if (saved) {
            treeExpandedState = JSON.parse(saved);
        }
    } catch (e) {
        console.warn('[Tree] Failed to load tree state:', e);
        treeExpandedState = {};
    }
}

function saveTreeState() {
    try {
        localStorage.setItem('tree-expanded-state', JSON.stringify(treeExpandedState));
    } catch (e) {
        console.warn('[Tree] Failed to save tree state:', e);
    }
}

function toggleTreeFolder(element) {
    const children = element.nextElementSibling;
    if (children && children.classList.contains('tree-children')) {
        children.classList.toggle('hidden');

        const toggle = element.querySelector('.tree-toggle');
        if (toggle) {
            toggle.classList.toggle('collapsed');
        }

        const path = element.getAttribute('data-path');
        if (path) {
            const isCollapsed = children.classList.contains('hidden');
            treeExpandedState[path] = !isCollapsed;
            saveTreeState();
        }
    }
}

function renderFileTree(treeData, container) {
    if (!treeData || treeData.length === 0) {
        container.innerHTML = '<div class="tree-empty">暂无工作区</div>';
        return;
    }

    loadTreeState();

    function buildTreeHTML(nodes, indentLevel = 0) {
        return nodes.map(node => {
            const hasChildren = node.children && node.children.length > 0;
            const isFolder = node.type === 'folder';
            const indent = indentLevel * 16;

            const expandedState = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            const childrenHiddenClass = expandedState ? '' : 'hidden';

            let html = `
                <div class="tree-item ${isFolder ? 'folder' : 'file'}" data-path="${node.path}" style="padding-left: ${indent}px;" onclick="${isFolder ? `window.TreeModule.toggleTreeFolder(this)` : `window.TreeModule.selectFile('${node.path}', '${node.name}')`}">
            `;

            if (isFolder) {
                html += `<span class="tree-toggle ${expandedState ? '' : 'collapsed'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg></span>`;
                html += `<span class="tree-icon folder-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m20 20-2-2V8l-4-4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2l2 2Z"></path></svg></span>`;
            } else {
                html += `<span class="tree-toggle" style="visibility:hidden"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg></span>`;
                html += `<span class="tree-icon file-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span>`;
            }

            html += `<span class="tree-name">${node.name}</span>`;

            if (!isFolder) {
                html += `<span class="tree-meta"><span class="tree-size">${formatFileSize(node.size)}</span><span class="tree-modified">${formatModifiedTime(node.modified)}</span></span>`;
            }

            html += `</div>`;

            if (hasChildren) {
                html += `<div class="tree-children ${childrenHiddenClass}">${buildTreeHTML(node.children, indentLevel + 1)}</div>`;
            }

            return html;
        }).join('');
    }

    container.innerHTML = buildTreeHTML(treeData);
}

async function loadFileTree() {
    const container = document.getElementById('file-tree');
    if (!container) return;

    if (!window.pywebview) {
        container.innerHTML = '<div class="tree-empty">工作区未设置</div>';
        return;
    }

    try {
        const treeData = await Promise.race([
            window.pywebview.api.get_workspace_tree(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('加载超时')), 5000))
        ]);
        if (Array.isArray(treeData) && treeData.length === 0) {
            container.innerHTML = '<div class="tree-empty">工作区为空或未设置</div>';
        } else {
            renderFileTree(treeData, container);
        }
    } catch (e) {
        console.error('加载目录树失败:', e);
        container.innerHTML = '<div class="tree-empty">加载失败: ' + e.message + '</div>';
    }
}

function selectFile(path, fileName) {
    selectedFilePath = path;
    selectedFileName = fileName;

    if (window.pywebview) {
        window.pywebview.api.on_file_selected(path);
        if (window.PreviewModule && window.PreviewModule.loadFilePreview) {
            window.PreviewModule.loadFilePreview(path, fileName);
        }
    }
}

function updateWebAIStatus() {
    const toggle = document.getElementById('web-ai-toggle');
    const card = document.getElementById('web-ai-card');
    const label = document.getElementById('web-ai-label');
    const statusBox = document.getElementById('web-ai-status');
    const isEnabled = toggle.checked;

    if (isEnabled) {
        card.classList.add('active');
        label.textContent = 'AI辅助已开启';
        if (statusBox) statusBox.innerHTML = '<span class="status-dot"></span><span class="status-text">AI模式 - 智能提取、优化排版</span>';
    } else {
        card.classList.remove('active');
        label.textContent = '使用AI辅助下载';
        if (statusBox) statusBox.innerHTML = '<span class="status-dot"></span><span class="status-text">基础模式 - 使用标准算法提取内容</span>';
    }
}

function updateConvAIStatus() {
    const toggle = document.getElementById('conv-ai-toggle');
    const card = document.getElementById('conv-ai-card');
    const label = document.getElementById('conv-ai-label');
    const statusBox = document.getElementById('conv-ai-status');
    const isEnabled = toggle.checked;

    if (isEnabled) {
        card.classList.add('active');
        label.textContent = 'AI辅助已开启';
        if (statusBox) statusBox.innerHTML = '<span class="status-dot"></span><span class="status-text">AI模式 - 智能识别文档结构、优化排版</span>';
    } else {
        card.classList.remove('active');
        label.textContent = '使用AI辅助转换';
        if (statusBox) statusBox.innerHTML = '<span class="status-dot"></span><span class="status-text">基础模式 - 使用标准算法转换</span>';
    }
}

window.TreeModule = {
    treeExpandedState,
    selectedFilePath,
    selectedFileName,
    loadTreeState,
    saveTreeState,
    toggleTreeFolder,
    renderFileTree,
    loadFileTree,
    selectFile,
    updateWebAIStatus,
    updateConvAIStatus
};
