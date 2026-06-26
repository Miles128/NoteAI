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
    var saved = window.Storage.getItem(window.Storage.KEYS.TREE_STATE, null, { silent: true });
    treeExpandedState = saved || {};
}

function saveTreeState() {
    window.Storage.setItem(window.Storage.KEYS.TREE_STATE, treeExpandedState);
}

function toggleTreeFolder(element) {
    var children = element.nextElementSibling;
    if (!children || !children.classList.contains('tree-children')) return;

    children.classList.toggle('hidden');

    var toggle = element.querySelector('.tree-toggle');
    if (toggle) toggle.classList.toggle('collapsed');

    var folderIcon = element.querySelector('.tree-folder-icon');
    if (folderIcon) {
        folderIcon.innerHTML = children.classList.contains('hidden')
            ? window.Icons.get('folderFilled')
            : window.Icons.get('folderOpen');
    }

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
    if (diff < 60000) return window.t('common.timeJustNow');
    if (diff < 3600000) return window.t('common.timeMinutesAgo', { count: Math.floor(diff / 60000) });
    if (diff < 86400000) return window.t('common.timeHoursAgo', { count: Math.floor(diff / 3600000) });
    if (diff < 604800000) return window.t('common.timeDaysAgo', { count: Math.floor(diff / 86400000) });
    var m = d.getMonth() + 1;
    var day = d.getDate();
    if (d.getFullYear() === now.getFullYear()) {
        return window.t('common.timeMonthDay', { month: m, day: day });
    }
    return d.getFullYear() + '/' + m + '/' + day;
}

function renderFileTree(treeData, container) {
    if (!treeData || treeData.length === 0) {
        container.innerHTML = '<div class="tree-empty">' + window.t('common.noWorkspace') + '</div>';
        return;
    }

    loadTreeState();

    function buildTreeHTML(nodes, indentLevel) {
        return nodes.map(function(node) {
            var isFolder = node.type === 'folder';
            var hasChildren = node.children && node.children.length > 0;

            // 只渲染文件夹节点（Tolaria Files-first：侧边栏只显示文件夹层级）
            if (!isFolder) {
                return '';
            }

            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            var childrenHidden = expanded ? '' : 'hidden';

            var ep = node.path.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            var en = node.name.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

            var levelClass = 'tree-level-' + Math.min(indentLevel, 3);
            var folderIcon = expanded ? window.Icons.get('folderOpen') : window.Icons.get('folderFilled');

            var html = '<div class="tree-item folder ' + levelClass + '" draggable="true" data-path="' + ep + '" data-name="' + en + '">';

            for (var i = 0; i < indentLevel; i++) {
                html += '<span class="tree-indent-unit"></span>';
            }

            html += '<span class="tree-toggle ' + (expanded ? '' : 'collapsed') + '" onclick="event.stopPropagation(); TreeModule.toggleTreeFolder(this.parentElement);">' + window.Icons.get('chevron') + '</span>';
            html += '<span class="tree-folder-icon">' + folderIcon + '</span>';
            html += '<span class="tree-name">' + en + '</span>';
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
                setActiveTreeItem(this);
                window.TreeModule.toggleTreeFolder(this);
                // 触发 Note List 显示该主题下的笔记
                if (window.NoteListModule && window.NoteListModule.showTopicNotes) {
                    window.NoteListModule.showTopicNotes(path, name);
                }
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
        label: window.t('tree.revealInFinder'),
        icon: window.Icons.get('folder'),
        action: function() { revealInFinder(path); }
    });

    if (!isFolder) {
        items.push({
            label: window.t('tree.openInNewWindow'),
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
            label: window.t('tree.deleteTopicFolder'),
            icon: window.Icons.get('trash'),
            action: function() { showDeleteTopicFolderConfirm(path, name); }
        });
    } else {
        items.push({
            label: window.t('tree.delete'),
            icon: window.Icons.get('trash'),
            action: function() { showDeleteConfirm(itemEl, path, name); }
        });
    }

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

async function showDeleteTopicFolderConfirm(path, name) {
    var topicName = name;
    var message = window.t('tree.deleteTopicFolderConfirm', { name: escapeHtml(name) }) + '\n\n' +
        window.t('tree.deleteTopicFolderDetail', { path: escapeHtml(path) }) + '\n' +
        window.t('tree.deleteTopicFolderWarning');

    var confirmed = await window._customConfirm(message);
    if (!confirmed) return;

    try {
        var topicResult = await window.api.deleteTopic(topicName);
        if (!topicResult || !topicResult.success) {
            alert(window.t('topic.deleteTopicFailed') + (topicResult ? topicResult.message || window.t('common.unknownError') : window.t('common.unknownError')));
            return;
        }

        var fileResult = await window.api.invoke('delete_file', { path: path });
        if (fileResult && fileResult.success) {
            window.TreeModule.loadFileTree();
        } else {
            alert(window.t('tree.deleteFolderFailed') + (fileResult ? fileResult.message || window.t('common.unknownError') : window.t('common.unknownError')));
        }
    } catch (e) {
        alert(window.t('tree.deleteTopicFolderError') + (e.message || e));
    }
}

function onAddTopicFromFileTree() {
    var topicName = prompt(window.t('tree.enterTopicName'));
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
                alert(window.t('tree.createTopicFailed') + (result ? result.message : window.t('common.unknownError')));
            }
        }).catch(function(e) {
            alert(window.t('tree.createTopicError') + (e.message || e));
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
    bar.innerHTML = '<span class="delete-confirm-text">' + window.t('tree.deleteConfirm', { name: escapeHtml(name) }) + '</span>' +
        '<button class="delete-confirm-yes" title="' + window.t('common.confirmDelete') + '">' + window.Icons.get('check', 16) + '</button>' +
        '<button class="delete-confirm-no" title="' + window.t('common.cancel') + '">' + window.Icons.get('close', 16) + '</button>';

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
            alert(window.t('tree.deleteFailed') + (result ? result.message || window.t('common.unknownError') : window.t('common.unknownError')));
        }
    } catch (e) {
        alert(window.t('tree.deleteError') + (e.message || e));
    }
}

function revealInFinder(path) {
    if (window.api && window.api.invoke) {
        window.api.invoke('reveal_in_finder', { path: path });
    }
}

async function deleteFile(path, name) {
    if (!(await window._customConfirm(window.t('tree.confirmDeleteItem', { name: name })))) return;
    if (window.api && window.api.invoke) {
        window.api.invoke('delete_file', { path: path }).then(function(result) {
            if (result && result.success) {
                window.TreeModule.loadFileTree();
            } else {
                alert(window.t('tree.deleteFailed') + (result ? result.message || window.t('common.unknownError') : window.t('common.unknownError')));
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
        _fileTreeDragData.fileName = itemEl.getAttribute('data-name') || window.t('common.file');
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
                    alert(window.t('topic.moveFailed') + (result ? result.message : window.t('common.unknownError')));
                }
            } catch (err) {
                console.error('[FileTree] move error:', err);
                alert(window.t('topic.moveFailed') + (err.message || window.t('common.errorOccurred')));
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
            // 侧边栏仅展示文件夹层级，跳过具体文件
            if (node.type !== 'folder') continue;
            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            result.push({ path: node.path, name: node.name, type: node.type, depth: depth, modified: node.modified, expanded: expanded });
            if (expanded && node.children) {
                walk(node.children, depth + 1);
            }
        }
    }
    walk(treeData, 0);
    return result;
}

function renderVirtualTree(container) {
    if (!_flatVisibleNodes || _flatVisibleNodes.length === 0) {
        container.innerHTML = '<div class="tree-empty">' + window.t('common.noWorkspace') + '</div>';
        return;
    }

    var scrollTop = container.scrollTop || 0;
    var viewHeight = container.clientHeight || 600;

    _virtualScrollStartIdx = Math.floor(scrollTop / _virtualScrollItemHeight);
    _virtualScrollVisibleCount = Math.ceil(viewHeight / _virtualScrollItemHeight) + 5;

    var startIdx = Math.max(0, _virtualScrollStartIdx - 2);
    var endIdx = Math.min(_flatVisibleNodes.length, startIdx + _virtualScrollVisibleCount + 4);

    var html = '<div class="tree-virtual-spacer" style="height:' + (startIdx * _virtualScrollItemHeight) + 'px"></div>';

    for (var i = startIdx; i < endIdx; i++) {
        var node = _flatVisibleNodes[i];
        var expanded = node.expanded;
        var levelClass = 'tree-level-' + Math.min(node.depth, 3);
        var folderIcon = expanded ? window.Icons.get('folderOpen') : window.Icons.get('folderFilled');
        var ep = node.path.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        var en = node.name.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        html += '<div class="tree-item folder ' + levelClass + '" draggable="true" data-path="' + ep + '" data-name="' + en + '">';
        for (var d = 0; d < node.depth; d++) {
            html += '<span class="tree-indent-unit"></span>';
        }
        html += '<span class="tree-toggle ' + (expanded ? '' : 'collapsed') + '">' + window.Icons.get('chevron') + '</span>';
        html += '<span class="tree-folder-icon">' + folderIcon + '</span>';
        html += '<span class="tree-name">' + en + '</span>';
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
            var currentExpanded = treeExpandedState.hasOwnProperty(path) ? treeExpandedState[path] : true;
            treeExpandedState[path] = !currentExpanded;
            saveTreeState();
            _flatVisibleNodes = flattenVisibleNodes(_lastTreeData);
            renderVirtualTree(container);
            var refreshedItem = container.querySelector('.tree-item[data-path="' + path.replace(/"/g, '&quot;') + '"]');
            if (refreshedItem) setActiveTreeItem(refreshedItem);
            if (window.NoteListModule && window.NoteListModule.showTopicNotes) {
                window.NoteListModule.showTopicNotes(path, name);
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

function _findFirstFolderWithFiles(nodes) {
    if (!nodes) return null;
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (node.type === 'folder') {
            var hasFileChild = node.children && node.children.some(function(child) {
                return child.type === 'file' && child.name && child.name.toLowerCase().endsWith('.md');
            });
            if (hasFileChild) return node;
            var found = _findFirstFolderWithFiles(node.children);
            if (found) return found;
        }
    }
    return null;
}

var _lastFileSet = null;
var FILE_TREE_LOAD_TIMEOUT_MS = 15000;
var _loadFileTreeInFlight = null;

function _describeTreeLoadError(error) {
    if (!error) return window.t('common.unknownError');
    if (typeof error === 'string') return error;
    if (error.message) return error.message;
    try {
        return JSON.stringify(error);
    } catch (_) {
        return String(error);
    }
}

async function loadFileTree(force) {
    if (_loadFileTreeInFlight) {
        return _loadFileTreeInFlight;
    }
    _loadFileTreeInFlight = _loadFileTreeOnce(!!force);
    try {
        return await _loadFileTreeInFlight;
    } finally {
        _loadFileTreeInFlight = null;
    }
}

async function _loadFileTreeOnce(force) {
    var container = document.getElementById('file-tree');
    if (!container) return;

    if (!window.api) {
        container.innerHTML = '<div class="tree-empty">' + window.t('tree.workspaceNotSet') + '</div>';
        return;
    }

    try {
        var treeData = await Promise.race([
            window.api.getWorkspaceTree(),
            new Promise(function(_, reject) { setTimeout(function() { reject(new Error(window.t('tree.loadTimeout'))); }, FILE_TREE_LOAD_TIMEOUT_MS); })
        ]);

        if (!Array.isArray(treeData)) {
            throw new Error(window.t('tree.invalidFormat', { detail: _describeTreeLoadError(treeData) }));
        }

        var newFileSet = extractFileSet(treeData);
        var newSetStr = JSON.stringify(newFileSet);

        if (!force && newSetStr === _lastFileSet) return;
        _lastFileSet = newSetStr;
        _lastTreeData = treeData;
        window.AppState.lastFileTreeData = treeData;

        if (Array.isArray(treeData) && treeData.length === 0) {
            container.innerHTML = '<div class="tree-empty">' + window.t('tree.workspaceEmpty') + '</div>';
        } else {
            loadTreeState();
            _flatVisibleNodes = flattenVisibleNodes(treeData);
            renderVirtualTree(container);
        }
    } catch (e) {
        console.warn('[Tree] Load skipped:', _describeTreeLoadError(e), e);
        if (!_lastTreeData) {
            container.innerHTML = '<div class="tree-empty">' + window.t('tree.loadFailed') + '</div>';
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
    try {
        if (window.NoteListModule) {
            var currentTopic = window.NoteListModule.getCurrentTopic && window.NoteListModule.getCurrentTopic();
            if (currentTopic) {
                window.NoteListModule.refresh();
            } else {
                var defaultFolder = _findFirstFolderWithFiles(treeData);
                if (!defaultFolder && _flatVisibleNodes && _flatVisibleNodes.length) {
                    defaultFolder = _flatVisibleNodes[0];
                }
                if (defaultFolder) {
                    var item = container.querySelector('.tree-item[data-path="' + defaultFolder.path.replace(/"/g, '&quot;') + '"]');
                    if (item) setActiveTreeItem(item);
                    window.NoteListModule.showTopicNotes(defaultFolder.path, defaultFolder.name);
                } else if (window.NoteListModule.showAllNotes) {
                    window.NoteListModule.showAllNotes();
                }
            }
        }
    } catch (e) {
        console.warn('[Tree] NoteListModule init failed:', e);
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

    // 触发 Note List 高亮当前文件
    if (window.NoteListModule && window.NoteListModule.setActiveFile) {
        window.NoteListModule.setActiveFile(path);
    }
    // 触发 Inspector 更新属性/Backlinks
    if (window.InspectorModule && window.InspectorModule.onFileSelected) {
        window.InspectorModule.onFileSelected(path);
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
        if (statusBar) { statusBar.classList.add('rewriting'); statusBar.textContent = window.t('app.llmRewriting'); }
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

})();

