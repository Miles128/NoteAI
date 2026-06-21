/**
 * Note List Module (中栏笔记列表)
 *
 * 当在 sidebar 树中选中一个主题文件夹时，列出该文件夹下的所有笔记。
 * 对标 Tolaria 的 Note List 面板。
 */
(function() {
    'use strict';

    var _currentTopicPath = null;
    var _currentTopicName = '';
    var _currentNotes = [];
    var _activeFilePath = null;
    var _searchQuery = '';

    function _escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _formatDate(ts) {
        if (!ts) return '';
        var d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        var now = new Date();
        var diff = now - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
        if (diff < 604800000) return Math.floor(diff / 86400000) + '天前';
        var mm = String(d.getMonth() + 1).padStart(2, '0');
        var dd = String(d.getDate()).padStart(2, '0');
        return mm + '-' + dd;
    }

    /**
     * 从树节点中提取直接子文件（不递归子文件夹）
     */
    function _extractFilesFromNode(node, topicPath) {
        var files = [];
        if (!node) return files;

        if (node.children && node.children.length > 0) {
            for (var i = 0; i < node.children.length; i++) {
                var child = node.children[i];
                if (child.type === 'file' || (!child.type && child.children === undefined)) {
                    files.push({
                        path: child.path,
                        name: child.name,
                        modified: child.modified || null,
                        topic: _currentTopicName,
                        topicPath: topicPath
                    });
                }
            }
        }
        return files;
    }

    /**
     * 从整棵树提取所有文件（递归），保留所属主题名
     */
    function _extractAllFiles(nodes, parentTopic) {
        var files = [];
        if (!nodes) return files;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (node.type === 'file' || (!node.type && node.children === undefined)) {
                files.push({
                    path: node.path,
                    name: node.name,
                    modified: node.modified || null,
                    topic: parentTopic || '',
                    topicPath: node.path
                });
            } else if (node.children && node.children.length > 0) {
                var topicName = parentTopic
                    ? parentTopic + ' / ' + node.name
                    : node.name;
                files = files.concat(_extractAllFiles(node.children, topicName));
            }
        }
        return files;
    }

    /**
     * 从 AppState.lastFileTreeData 中找到指定路径的节点
     */
    function _findNodeByPath(nodes, path) {
        if (!nodes || !path) return null;
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].path === path) return nodes[i];
            if (nodes[i].children && nodes[i].children.length > 0) {
                var found = _findNodeByPath(nodes[i].children, path);
                if (found) return found;
            }
        }
        return null;
    }

    /**
     * 当点击树中的文件夹时调用
     */
    function showTopicNotes(folderPath, folderName) {
        _currentTopicPath = folderPath;
        _currentTopicName = folderName || '';

        var treeData = window.AppState && window.AppState.lastFileTreeData;
        if (!treeData) {
            renderEmpty();
            return;
        }

        var node = _findNodeByPath(treeData, folderPath);
        if (!node) {
            renderEmpty();
            return;
        }

        _currentNotes = _extractFilesFromNode(node, folderPath);
        _currentNotes.sort(function(a, b) {
            var am = a.modified ? new Date(a.modified).getTime() : 0;
            var bm = b.modified ? new Date(b.modified).getTime() : 0;
            return bm - am;
        });

        render();
    }

    /**
     * 显示所有笔记（默认视图，文件树加载后自动调用）
     */
    function showAllNotes() {
        _currentTopicPath = null;
        _currentTopicName = '';

        var treeData = window.AppState && window.AppState.lastFileTreeData;
        if (!treeData || !treeData.length) {
            renderEmpty();
            return;
        }

        _currentNotes = _extractAllFiles(treeData, '');
        _currentNotes.sort(function(a, b) {
            var am = a.modified ? new Date(a.modified).getTime() : 0;
            var bm = b.modified ? new Date(b.modified).getTime() : 0;
            return bm - am;
        });

        render();
    }

    function renderEmpty() {
        _currentNotes = [];
        var body = document.getElementById('note-list-body');
        var titleEl = document.getElementById('note-list-title');
        var countEl = document.getElementById('note-list-count');
        var searchWrap = document.getElementById('note-list-search-wrap');
        if (body) body.innerHTML = '<div class="note-list-empty">' + (window.t ? window.t('noteList.empty') : '暂无笔记') + '</div>';
        if (titleEl) titleEl.textContent = _currentTopicName || (window.t ? window.t('noteList.title') : '笔记列表');
        if (countEl) countEl.textContent = '0';
        if (searchWrap) searchWrap.style.display = 'none';
    }

    function render() {
        var body = document.getElementById('note-list-body');
        var titleEl = document.getElementById('note-list-title');
        var countEl = document.getElementById('note-list-count');
        var searchWrap = document.getElementById('note-list-search-wrap');
        if (!body) return;

        var filtered = _currentNotes;
        if (_searchQuery) {
            var q = _searchQuery.toLowerCase();
            filtered = _currentNotes.filter(function(n) {
                return (n.name || '').toLowerCase().indexOf(q) >= 0;
            });
        }

        if (titleEl) titleEl.textContent = _currentTopicName || (window.t ? window.t('noteList.title') : '笔记列表');
        if (countEl) countEl.textContent = String(filtered.length);
        if (searchWrap) searchWrap.style.display = _currentNotes.length > 0 ? '' : 'none';

        if (filtered.length === 0) {
            body.innerHTML = '<div class="note-list-empty">' +
                (_searchQuery ? (window.t ? window.t('noteList.noSearchResult') : '无匹配笔记') : (window.t ? window.t('noteList.emptyTopic') : '该主题下暂无笔记')) +
                '</div>';
            return;
        }

        var html = filtered.map(function(note) {
            var isActive = note.path === _activeFilePath;
            var name = _escapeHtml(note.name || '');
            var dateStr = _formatDate(note.modified);
            var topicStr = _escapeHtml(note.topic || '');
            var ext = '';
            var dotIdx = name.lastIndexOf('.');
            if (dotIdx > 0) ext = name.substring(0, dotIdx);
            var displayName = ext || name;

            return '<div class="note-list-item' + (isActive ? ' is-active' : '') + '" ' +
                'data-path="' + _escapeHtml(note.path) + '" data-name="' + _escapeHtml(note.name) + '">' +
                '<div class="note-list-item-title">' + _escapeHtml(displayName) + '</div>' +
                '<div class="note-list-item-meta">' +
                (topicStr ? '<span class="note-list-item-topic">' + topicStr + '</span>' : '') +
                (dateStr ? '<span class="note-list-item-date">' + dateStr + '</span>' : '') +
                '</div>' +
                '</div>';
        }).join('');

        body.innerHTML = html;

        var items = body.querySelectorAll('.note-list-item');
        items.forEach(function(item) {
            item.addEventListener('click', function() {
                var path = this.getAttribute('data-path');
                var name = this.getAttribute('data-name');
                if (path && window.TreeModule && window.TreeModule.selectFile) {
                    window.TreeModule.selectFile(path, name);
                }
            });
        });
    }

    function setActiveFile(filePath) {
        _activeFilePath = filePath;
        var items = document.querySelectorAll('.note-list-item');
        items.forEach(function(item) {
            if (item.getAttribute('data-path') === filePath) {
                item.classList.add('is-active');
            } else {
                item.classList.remove('is-active');
            }
        });
    }

    function clearSelection() {
        _searchQuery = '';
        var searchInput = document.getElementById('note-list-search-input');
        if (searchInput) searchInput.value = '';
        showAllNotes();
    }

    function refresh() {
        if (_currentTopicPath) {
            showTopicNotes(_currentTopicPath, _currentTopicName);
        } else {
            showAllNotes();
        }
    }

    function toggleNoteList() {
        var panel = document.getElementById('note-list-panel');
        var resizer = document.getElementById('note-list-resizer');
        var topBtn = document.getElementById('titlebar-toggle-note-list');
        if (!panel) return;
        if (panel.classList.contains('collapsed')) {
            panel.classList.remove('collapsed');
            panel.style.width = '';
            panel.style.minWidth = '';
            if (resizer) resizer.style.display = '';
            if (topBtn) topBtn.classList.add('active');
            _initResizer();
        } else {
            panel.classList.add('collapsed');
            panel.style.width = '6px';
            panel.style.minWidth = '6px';
            if (resizer) resizer.style.display = 'none';
            if (topBtn) topBtn.classList.remove('active');
        }
    }

    function init() {
        var panel = document.getElementById('note-list-panel');
        var resizer = document.getElementById('note-list-resizer');
        var topBtn = document.getElementById('titlebar-toggle-note-list');
        if (panel) {
            panel.classList.add('collapsed');
            panel.style.width = '6px';
            panel.style.minWidth = '6px';
        }
        if (resizer) resizer.style.display = 'none';
        if (topBtn) topBtn.classList.remove('active');

        var searchInput = document.getElementById('note-list-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                _searchQuery = this.value || '';
                render();
            });
        }
    }

    function _initResizer() {
        var resizer = document.getElementById('note-list-resizer');
        var panel = document.getElementById('note-list-panel');
        if (!resizer || !panel) return;

        var isResizing = false;
        var startX = 0;
        var startWidth = 0;

        resizer.addEventListener('mousedown', function(e) {
            isResizing = true;
            startX = e.clientX;
            startWidth = panel.offsetWidth;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
            e.stopPropagation();
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            var delta = e.clientX - startX;
            var newWidth = startWidth + delta;
            if (newWidth >= 180 && newWidth <= 420) {
                panel.style.width = newWidth + 'px';
                panel.style.minWidth = newWidth + 'px';
            }
        });

        document.addEventListener('mouseup', function() {
            if (!isResizing) return;
            isResizing = false;
            resizer.classList.remove('resizing');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    }

    window.NoteListModule = {
        showTopicNotes: showTopicNotes,
        showAllNotes: showAllNotes,
        setActiveFile: setActiveFile,
        clearSelection: clearSelection,
        refresh: refresh,
        init: init,
        toggleNoteList: toggleNoteList,
        getCurrentTopic: function() { return _currentTopicPath; }
    };

    window.toggleNoteList = toggleNoteList;

    document.addEventListener('DOMContentLoaded', function() {
        init();
    });
})();
