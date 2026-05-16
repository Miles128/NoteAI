(function() { 'use strict';

var treeExpandedState = window.AppState.treeExpandedState;
var selectedFilePath = null;
var selectedFileName = null;
var _activeTreeItem = null;

function setSelectedFile(path, name) {
    selectedFilePath = path;
    selectedFileName = name;
    window.AppState.selectedFilePath = path;
    window.AppState.selectedFileName = name;
}

function getSelectedFilePath() {
    return window.AppState.selectedFilePath;
}

function getSelectedFileName() {
    return window.AppState.selectedFileName;
}

function loadTreeState() {
    try {
        var saved = localStorage.getItem('tree-expanded-state');
        if (saved) treeExpandedState = JSON.parse(saved);
    } catch (e) {
        console.warn('[Tree] loadTreeState failed:', e);
        treeExpandedState = {};
    }
}

function saveTreeState() {
    try {
        localStorage.setItem('tree-expanded-state', JSON.stringify(treeExpandedState));
    } catch (e) {
        console.warn('[Tree] saveTreeState failed:', e);
    }
}

function toggleTreeFolder(element) {
    var children = element.nextElementSibling;
    if (!children || !children.classList.contains('tree-children')) return;

    children.classList.toggle('hidden');

    var toggle = element.querySelector('.tree-toggle');
    if (toggle) toggle.classList.toggle('collapsed');

    var path = element.getAttribute('data-path');
    if (path) {
        treeExpandedState[path] = !children.classList.contains('hidden');
        saveTreeState();
    }
}

function setActiveTreeItem(itemEl) {
    if (_activeTreeItem) _activeTreeItem.classList.remove('is-active');
    _activeTreeItem = itemEl;
    if (itemEl) itemEl.classList.add('is-active');
}

function formatModifiedTime(modified) {
    if (!modified) return '';
    var d = new Date(modified * 1000);
    if (isNaN(d.getTime())) return '';
    var now = new Date();
    var diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
    if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
    if (diff < 604800000) return Math.floor(diff / 86400000) + '天前';
    var m = d.getMonth() + 1;
    var day = d.getDate();
    if (d.getFullYear() === now.getFullYear()) {
        return m + '月' + day + '日';
    }
    return d.getFullYear() + '/' + m + '/' + day;
}

function renderFileTree(treeData, container) {
    if (!treeData || treeData.length === 0) {
        container.innerHTML = '<div class="tree-empty">暂无工作区</div>';
        return;
    }

    loadTreeState();

    function buildTreeHTML(nodes, indentLevel) {
        return nodes.map(function(node) {
            var hasChildren = node.children && node.children.length > 0;
            var isFolder = node.type === 'folder';

            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            var childrenHidden = expanded ? '' : 'hidden';

            var ep = node.path.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            var en = node.name.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

            var html = '<div class="tree-item ' + (isFolder ? 'folder' : 'file') + '" draggable="true" data-path="' + ep + '" data-name="' + en + '">';

            for (var i = 0; i < indentLevel; i++) {
                html += '<span class="tree-indent-unit"></span>';
            }

            if (isFolder) {
                html += '<span class="tree-toggle ' + (expanded ? '' : 'collapsed') + '">' + window.Icons.get('chevron') + '</span>';
            } else {
                html += '<span class="tree-toggle" style="visibility:hidden">' + window.Icons.get('chevron') + '</span>';
            }

            html += '<span class="tree-name">' + en + '</span>';

            if (!isFolder && node.modified) {
                html += '<span class="tree-modified">' + formatModifiedTime(node.modified) + '</span>';
            }

            html += '</div>';

            if (hasChildren) {
                html += '<div class="tree-children ' + childrenHidden + '">' + buildTreeHTML(node.children, indentLevel + 1) + '</div>';
            }

            return html;
        }).join('');
    }

    container.innerHTML = buildTreeHTML(treeData, 0);

    container.querySelectorAll('.tree-item').forEach(function(item) {
        item.addEventListener('click', function(e) {
            var path = this.getAttribute('data-path');
            var name = this.getAttribute('data-name');
            if (this.classList.contains('folder')) {
                window.TreeModule.toggleTreeFolder(this);
            } else {
                setActiveTreeItem(this);
                window.TreeModule.selectFile(path, name);
            }
        });

        item.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            e.stopPropagation();
            showTreeContextMenu(e, this);
        });
    });

    setupFileTreeDragDrop(container);

    if (selectedFilePath) {
        var prev = container.querySelector('.tree-item[data-path="' + selectedFilePath.replace(/"/g, '&quot;') + '"]');
        if (prev) setActiveTreeItem(prev);
    }
}

function showTreeContextMenu(e, itemEl) {
    hideTreeContextMenu();

    var isFolder = itemEl.classList.contains('folder');
    var path = itemEl.getAttribute('data-path');
    var name = itemEl.getAttribute('data-name');

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({
        label: '在访达中显示',
        icon: window.Icons.get('folder'),
        action: function() { revealInFinder(path); }
    });

    if (!isFolder) {
        items.push({
            label: '在新窗口打开',
            icon: window.Icons.get('folderOpen'),
            action: function() {
                if (window.api && window.api.openFileInNewWindow) {
                    window.api.openFileInNewWindow(path, name);
                }
            }
        });
    }

    if (isFolder) {
        items.push({
            label: '删除主题',
            icon: window.Icons.get('trash'),
            action: function() { showTopicDeleteConfirm(itemEl, path, name); }
        });
    }

    items.push({
        label: isFolder ? '删除文件夹' : '删除',
        icon: window.Icons.get('trash'),
        action: function() { showDeleteConfirm(itemEl, path, name); }
    });

    items.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'ctx-menu-item';
        el.innerHTML = item.icon + '<span>' + item.label + '</span>';
        el.addEventListener('click', function() {
            hideTreeContextMenu();
            item.action();
        });
        menu.appendChild(el);
    });

    document.body.appendChild(menu);

    var x = e.clientX;
    var y = e.clientY;
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 4;
    if (y + mh > window.innerHeight) y = window.innerHeight - mh - 4;
    if (x < 0) x = 4;
    if (y < 0) y = 4;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function showTopicDeleteConfirm(itemEl, path, name) {
    var existingConfirm = itemEl.querySelector('.delete-confirm-bar');
    if (existingConfirm) return;

    var bar = document.createElement('div');
    bar.className = 'delete-confirm-bar';
    bar.innerHTML = '<span class="delete-confirm-text">删除主题「' + escapeHtml(name) + '」？文件将移至 Notes 根目录</span>' +
        '<button class="delete-confirm-yes" title="确认删除主题">' + window.Icons.get('check', 16) + '</button>' +
        '<button class="delete-confirm-no" title="取消">' + window.Icons.get('close', 16) + '</button>';

    itemEl.style.position = 'relative';
    itemEl.appendChild(bar);

    bar.querySelector('.delete-confirm-yes').addEventListener('click', function(e) {
        e.stopPropagation();
        doDeleteTopic(name, bar);
    });

    bar.querySelector('.delete-confirm-no').addEventListener('click', function(e) {
        e.stopPropagation();
        bar.remove();
    });

    var outsideClick = function(e) {
        if (!bar.contains(e.target) && e.target !== itemEl) {
            bar.remove();
            document.removeEventListener('click', outsideClick);
        }
    };
    setTimeout(function() { document.addEventListener('click', outsideClick); }, 10);
}

async function doDeleteTopic(topicName, confirmBar) {
    if (confirmBar) confirmBar.remove();
    try {
        var result = await window.api.deleteTopic(topicName);
        if (result && result.success) {
            window.TreeModule.loadFileTree();
        } else {
            alert('删除主题失败：' + (result ? result.message || '未知错误' : '未知错误'));
        }
    } catch (e) {
        alert('删除主题出错：' + (e.message || e));
    }
}

function onAddTopicFromFileTree() {
    var topicName = prompt('请输入新主题名称：\n\n将创建对应的主题文件夹，并自动匹配相关文件。');
    if (!topicName || !topicName.trim()) return;
    topicName = topicName.trim();

    if (window.api && window.api.createTopic) {
        window.api.createTopic(topicName).then(function(result) {
            if (result && result.success) {
                window.TreeModule.loadFileTree();
                if (window.api && window.api.batchAutoAssignTopics) {
                    window.api.batchAutoAssignTopics().then(function(r) {
                        if (r && r.success && r.need_confirm > 0) {
                            if (typeof window.loadTopicPendingPanel === 'function') {
                                var topicNames = [];
                                window.loadTopicPendingPanel(r.pending, topicNames);
                                var panel = document.getElementById('topic-pending-panel');
                                if (panel) panel.style.display = '';
                            }
                        }
                    }).catch(function() {});
                }
            } else {
                alert('创建主题失败：' + (result ? result.message : '未知错误'));
            }
        }).catch(function(e) {
            alert('创建主题出错：' + (e.message || e));
        });
    }
}

function hideTreeContextMenu() {
    var existing = document.getElementById('tree-ctx-menu');
    if (existing) existing.remove();
}

function showDeleteConfirm(itemEl, path, name) {
    var existingConfirm = itemEl.querySelector('.delete-confirm-bar');
    if (existingConfirm) return;

    var bar = document.createElement('div');
    bar.className = 'delete-confirm-bar';
    bar.innerHTML = '<span class="delete-confirm-text">删除 ' + escapeHtml(name) + '？</span>' +
        '<button class="delete-confirm-yes" title="确认删除">' + window.Icons.get('check', 16) + '</button>' +
        '<button class="delete-confirm-no" title="取消">' + window.Icons.get('close', 16) + '</button>';

    itemEl.style.position = 'relative';
    itemEl.appendChild(bar);

    bar.querySelector('.delete-confirm-yes').addEventListener('click', function(e) {
        e.stopPropagation();
        doDeleteFile(path, name, bar);
    });

    bar.querySelector('.delete-confirm-no').addEventListener('click', function(e) {
        e.stopPropagation();
        bar.remove();
    });

    var outsideClick = function(e) {
        if (!bar.contains(e.target) && e.target !== itemEl) {
            bar.remove();
            document.removeEventListener('click', outsideClick);
        }
    };
    setTimeout(function() { document.addEventListener('click', outsideClick); }, 10);
}

async function doDeleteFile(path, name, confirmBar) {
    if (confirmBar) confirmBar.remove();
    try {
        var result = await window.api.invoke('delete_file', { path: path });
        if (result && result.success) {
            if (selectedFilePath === path) {
                setSelectedFile(null, null);
            }
            window.TreeModule.loadFileTree();
        } else {
            alert('删除失败：' + (result ? result.message || '未知错误' : '未知错误'));
        }
    } catch (e) {
        alert('删除出错：' + (e.message || e));
    }
}

function revealInFinder(path) {
    if (window.api && window.api.invoke) {
        window.api.invoke('reveal_in_finder', { path: path });
    }
}

async function deleteFile(path, name) {
    if (!(await window._customConfirm('确定要删除 "' + name + '" 吗？'))) return;
    if (window.api && window.api.invoke) {
        window.api.invoke('delete_file', { path: path }).then(function(result) {
            if (result && result.success) {
                window.TreeModule.loadFileTree();
            } else {
                alert('删除失败：' + (result ? result.message || '未知错误' : '未知错误'));
            }
        });
    }
}

var _fileTreeDragData = { filePath: null, fileName: null, isFolder: false };

var _dragDropInitialized = false;

function setupFileTreeDragDrop(container) {
    if (_dragDropInitialized) return;
    _dragDropInitialized = true;

    container.addEventListener('dragstart', function(e) {
        var itemEl = e.target.closest('.tree-item');
        if (!itemEl) return;

        var filePath = itemEl.getAttribute('data-path');
        if (!filePath) return;

        _fileTreeDragData.filePath = filePath;
        _fileTreeDragData.fileName = itemEl.getAttribute('data-name') || '文件';
        _fileTreeDragData.isFolder = itemEl.classList.contains('folder');
        itemEl.classList.add('dragging');

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', filePath);
        e.dataTransfer.setData('text/html', '<span>' + escapeHtml(_fileTreeDragData.fileName) + '</span>');
    });

    container.addEventListener('dragend', function(e) {
        var itemEl = e.target.closest('.tree-item');
        if (itemEl) itemEl.classList.remove('dragging');

        container.querySelectorAll('.tree-item').forEach(function(item) {
            item.classList.remove('drag-over', 'drag-over-top');
        });

        _fileTreeDragData.filePath = null;
        _fileTreeDragData.fileName = null;
        _fileTreeDragData.isFolder = false;
    });

    container.addEventListener('dragover', function(e) {
        var dragFilePath = _fileTreeDragData.filePath || e.dataTransfer.getData('text/plain');
        if (!dragFilePath) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        var itemEl = e.target.closest('.tree-item');

        container.querySelectorAll('.tree-item').forEach(function(item) {
            item.classList.remove('drag-over', 'drag-over-top');
        });

        if (itemEl && itemEl.classList.contains('folder')) {
            var targetPath = itemEl.getAttribute('data-path');
            if (targetPath !== dragFilePath) {
                itemEl.classList.add('drag-over');
            }
        }
    });

    container.addEventListener('dragleave', function(e) {
        var itemEl = e.target.closest('.tree-item');
        if (itemEl) itemEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e) {
        e.preventDefault();

        var srcPath = _fileTreeDragData.filePath || e.dataTransfer.getData('text/plain');
        if (!srcPath) return;

        var itemEl = e.target.closest('.tree-item');

        if (itemEl && itemEl.classList.contains('folder')) {
            var targetPath = itemEl.getAttribute('data-path');

            if (targetPath === srcPath) return;

            if (_fileTreeDragData.isFolder && targetPath.startsWith(srcPath + '/')) return;

            try {
                var result = await window.api.moveFile(srcPath, targetPath);
                if (result && result.success) {
                    await window.TreeModule.loadFileTree();
                } else {
                    alert('移动失败：' + (result ? result.message : '未知错误'));
                }
            } catch (err) {
                console.error('[FileTree] move error:', err);
                alert('移动失败：' + (err.message || '发生错误'));
            }
        }

        container.querySelectorAll('.tree-item').forEach(function(item) {
            item.classList.remove('drag-over', 'drag-over-top');
        });
    });
}

document.addEventListener('click', function() { hideTreeContextMenu(); });
document.addEventListener('contextmenu', function(e) {
    if (!e.target.closest('.tree-item') && !e.target.closest('.sidebar-tag-row') && !e.target.closest('.sidebar-tag-file')) hideTreeContextMenu();
});

var _virtualScrollRAF = null;
document.addEventListener('DOMContentLoaded', function() {
    var container = document.getElementById('file-tree');
    if (container) {
        container.addEventListener('scroll', function() {
            if (_virtualScrollRAF) return;
            _virtualScrollRAF = requestAnimationFrame(function() {
                _virtualScrollRAF = null;
                if (_flatVisibleNodes && _flatVisibleNodes.length > 50) {
                    renderVirtualTree(container);
                }
            });
        });
    }
});

var _lastFileTreeData = null;
var _flatVisibleNodes = null;
var _virtualScrollItemHeight = 28;
var _virtualScrollVisibleCount = 0;
var _virtualScrollStartIdx = 0;

function flattenVisibleNodes(treeData) {
    var result = [];
    function walk(nodes, depth) {
        if (!nodes) return;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            var isFolder = node.type === 'folder';
            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            result.push({ path: node.path, name: node.name, type: node.type, depth: depth, modified: node.modified, expanded: expanded });
            if (isFolder && expanded && node.children) {
                walk(node.children, depth + 1);
            }
        }
    }
    walk(treeData, 0);
    return result;
}

function renderVirtualTree(container) {
    if (!_flatVisibleNodes || _flatVisibleNodes.length === 0) {
        container.innerHTML = '<div class="tree-empty">暂无工作区</div>';
        return;
    }

    var totalHeight = _flatVisibleNodes.length * _virtualScrollItemHeight;
    var scrollTop = container.scrollTop || 0;
    var viewHeight = container.clientHeight || 600;

    _virtualScrollStartIdx = Math.floor(scrollTop / _virtualScrollItemHeight);
    _virtualScrollVisibleCount = Math.ceil(viewHeight / _virtualScrollItemHeight) + 5;

    var startIdx = Math.max(0, _virtualScrollStartIdx - 2);
    var endIdx = Math.min(_flatVisibleNodes.length, startIdx + _virtualScrollVisibleCount + 4);

    var html = '<div class="tree-virtual-spacer" style="height:' + (startIdx * _virtualScrollItemHeight) + 'px"></div>';

    for (var i = startIdx; i < endIdx; i++) {
        var node = _flatVisibleNodes[i];
        var isFolder = node.type === 'folder';
        var ep = node.path.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        var en = node.name.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        html += '<div class="tree-item ' + (isFolder ? 'folder' : 'file') + '" draggable="true" data-path="' + ep + '" data-name="' + en + '">';
        for (var d = 0; d < node.depth; d++) {
            html += '<span class="tree-indent-unit"></span>';
        }
        if (isFolder) {
            html += '<span class="tree-toggle ' + (node.expanded ? '' : 'collapsed') + '">' + window.Icons.get('chevron') + '</span>';
        } else {
            html += '<span class="tree-toggle" style="visibility:hidden">' + window.Icons.get('chevron') + '</span>';
        }
        html += '<span class="tree-name">' + en + '</span>';
        if (!isFolder && node.modified) {
            html += '<span class="tree-modified">' + formatModifiedTime(node.modified) + '</span>';
        }
        html += '</div>';
    }

    html += '<div class="tree-virtual-spacer" style="height:' + ((_flatVisibleNodes.length - endIdx) * _virtualScrollItemHeight) + 'px"></div>';

    container.innerHTML = html;

    if (!container._treeDelegated) {
        container.addEventListener('click', function(e) {
            var item = e.target.closest('.tree-item');
            if (!item) return;
            var path = item.getAttribute('data-path');
            var name = item.getAttribute('data-name');
            if (item.classList.contains('folder')) {
                var currentExpanded = treeExpandedState.hasOwnProperty(path) ? treeExpandedState[path] : true;
                treeExpandedState[path] = !currentExpanded;
                saveTreeState();
                _flatVisibleNodes = flattenVisibleNodes(_lastTreeData);
                renderVirtualTree(container);
            } else {
                setActiveTreeItem(item);
                window.TreeModule.selectFile(path, name);
            }
        });

        container.addEventListener('contextmenu', function(e) {
            var item = e.target.closest('.tree-item');
            if (item) {
                e.preventDefault();
                e.stopPropagation();
                showTreeContextMenu(e, item);
            }
        });
        container._treeDelegated = true;
    }

    setupFileTreeDragDrop(container);

    if (selectedFilePath) {
        var prev = container.querySelector('.tree-item[data-path="' + selectedFilePath.replace(/"/g, '&quot;') + '"]');
        if (prev) setActiveTreeItem(prev);
    }
}

var _lastTreeData = null;

function extractFileSet(treeData) {
    var files = {};
    function walk(nodes) {
        if (!nodes) return;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            files[n.path] = n.type + ':' + n.name + ':' + (n.modified || 0);
            if (n.children) walk(n.children);
        }
    }
    walk(treeData);
    return files;
}

var _lastFileSet = null;
var FILE_TREE_LOAD_TIMEOUT_MS = 15000;
var _loadFileTreeInFlight = null;

function _describeTreeLoadError(error) {
    if (!error) return '未知错误';
    if (typeof error === 'string') return error;
    if (error.message) return error.message;
    try {
        return JSON.stringify(error);
    } catch (_) {
        return String(error);
    }
}

async function loadFileTree() {
    if (_loadFileTreeInFlight) {
        return _loadFileTreeInFlight;
    }
    _loadFileTreeInFlight = _loadFileTreeOnce();
    try {
        return await _loadFileTreeInFlight;
    } finally {
        _loadFileTreeInFlight = null;
    }
}

async function _loadFileTreeOnce() {
    var container = document.getElementById('file-tree');
    if (!container) return;

    if (!window.api) {
        container.innerHTML = '<div class="tree-empty">工作区未设置</div>';
        return;
    }

    try {
        var treeData = await Promise.race([
            window.api.getWorkspaceTree(),
            new Promise(function(_, reject) { setTimeout(function() { reject(new Error('加载超时')); }, FILE_TREE_LOAD_TIMEOUT_MS); })
        ]);

        if (!Array.isArray(treeData)) {
            throw new Error('文件树返回格式错误: ' + _describeTreeLoadError(treeData));
        }

        var newFileSet = extractFileSet(treeData);
        var newSetStr = JSON.stringify(newFileSet);

        if (newSetStr === _lastFileSet) return;
        _lastFileSet = newSetStr;
        _lastTreeData = treeData;
        window.AppState.lastFileTreeData = treeData;

        if (Array.isArray(treeData) && treeData.length === 0) {
            container.innerHTML = '<div class="tree-empty">工作区为空</div>';
        } else {
            loadTreeState();
            _flatVisibleNodes = flattenVisibleNodes(treeData);
            renderVirtualTree(container);
        }
    } catch (e) {
        console.warn('[Tree] Load skipped:', _describeTreeLoadError(e), e);
        if (!_lastTreeData) {
            container.innerHTML = '<div class="tree-empty">暂时无法加载文件树</div>';
        }
    }

    try {
        if (typeof window.updateSidebarStats === 'function') window.updateSidebarStats();
    } catch (e) {
        console.warn('[Tree] updateSidebarStats failed:', _describeTreeLoadError(e), e);
    }
    try {
        if (typeof window.refreshPendingBtnState === 'function') refreshPendingBtnState();
    } catch (e) {
        console.warn('[Tree] refreshPendingBtnState failed:', _describeTreeLoadError(e), e);
    }
}

function selectFile(path, fileName) {
    setSelectedFile(path, fileName);

    var graphHome = document.getElementById('graph-home-view');
    var graphPanel = document.getElementById('graph-panel');
    var contentArea = document.getElementById('content-area');
    var pendingView = document.getElementById('pending-view');
    if (graphHome) graphHome.style.display = 'none';
    if (graphPanel) graphPanel.style.display = 'none';
    if (contentArea) contentArea.style.display = '';
    if (pendingView) pendingView.style.display = 'none';
    if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();

    if (window.api) {
        window.api.onFileSelected(path).catch(function() {});
    }

    var container = document.getElementById('tiptap-editor-container');
    var statusBar = document.getElementById('editor-status-bar');
    if (window._rewritingFilePath && path !== window._rewritingFilePath) {
        if (container) container.classList.remove('rewriting');
        if (statusBar) { statusBar.classList.remove('rewriting'); statusBar.textContent = ''; }
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(true);
        }
    } else if (window._rewritingFilePath && path === window._rewritingFilePath) {
        if (container) container.classList.add('rewriting');
        if (statusBar) { statusBar.classList.add('rewriting'); statusBar.textContent = 'LLM 正在改写文档...'; }
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(false);
        }
    }

    var selectGraphPanel = document.getElementById('graph-panel');
    if (selectGraphPanel && selectGraphPanel.style.display !== 'none') {
        graphPanel.style.display = 'none';
        var graphBtn = document.getElementById('titlebar-graph-btn');
        if (graphBtn) graphBtn.classList.remove('active');
    }

    var pendingLinksPanel = document.getElementById('pending-links-panel');
    if (pendingLinksPanel && pendingLinksPanel.style.display !== 'none') {
        pendingLinksPanel.style.display = 'none';
    }

    var pendingPanel = document.getElementById('topic-pending-panel');
    if (pendingPanel && pendingPanel.style.display !== 'none') {
        pendingPanel.style.display = 'none';
    }

    if (window.PreviewModule && window.PreviewModule.loadFilePreview) {
        window.PreviewModule.loadFilePreview(path, fileName);
    }
    if (window.AppState.currentSidebarView === 'graph') {
        if (window.LinksModule && window.LinksModule.loadGraphView) {
            window.LinksModule.loadGraphView();
        }
    }
}

window.TreeModule = {
    loadTreeState: loadTreeState,
    saveTreeState: saveTreeState,
    toggleTreeFolder: toggleTreeFolder,
    renderFileTree: renderFileTree,
    loadFileTree: loadFileTree,
    selectFile: selectFile,
    setSelectedFile: setSelectedFile,
    hasTopicPending: function() { return window.hasTopicPending ? window.hasTopicPending() : false; },
    updateWebAIStatus: function() {},
    updateConvAIStatus: function() {}
};

window.switchSidebarView = window.switchSidebarView;
window.toggleGraphPanel = function() {
    var panel = document.getElementById('graph-panel');
    if (!panel) return;
    if (panel.style.display === 'none') {
        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');
        var pendingView = document.getElementById('pending-view');
        if (contentPanel) contentPanel.style.display = 'flex';
        if (previewPanel) previewPanel.style.display = 'none';
        if (pendingView) pendingView.style.display = 'none';
        if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();
        panel.style.display = 'flex';
        var graphHome = document.getElementById('graph-home-view');
        var contentArea = document.getElementById('content-area');
        if (graphHome) graphHome.style.display = 'none';
        if (contentArea) contentArea.style.display = 'none';
        if (window.Graph3Tier && window.Graph3Tier.load) {
            window.Graph3Tier.load();
        }
    } else {
        // Closing graph — go to pending/log panel
        panel.style.display = 'none';
        if (window.AppState.selectedFilePath) {
            var contentArea = document.getElementById('content-area');
            if (contentArea) contentArea.style.display = '';
        } else {
            if (typeof window.togglePendingView === 'function') window.togglePendingView();
        }
    }
};
window.togglePendingLinksPanel = function() { window.LinksModule && window.LinksModule.togglePendingLinksPanel(); };
window.loadRelationGraphData = function() {
    if (window.Graph3Tier && window.Graph3Tier.load) {
        window.Graph3Tier.load();
    }
};
window.graphZoomIn = function() {
    if (window.Graph3Tier && window.Graph3Tier.zoomIn) window.Graph3Tier.zoomIn();
};
window.graphZoomOut = function() {
    if (window.Graph3Tier && window.Graph3Tier.zoomOut) window.Graph3Tier.zoomOut();
};
window.onDiscoverLinks = function() { window.LinksModule && window.LinksModule.onDiscoverLinks(); };
window.onConfirmLink = function(f, t) { window.LinksModule && window.LinksModule.onConfirmLink(f, t); };
window.onRejectLink = function(f, t) { window.LinksModule && window.LinksModule.onRejectLink(f, t); };

window.hideTreeContextMenu = hideTreeContextMenu;
window.revealInFinder = revealInFinder;
window.showTreeContextMenu = showTreeContextMenu;
window.onAddTopicFromFileTree = onAddTopicFromFileTree;
window.doDeleteTopic = doDeleteTopic;

})();

