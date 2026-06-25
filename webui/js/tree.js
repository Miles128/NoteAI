(function() { 'use strict';

var treeExpandedState = window.AppState.treeExpandedState;
var selectedFilePath = null;
var selectedFileName = null;
var _activeTreeItem = null;
var _activeFolderItem = null;
var _selectedFolderPath = '';
var SELECTED_FOLDER_KEY = 'noteai_selected_folder_path';

try {
    _selectedFolderPath = localStorage.getItem(SELECTED_FOLDER_KEY) || '';
} catch (e) {
    _selectedFolderPath = '';
}

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

function setActiveFolderItem(itemEl) {
    if (_activeFolderItem) _activeFolderItem.classList.remove('is-active');
    _activeFolderItem = itemEl;
    if (itemEl) itemEl.classList.add('is-active');
}

function escapeAttrValue(value) {
    return String(value || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function isMarkdownFile(node) {
    return node && node.type === 'file' && node.name && node.name.toLowerCase().endsWith('.md');
}

function findNodeByPath(treeData, path) {
    var found = null;
    function walk(nodes) {
        if (!nodes || found) return;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (node.path === path) {
                found = node;
                return;
            }
            if (node.children) walk(node.children);
        }
    }
    walk(treeData);
    return found;
}

function firstFolderPath(treeData) {
    var found = '';
    function walk(nodes) {
        if (!nodes || found) return;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (node.type === 'folder') {
                found = node.path;
                return;
            }
            if (node.children) walk(node.children);
        }
    }
    walk(treeData);
    return found;
}

function findParentFolderPath(treeData, filePath) {
    var parent = '';
    function walk(nodes, currentFolderPath) {
        if (!nodes || parent) return;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (node.type === 'file' && node.path === filePath) {
                parent = currentFolderPath || '';
                return;
            }
            if (node.type === 'folder' && node.children) {
                walk(node.children, node.path);
            }
        }
    }
    walk(treeData, '');
    return parent;
}

function setSelectedFolder(path, itemEl) {
    _selectedFolderPath = path || '';
    try {
        localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath);
    } catch (e) {
        console.warn('[Tree] save selected folder failed:', e);
    }
    setActiveFolderItem(itemEl || null);
    renderNoteList(_lastTreeData);
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

function buildFolderToggleHTML(expanded, hasChildren) {
    var cls = 'tree-toggle' + (expanded ? '' : ' collapsed') + (hasChildren ? '' : ' no-children');
    var openIcon = '<svg class="tree-folder-icon tree-folder-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 8.5h6.4l1.7 2h8.9l-2.1 8H4.7L3.5 8.5Z"></path><path d="M4.5 6h5.2l1.7 2h7.1v2.5"></path></svg>';
    var closedIcon = '<svg class="tree-folder-icon tree-folder-closed" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6.1l1.8 2h9.1v9.5h-17V6.5Z"></path></svg>';
    return '<span class="' + cls + '" aria-hidden="true">' + (hasChildren && expanded ? openIcon : closedIcon) + '</span>';
}

function noteTitle(node) {
    return String((node && node.name) || '').replace(/\.md$/i, '');
}

function noteDescription(node) {
    if (!node) return '';
    var summary = node.summary || node.description || node.excerpt || node.abstract || '';
    if (summary) return String(summary).replace(/\s+/g, ' ').trim();
    var meta = [];
    if (node.modified) meta.push(formatModifiedTime(node.modified));
    meta.push('Markdown');
    var path = String(node.path || '');
    var parts = path.split('/').filter(Boolean);
    if (parts.length > 1) meta.push(parts.slice(Math.max(0, parts.length - 3), -1).join(' / '));
    return meta.filter(Boolean).join(' · ');
}

function countMarkdownFiles(nodes) {
    var count = 0;
    function walk(list) {
        (list || []).forEach(function(node) {
            if (isMarkdownFile(node)) count += 1;
            if (node.children) walk(node.children);
        });
    }
    walk(nodes);
    return count;
}

function updateVaultNavCounts(treeData) {
    var allEl = document.getElementById('vault-all-notes-count');
    if (allEl) allEl.textContent = countMarkdownFiles(treeData || []);
    var inboxEl = document.getElementById('vault-inbox-count');
    var pendingBadge = document.querySelector('#titlebar-pending-btn .pending-badge');
    if (inboxEl) inboxEl.textContent = pendingBadge && pendingBadge.textContent ? pendingBadge.textContent : '0';
}

function renderFileTree(treeData, container) {
    if (!treeData || treeData.length === 0) {
        container.innerHTML = '<div class="tree-empty">' + window.t('common.noWorkspace') + '</div>';
        updateVaultNavCounts([]);
        return;
    }

    loadTreeState();
    updateVaultNavCounts(treeData);

    function buildTreeHTML(nodes, indentLevel) {
        return nodes.map(function(node) {
            var isFolder = node.type === 'folder';
            if (!isFolder) return '';
            var childFolders = (node.children || []).filter(function(child) { return child.type === 'folder'; });
            var hasChildren = childFolders.length > 0;

            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            var childrenHidden = expanded ? '' : 'hidden';

            var ep = escapeAttrValue(node.path);
            var en = escapeAttrValue(node.name);

            var html = '<div class="tree-item folder" draggable="true" data-path="' + ep + '" data-name="' + en + '">';

            for (var i = 0; i < indentLevel; i++) {
                html += '<span class="tree-indent-unit"></span>';
            }

            html += buildFolderToggleHTML(expanded, hasChildren);

            html += '<span class="tree-name">' + en + '</span>';

            html += '</div>';

            if (hasChildren) {
                html += '<div class="tree-children ' + childrenHidden + '">' + buildTreeHTML(childFolders, indentLevel + 1) + '</div>';
            }

            return html;
        }).join('');
    }

    container.innerHTML = buildTreeHTML(treeData, 0);

    container.querySelectorAll('.tree-item').forEach(function(item) {
        item.addEventListener('click', function(e) {
            var path = this.getAttribute('data-path');
            var name = this.getAttribute('data-name');
            if (e.target.closest('.tree-toggle')) {
                window.TreeModule.toggleTreeFolder(this);
            } else {
                setSelectedFolder(path, this);
            }
        });

        item.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            e.stopPropagation();
            showTreeContextMenu(e, this);
        });
    });

    setupFileTreeDragDrop(container);

    if (_selectedFolderPath) {
        var prev = container.querySelector('.tree-item[data-path="' + escapeAttrValue(_selectedFolderPath) + '"]');
        if (prev) setActiveFolderItem(prev);
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
            label: window.t('tree.deleteTopic'),
            icon: window.Icons.get('trash'),
            action: function() { showTopicDeleteConfirm(itemEl, path, name); }
        });
    }

    items.push({
        label: isFolder ? window.t('tree.deleteFolder') : window.t('tree.delete'),
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
    bar.innerHTML = '<span class="delete-confirm-text">' + window.t('tree.deleteTopicConfirm', { name: escapeHtml(name) }) + '</span>' +
        '<button class="delete-confirm-yes" title="' + window.t('common.confirmDeleteTopic') + '">' + window.Icons.get('check', 16) + '</button>' +
        '<button class="delete-confirm-no" title="' + window.t('common.cancel') + '">' + window.Icons.get('close', 16) + '</button>';

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
            alert(window.t('topic.deleteTopicFailed') + (result ? result.message || window.t('common.unknownError') : window.t('common.unknownError')));
        }
    } catch (e) {
        alert(window.t('tree.deleteTopicError') + (e.message || e));
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

var _dragDropInitialized = typeof WeakSet !== 'undefined' ? new WeakSet() : [];

function setupFileTreeDragDrop(container) {
    if (!container) return;
    if (_dragDropInitialized instanceof WeakSet) {
        if (_dragDropInitialized.has(container)) return;
        _dragDropInitialized.add(container);
    } else {
        if (_dragDropInitialized.indexOf(container) >= 0) return;
        _dragDropInitialized.push(container);
    }

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
            var isFolder = node.type === 'folder';
            if (!isFolder) continue;
            var expanded = treeExpandedState.hasOwnProperty(node.path) ? treeExpandedState[node.path] : true;
            var childFolders = (node.children || []).filter(function(child) { return child.type === 'folder'; });
            result.push({ path: node.path, name: node.name, type: node.type, depth: depth, modified: node.modified, expanded: expanded, hasChildren: childFolders.length > 0 });
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
        container.innerHTML = '<div class="tree-empty">' + window.t('common.noWorkspace') + '</div>';
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
        var ep = escapeAttrValue(node.path);
        var en = escapeAttrValue(node.name);

        html += '<div class="tree-item folder" draggable="true" data-path="' + ep + '" data-name="' + en + '">';
        for (var d = 0; d < node.depth; d++) {
            html += '<span class="tree-indent-unit"></span>';
        }
        html += buildFolderToggleHTML(node.expanded, node.hasChildren);
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
            if (e.target.closest('.tree-toggle')) {
                var currentExpanded = treeExpandedState.hasOwnProperty(path) ? treeExpandedState[path] : true;
                treeExpandedState[path] = !currentExpanded;
                saveTreeState();
                _flatVisibleNodes = flattenVisibleNodes(_lastTreeData);
                renderVirtualTree(container);
            } else {
                setSelectedFolder(path, item);
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

    if (_selectedFolderPath) {
        var prev = container.querySelector('.tree-item[data-path="' + escapeAttrValue(_selectedFolderPath) + '"]');
        if (prev) setActiveFolderItem(prev);
    }
}

function renderNoteList(treeData) {
    var container = document.getElementById('note-list');
    if (!container) return;

    if (!treeData || treeData.length === 0) {
        container.innerHTML = '<div class="tree-empty">' + window.t('common.noWorkspace') + '</div>';
        updateNoteListStatus(0);
        return;
    }

    var folderNode = _selectedFolderPath ? findNodeByPath(treeData, _selectedFolderPath) : null;
    if (_selectedFolderPath && (!folderNode || folderNode.type !== 'folder')) {
        _selectedFolderPath = firstFolderPath(treeData);
        try { localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath); } catch (_) {}
        folderNode = _selectedFolderPath ? findNodeByPath(treeData, _selectedFolderPath) : null;
    }
    if (!_selectedFolderPath) {
        _selectedFolderPath = firstFolderPath(treeData);
        try { localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath); } catch (_) {}
        folderNode = _selectedFolderPath ? findNodeByPath(treeData, _selectedFolderPath) : null;
    }

    var sourceChildren = folderNode ? (folderNode.children || []) : treeData;
    var files = sourceChildren.filter(isMarkdownFile);
    var title = folderNode ? folderNode.name : window.t('common.file');
    var html = '<div class="note-list-header">' +
        '<div class="note-list-titlebar">' +
            '<span class="note-list-heading">' + escapeHtml(title || window.t('common.file')) + '</span>' +
            '<span class="note-list-sort">↓ ' + window.t('common.modified') + '</span>' +
        '</div>' +
        '<div class="note-list-actions">' +
            '<button type="button" class="note-list-action" onclick="toggleSearchModal()" title="' + window.t('titlebar.search') + '">⌕</button>' +
            '<button type="button" class="note-list-action" onclick="openQuickCreate(\'note\')" title="' + window.t('sidebar.newNote') + '">+</button>' +
        '</div>' +
    '</div>';

    if (!files.length) {
        html += '<div class="tree-empty">' + window.t('tree.workspaceEmpty') + '</div>';
    } else {
        html += files.map(function(node) {
            var ep = escapeAttrValue(node.path);
            var en = escapeAttrValue(node.name);
            var active = selectedFilePath === node.path ? ' is-active' : '';
            var title = escapeHtml(noteTitle(node));
            var desc = escapeHtml(noteDescription(node));
            var modified = node.modified ? escapeHtml(formatModifiedTime(node.modified)) : '';
            return '<div class="tree-item file' + active + '" draggable="true" data-path="' + ep + '" data-name="' + en + '">' +
                '<span class="tree-toggle" aria-hidden="true"></span>' +
                '<span class="note-list-text">' +
                    '<span class="tree-name note-list-title">' + title + '</span>' +
                    '<span class="note-list-summary">' + desc + '</span>' +
                    '<span class="note-list-meta">' + modified + (modified ? '<span>Created ' + modified + '</span>' : '') + '</span>' +
                '</span>' +
            '</div>';
        }).join('');
    }

    container.innerHTML = html;
    updateNoteListStatus(files.length);

    container.querySelectorAll('.tree-item.file').forEach(function(item) {
        item.addEventListener('click', function() {
            var path = this.getAttribute('data-path');
            var name = this.getAttribute('data-name');
            setActiveTreeItem(this);
            window.TreeModule.selectFile(path, name);
        });
        item.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            e.stopPropagation();
            showTreeContextMenu(e, this);
        });
    });

    setupFileTreeDragDrop(container);
}

function updateNoteListStatus(count) {
    var el = document.getElementById('note-list-status');
    if (el) el.textContent = window.t('common.notesCount', { count: count || 0 });
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

        if (!force && newSetStr === _lastFileSet) {
            renderNoteList(_lastTreeData);
            return;
        }
        _lastFileSet = newSetStr;
        _lastTreeData = treeData;
        window.AppState.lastFileTreeData = treeData;

        if (Array.isArray(treeData) && treeData.length === 0) {
            container.innerHTML = '<div class="tree-empty">' + window.t('tree.workspaceEmpty') + '</div>';
            renderNoteList(treeData);
        } else {
            loadTreeState();
            if (_selectedFolderPath && !findNodeByPath(treeData, _selectedFolderPath)) {
                _selectedFolderPath = firstFolderPath(treeData);
                try { localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath); } catch (_) {}
            } else if (!_selectedFolderPath) {
                _selectedFolderPath = firstFolderPath(treeData);
                try { localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath); } catch (_) {}
            }
            _flatVisibleNodes = flattenVisibleNodes(treeData);
            renderVirtualTree(container);
            renderNoteList(treeData);
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
}

function selectFile(path, fileName) {
    setSelectedFile(path, fileName);
    if (_lastTreeData) {
        var parentFolderPath = findParentFolderPath(_lastTreeData, path);
        if (parentFolderPath && parentFolderPath !== _selectedFolderPath) {
            _selectedFolderPath = parentFolderPath;
            try { localStorage.setItem(SELECTED_FOLDER_KEY, _selectedFolderPath); } catch (_) {}
            _flatVisibleNodes = flattenVisibleNodes(_lastTreeData);
            var folderContainer = document.getElementById('file-tree');
            if (folderContainer) renderVirtualTree(folderContainer);
        }
        renderNoteList(_lastTreeData);
    }

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

    var pendingPanel = document.getElementById('topic-pending-panel');
    if (pendingPanel && pendingPanel.style.display !== 'none') {
        pendingPanel.style.display = 'none';
    }

    if (window.PreviewModule && window.PreviewModule.loadFilePreview) {
        window.PreviewModule.loadFilePreview(path, fileName);
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

window.hideTreeContextMenu = hideTreeContextMenu;
window.revealInFinder = revealInFinder;
window.showTreeContextMenu = showTreeContextMenu;
window.onAddTopicFromFileTree = onAddTopicFromFileTree;
window.doDeleteTopic = doDeleteTopic;

})();
