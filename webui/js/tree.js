var treeExpandedState = {};
var selectedFilePath = null;
var selectedFileName = null;
var _activeTreeItem = null;

function loadTreeState() {
    try {
        var saved = localStorage.getItem('tree-expanded-state');
        if (saved) treeExpandedState = JSON.parse(saved);
    } catch (e) {
        treeExpandedState = {};
    }
}

function saveTreeState() {
    try {
        localStorage.setItem('tree-expanded-state', JSON.stringify(treeExpandedState));
    } catch (e) {}
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
                html += '<span class="tree-toggle ' + (expanded ? '' : 'collapsed') + '"><svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg></span>';
            } else {
                html += '<span class="tree-toggle" style="visibility:hidden"><svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg></span>';
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
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>', 
        action: function() { revealInFinder(path); } 
    });

    if (!isFolder) {
        items.push({ 
            label: '在新窗口打开', 
            icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>', 
            action: function() { 
                if (window.api && window.api.openFileInNewWindow) {
                    window.api.openFileInNewWindow(path, name);
                }
            } 
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

function hideTreeContextMenu() {
    var existing = document.getElementById('tree-ctx-menu');
    if (existing) existing.remove();
}

function revealInFinder(path) {
    if (window.api && window.api.pyCall) {
        window.api.pyCall('reveal_in_finder', { path: path });
    }
}

function deleteFile(path, name) {
    if (!confirm('确定要删除 "' + name + '" 吗？')) return;
    if (window.api && window.api.pyCall) {
        window.api.pyCall('delete_file', { path: path }).then(function(result) {
            if (result && result.success) {
                window.TreeModule.loadFileTree();
            } else {
                alert('删除失败：' + (result ? result.message || '未知错误' : '未知错误'));
            }
        });
    }
}

var _fileTreeDragData = { filePath: null, fileName: null, isFolder: false };

function setupFileTreeDragDrop(container) {
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
                var result = await window.api.move_file(srcPath, targetPath);
                if (result && result.success) {
                    await window.TreeModule.loadFileTree();
                    var topicContainer = document.getElementById('sidebar-topic');
                    if (topicContainer && topicContainer.style.display !== 'none') {
                        loadTopicView();
                    }
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
    if (!e.target.closest('.tree-item')) hideTreeContextMenu();
});

async function loadFileTree() {
    var container = document.getElementById('file-tree');
    if (!container) return;

    if (!window.api) {
        container.innerHTML = '<div class="tree-empty">工作区未设置</div>';
        return;
    }

    try {
        var treeData = await Promise.race([
            window.api.get_workspace_tree(),
            new Promise(function(_, reject) { setTimeout(function() { reject(new Error('加载超时')); }, 5000); })
        ]);
        if (Array.isArray(treeData) && treeData.length === 0) {
            container.innerHTML = '<div class="tree-empty">工作区为空</div>';
        } else {
            renderFileTree(treeData, container);
        }
    } catch (e) {
        console.error('[Tree] Load failed:', e);
        container.innerHTML = '<div class="tree-empty">加载失败</div>';
    }
}

function selectFile(path, fileName) {
    selectedFilePath = path;
    selectedFileName = fileName;
    if (window.api) {
        window.api.on_file_selected(path);
    }
    if (window.PreviewModule && window.PreviewModule.loadFilePreview) {
        window.PreviewModule.loadFilePreview(path, fileName);
    }
}

var _currentSidebarView = 'tree';

function switchSidebarView(view) {
    _currentSidebarView = view;

    var fileTree = document.getElementById('file-tree');
    var sidebarTags = document.getElementById('sidebar-tags');
    var sidebarTopic = document.getElementById('sidebar-topic');
    var sidebarGraph = document.getElementById('sidebar-graph');
    var sidebar = document.querySelector('.sidebar-left');
    var resizer = document.getElementById('sidebar-resizer');

    if (sidebar) sidebar.style.display = 'flex';
    if (resizer) resizer.style.display = '';

    if (fileTree) fileTree.style.display = view === 'tree' ? '' : 'none';
    if (sidebarTags) sidebarTags.style.display = view === 'tags' ? '' : 'none';
    if (sidebarTopic) sidebarTopic.style.display = view === 'topic' ? '' : 'none';
    if (sidebarGraph) sidebarGraph.style.display = view === 'graph' ? '' : 'none';

    document.querySelectorAll('.sidebar-view-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.sidebar === view);
    });

    if (view === 'topic') {
        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');
        var pendingPanel = document.getElementById('topic-pending-panel');
        if (contentPanel) contentPanel.style.display = 'none';
        if (previewPanel) previewPanel.style.display = 'none';
        if (pendingPanel) pendingPanel.style.display = '';
    } else {
        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');
        var pendingPanel = document.getElementById('topic-pending-panel');
        if (contentPanel) contentPanel.style.display = '';
        if (pendingPanel) pendingPanel.style.display = 'none';
    }

    if (view === 'tags') loadTagsView();
    if (view === 'topic') loadTopicView();
    if (view === 'graph') loadGraphView();
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

async function loadTagsView() {
    var container = document.getElementById('sidebar-tags');
    if (!container) return;
    container.innerHTML = '<div class="sidebar-view-loading">加载标签...</div>';

    try {
        var result = await window.api.get_all_tags();
        if (!result || !result.tags || result.tags.length === 0) {
            container.innerHTML = '<div class="sidebar-view-empty">暂无标签<br><span style="font-size:11px;color:var(--text-muted)">点击下方按钮自动匹配标签</span></div>';
        } else {
            var html = '<div class="sidebar-tags-list">';
            result.tags.forEach(function(tag) {
                html += '<div class="sidebar-tag-group" data-tag-name="' + escapeAttr(tag.name) + '">';
                html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')">';
                html += '<svg class="sidebar-tag-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
                html += '<span class="sidebar-tag-name">' + escapeHtml(tag.name) + '</span>';
                html += '<span class="sidebar-tag-count">' + tag.count + '</span>';
                html += '</div>';
                html += '<div class="sidebar-tag-files">';
                tag.files.forEach(function(file) {
                    var fileName = file.split('/').pop();
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + escapeAttr(file) + '" data-file-name="' + escapeAttr(fileName) + '" onclick="window.TreeModule.selectFile(\'' + escapeAttr(file) + '\', \'' + escapeAttr(fileName) + '\')">';
                    html += '<span class="tree-indent-unit"></span>';
                    html += '<span class="tree-name">' + escapeHtml(fileName) + '</span>';
                    html += '</div>';
                });
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;

            setupTagsDragDrop(container);
            setupTagsContextMenu(container);
        }

        var actionBar = document.createElement('div');
        actionBar.className = 'sidebar-tags-action';
        actionBar.innerHTML = '<button class="sidebar-tags-action-btn" onclick="doAutoTag()">自动匹配标签</button><button class="sidebar-tags-action-btn" onclick="doSaveTagsMd()">保存 tags.md</button>';
        container.appendChild(actionBar);
    } catch (e) {
        container.innerHTML = '<div class="sidebar-view-empty">加载标签失败</div>';
    }
}

var _tagsDragData = { filePath: null, fileName: null };

function setupTagsDragDrop(container) {
    container.addEventListener('dragstart', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (!fileEl) return;

        var filePath = fileEl.getAttribute('data-file-path');
        if (!filePath) return;

        _tagsDragData.filePath = filePath;
        _tagsDragData.fileName = fileEl.getAttribute('data-file-name') || '文件';
        fileEl.classList.add('dragging');

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', filePath);
        e.dataTransfer.setData('text/html', '<span>' + escapeHtml(_tagsDragData.fileName) + '</span>');
    });

    container.addEventListener('dragend', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (fileEl) fileEl.classList.remove('dragging');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        _tagsDragData.filePath = null;
        _tagsDragData.fileName = null;
    });

    container.addEventListener('dragover', function(e) {
        if (!_tagsDragData.filePath) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        var rowEl = e.target.closest('.sidebar-tag-row');
        var groupEl = e.target.closest('.sidebar-tag-group');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        if (rowEl) {
            var targetTag = rowEl.closest('.sidebar-tag-group')?.getAttribute('data-tag-name');
            if (targetTag) {
                rowEl.classList.add('drag-over');
            }
        } else if (groupEl) {
            var row = groupEl.querySelector('.sidebar-tag-row');
            if (row) row.classList.add('drag-over');
        }
    });

    container.addEventListener('dragleave', function(e) {
        var rowEl = e.target.closest('.sidebar-tag-row');
        if (rowEl) rowEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e) {
        e.preventDefault();

        if (!_tagsDragData.filePath) return;

        var rowEl = e.target.closest('.sidebar-tag-row');
        var groupEl = e.target.closest('.sidebar-tag-group');

        var targetTag = null;
        if (rowEl) {
            targetTag = rowEl.closest('.sidebar-tag-group')?.getAttribute('data-tag-name');
        } else if (groupEl) {
            targetTag = groupEl.getAttribute('data-tag-name');
        }

        if (!targetTag) {
            container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
                row.classList.remove('drag-over', 'drag-over-top');
            });
            return;
        }

        try {
            var result = await window.api.add_tag_to_file(_tagsDragData.filePath, targetTag);
            if (result && result.success) {
                await loadTagsView();
            } else {
                alert('添加标签失败：' + (result ? result.message : '未知错误'));
            }
        } catch (err) {
            console.error('[Tags] add tag error:', err);
            alert('添加标签失败：' + (err.message || '发生错误'));
        }

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });
    });
}

function setupTagsContextMenu(container) {
    container.addEventListener('contextmenu', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (fileEl) {
            e.preventDefault();
            e.stopPropagation();
            showTagsContextMenu(e, fileEl);
        }
    });
}

function showTagsContextMenu(e, fileEl) {
    hideTreeContextMenu();

    var path = fileEl.getAttribute('data-file-path');
    var name = fileEl.getAttribute('data-file-name');

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({ 
        label: '在访达中显示', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>', 
        action: function() { revealInFinder(path); } 
    });

    items.push({ 
        label: '在新窗口打开', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>', 
        action: function() { 
            if (window.api && window.api.openFileInNewWindow) {
                window.api.openFileInNewWindow(path, name);
            }
        } 
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

async function doAutoTag() {
    var btns = document.querySelectorAll('.sidebar-tags-action-btn');
    var btn = btns[0];
    if (btn) {
        btn.disabled = true;
        btn.textContent = '匹配中...';
    }
    try {
        var result = await window.api.auto_tag_files();
        if (result && result.success) {
            if (btn) btn.textContent = '已更新 ' + result.updated + ' 个文件';
            setTimeout(function() { loadTagsView(); }, 1500);
        } else {
            if (btn) btn.textContent = result.message || '匹配失败';
            setTimeout(function() { if (btn) { btn.disabled = false; btn.textContent = '自动匹配标签'; } }, 2000);
        }
    } catch (e) {
        if (btn) btn.textContent = '匹配失败';
        setTimeout(function() { if (btn) { btn.disabled = false; btn.textContent = '自动匹配标签'; } }, 2000);
    }
}

async function doSaveTagsMd() {
    var btns = document.querySelectorAll('.sidebar-tags-action-btn');
    var btn = btns[1];
    if (btn) {
        btn.disabled = true;
        btn.textContent = '保存中...';
    }
    try {
        var result = await window.api.save_tags_md();
        if (result && result.success) {
            if (btn) btn.textContent = '已保存 ' + result.count + ' 个标签';
            setTimeout(function() { if (btn) { btn.disabled = false; btn.textContent = '保存 tags.md'; } }, 2000);
        } else {
            if (btn) btn.textContent = result.message || '保存失败';
            setTimeout(function() { if (btn) { btn.disabled = false; btn.textContent = '保存 tags.md'; } }, 2000);
        }
    } catch (e) {
        if (btn) btn.textContent = '保存失败';
        setTimeout(function() { if (btn) { btn.disabled = false; btn.textContent = '保存 tags.md'; } }, 2000);
    }
}

async function loadTopicTree() {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;
    container.innerHTML = '<div class="sidebar-view-loading">加载主题...</div>';

    try {
        var result = await window.api.get_topic_tree();
        console.log('[Topic] API result:', result);

        if (!result || typeof result !== 'object') {
            container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">API 返回异常</span></div>';
            return;
        }

        if (result.success === false) {
            container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">' + escapeHtml(result.message || '后端错误') + '</span></div>';
            return;
        }

        var topics = result.topics || [];
        var hasTopics = topics.length > 0;

        if (!hasTopics) {
            container.innerHTML = '<div class="sidebar-view-empty">暂无已确认主题<br><span style="font-size:11px;color:var(--text-muted)">待确认的主题在右侧处理</span></div>';
            return;
        }

        var html = '<div class="sidebar-tags-list">';
        result.topics.forEach(function(topic) {
            html += '<div class="sidebar-tag-group" data-topic-name="' + escapeAttr(topic.name) + '">';
            html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')" data-topic-name="' + escapeAttr(topic.name) + '">';
            html += '<svg class="sidebar-tag-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
            html += '<span class="sidebar-tag-name" data-topic-name="' + escapeAttr(topic.name) + '">' + escapeHtml(topic.name) + '</span>';
            html += '<span class="sidebar-tag-count">' + topic.files.length + '</span>';
            html += '</div>';
            html += '<div class="sidebar-tag-files">';
            topic.files.forEach(function(f) {
                var display = f.title || '未命名';
                var path = f.path || '';
                if (path) {
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + escapeAttr(path) + '" onclick="window.TreeModule.selectFile(\'' + escapeAttr(path) + '\', \'' + escapeAttr(display) + '\')">';
                } else {
                    html += '<div class="sidebar-tag-file tree-item">';
                }
                html += '<span class="tree-indent-unit"></span>';
                html += '<span class="tree-name">' + escapeHtml(display) + '</span>';
                html += '</div>';
            });
            html += '</div>';
            html += '</div>';
        });
        html += '</div>';

        html += '<div class="topic-context-menu" id="topic-context-menu" style="display:none;">';
        html += '<div class="topic-menu-item" data-action="rename">重命名</div>';
        html += '</div>';

        html += '<style>';
        html += '.topic-context-menu { position: fixed; z-index: 10000; background: var(--background-secondary); border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); padding: 4px 0; min-width: 120px; }';
        html += '.topic-menu-item { padding: 6px 12px; cursor: pointer; font-size: 13px; color: var(--text-normal); }';
        html += '.topic-menu-item:hover { background: var(--interactive-hover); }';
        html += '.sidebar-tag-row { position: relative; }';
        html += '.sidebar-tag-row.drag-over { background: var(--background-modifier-hover); outline: 1px solid var(--text-accent); outline-offset: -1px; }';
        html += '.sidebar-tag-row.drag-over-top { border-top: 2px solid var(--text-accent); }';
        html += '.sidebar-tag-file.dragging { opacity: 0.4; }';
        html += '.topic-rename-input { background: var(--background-modifier-hover); border: 1px solid var(--text-accent); border-radius: 4px; padding: 2px 6px; color: var(--text-normal); font-size: 13px; outline: none; min-width: 80px; }';
        html += '</style>';

        container.innerHTML = html;

        setupTopicDragDrop(container);
        setupTopicContextMenu(container);
    } catch (e) {
        console.error('[Topic] loadTopicTree error:', e);
        container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">' + escapeHtml(e.message || '未知错误') + '</span></div>';
    }
}

function setupTopicDragDrop(container) {
    var dragData = { filePath: null, fileName: null, srcTopic: null };

    container.addEventListener('dragstart', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (!fileEl) return;

        var filePath = fileEl.getAttribute('data-file-path');
        if (!filePath) return;

        var srcGroup = fileEl.closest('.sidebar-tag-group');
        var srcTopic = srcGroup ? srcGroup.getAttribute('data-topic-name') : null;

        dragData.filePath = filePath;
        dragData.fileName = fileEl.querySelector('.tree-name')?.textContent || '文件';
        dragData.srcTopic = srcTopic;
        fileEl.classList.add('dragging');

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', filePath);
        e.dataTransfer.setData('application/x-topic-src', srcTopic || '');
    });

    container.addEventListener('dragend', function(e) {
        container.querySelectorAll('.sidebar-tag-file.dragging').forEach(function(el) {
            el.classList.remove('dragging');
        });
        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });
        dragData.filePath = null;
        dragData.fileName = null;
        dragData.srcTopic = null;
    });

    container.addEventListener('dragover', function(e) {
        var pendingCard = document.querySelector('.topic-pending-card.dragging');
        if (!dragData.filePath && !pendingCard) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        var rowEl = e.target.closest('.sidebar-tag-row');
        var groupEl = e.target.closest('.sidebar-tag-group');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        var targetTopic = null;
        if (rowEl) {
            targetTopic = rowEl.getAttribute('data-topic-name');
        } else if (groupEl) {
            targetTopic = groupEl.getAttribute('data-topic-name');
        }

        if (!targetTopic) return;

        // For pending cards: always allow drop on any topic
        if (pendingCard) {
            if (rowEl) {
                rowEl.classList.add('drag-over');
            } else if (groupEl) {
                var row = groupEl.querySelector('.sidebar-tag-row');
                if (row) row.classList.add('drag-over');
            }
            return;
        }

        // For topic-internal drags: don't highlight same topic
        if (dragData.srcTopic === targetTopic) return;

        if (rowEl) {
            rowEl.classList.add('drag-over');
        } else if (groupEl) {
            var row = groupEl.querySelector('.sidebar-tag-row');
            if (row) row.classList.add('drag-over');
        }
    });

    container.addEventListener('dragleave', function(e) {
        var rowEl = e.target.closest('.sidebar-tag-row');
        if (rowEl) rowEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e) {
        e.preventDefault();
        e.stopPropagation();

        // --- Pending card drop branch ---
        var pendingCard = document.querySelector('.topic-pending-card.dragging');
        if (pendingCard) {
            var pendingFile = pendingCard.getAttribute('data-file');
            var targetEl = e.target.closest('.sidebar-tag-row') || e.target.closest('.sidebar-tag-group');
            var targetTopic = targetEl ? targetEl.getAttribute('data-topic-name') : null;

            if (!targetTopic || !pendingFile) {
                cleanupDragState(container);
                return;
            }

            try {
                var result = await window.api.resolve_topic(pendingFile, targetTopic);
                if (result && result.success) {
                    pendingCard.classList.add('resolved');
                    animateCardOut(pendingCard);
                } else {
                    alert('确认主题失败：' + (result ? result.message : '未知错误'));
                }
            } catch (err) {
                console.error('[Topic] resolve via drag error:', err);
                alert('确认主题失败：' + (err.message || '发生错误'));
            }

            cleanupDragState(container);
            return;
        }
        // --- End pending card drop branch ---

        var filePath = dragData.filePath;
        if (!filePath) {
            cleanupDragState(container);
            return;
        }

        var targetEl2 = e.target.closest('.sidebar-tag-row') || e.target.closest('.sidebar-tag-group');
        var targetTopic2 = targetEl2 ? targetEl2.getAttribute('data-topic-name') : null;

        if (!targetTopic2) {
            cleanupDragState(container);
            return;
        }

        if (dragData.srcTopic === targetTopic2) {
            cleanupDragState(container);
            return;
        }

        console.log('[Topic] Move file:', filePath, 'from:', dragData.srcTopic, 'to:', targetTopic2);

        try {
            var result2 = await window.api.move_file_to_topic(filePath, targetTopic2);
            if (result2 && result2.success) {
                await loadTopicTree();
            } else {
                console.error('[Topic] move failed:', result2);
                alert('移动失败：' + (result2 ? result2.message : '未知错误'));
            }
        } catch (err) {
            console.error('[Topic] move error:', err);
            alert('移动失败：' + (err.message || '发生错误'));
        }

        cleanupDragState(container);
    });

    function cleanupDragState(cont) {
        cont.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });
    }
}

function setupTopicContextMenu(container) {
    container.addEventListener('contextmenu', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        var rowEl = e.target.closest('.sidebar-tag-row');
        
        if (fileEl) {
            e.preventDefault();
            e.stopPropagation();
            showTopicFileContextMenu(e, fileEl);
        } else if (rowEl) {
            e.preventDefault();
            e.stopPropagation();
            showTopicContextMenu(e, rowEl);
        }
    });
}

function showTopicContextMenu(e, rowEl) {
    hideTreeContextMenu();

    var topicName = rowEl.getAttribute('data-topic-name');
    var tagNameEl = rowEl.querySelector('.sidebar-tag-name');
    if (!topicName) return;

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({ 
        label: '更改名称', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>', 
        action: function() { 
            if (tagNameEl) {
                startTopicRename(tagNameEl, topicName);
            }
        } 
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

function showTopicFileContextMenu(e, fileEl) {
    hideTreeContextMenu();

    var path = fileEl.getAttribute('data-file-path');
    var name = fileEl.querySelector('.tree-name')?.textContent || '文件';

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({ 
        label: '在访达中显示', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>', 
        action: function() { revealInFinder(path); } 
    });

    items.push({ 
        label: '在新窗口打开', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>', 
        action: function() { 
            if (window.api && window.api.openFileInNewWindow) {
                window.api.openFileInNewWindow(path, name);
            }
        } 
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

function startTopicRename(tagNameEl, oldTopicName) {
    var parentRow = tagNameEl.closest('.sidebar-tag-row');
    if (!parentRow) return;

    var originalHtml = tagNameEl.innerHTML;
    var originalDisplay = tagNameEl.style.display;

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'topic-rename-input';
    input.value = oldTopicName;
    input.style.minWidth = (tagNameEl.offsetWidth + 20) + 'px';

    tagNameEl.style.display = 'none';
    parentRow.insertBefore(input, tagNameEl.nextSibling);
    input.focus();
    input.select();

    var finished = false;
    function finishRename(cancel) {
        if (finished) return;
        finished = true;

        var newName = input.value.trim();
        input.remove();
        tagNameEl.style.display = originalDisplay || '';

        if (cancel || !newName || newName === oldTopicName) {
            return;
        }

        console.log('[Topic] Rename:', oldTopicName, '->', newName);

        window.api.rename_topic(oldTopicName, newName).then(function(result) {
            console.log('[Topic] rename result:', result);
            if (result && result.success) {
                loadTopicTree();
            } else {
                console.error('[Topic] rename failed:', result);
            }
        }).catch(function(e) {
            console.error('[Topic] rename error:', e);
        });
    }

    input.addEventListener('blur', function() {
        finishRename(false);
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            finishRename(true);
        }
    });

    input.addEventListener('click', function(e) {
        e.stopPropagation();
    });

    var rowClickHandler = function(e) {
        if (e.target === input || e.target.closest('.topic-rename-input')) {
            e.stopPropagation();
        }
    };
    parentRow.addEventListener('click', rowClickHandler);
}

async function onBatchAutoAssignTopics() {
    var btn = document.getElementById('btn-auto-topic');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }

    try {
        var result = await window.api.batch_auto_assign_topics();
        if (result && result.success) {
            await loadTopicTree();

            if (result.pending && result.pending.length > 0) {
                loadTopicPendingPanel(result.pending);
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = '';
            }

            var msg = '扫描完成：共 ' + result.total + ' 个文件';
            msg += '，自动分配 ' + result.auto_assigned + ' 个';
            msg += '，待确认 ' + result.need_confirm + ' 个';
            msg += '，跳过 ' + result.skipped + ' 个';
            console.log('[Topic] ' + msg);
        } else {
            var errMsg = result && result.message ? result.message : '未知错误';
            console.error('[Topic] batch failed:', result);
            alert('自动分配主题失败：' + errMsg);
        }
    } catch (e) {
        console.error('[Topic] batch error:', e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    }
}

function onShowTopicInput() {
    var inputPanel = document.getElementById('sidebar-topic-input');
    var inputField = document.getElementById('topic-input-field');
    var confirmBtn = document.getElementById('topic-input-confirm');
    
    if (!inputPanel || !inputField) return;
    
    inputPanel.style.display = '';
    inputField.value = '';
    inputField.focus();
    
    if (confirmBtn) {
        confirmBtn.classList.remove('has-text');
        confirmBtn.disabled = true;
    }
}

function onHideTopicInput() {
    var inputPanel = document.getElementById('sidebar-topic-input');
    var inputField = document.getElementById('topic-input-field');
    
    if (inputPanel) {
        inputPanel.style.display = 'none';
    }
    if (inputField) {
        inputField.value = '';
    }
}

function onTopicInputChange() {
    var inputField = document.getElementById('topic-input-field');
    var confirmBtn = document.getElementById('topic-input-confirm');
    
    if (!inputField || !confirmBtn) return;
    
    var hasText = inputField.value.trim().length > 0;
    
    if (hasText) {
        confirmBtn.classList.add('has-text');
        confirmBtn.disabled = false;
    } else {
        confirmBtn.classList.remove('has-text');
        confirmBtn.disabled = true;
    }
}

async function onConfirmTopic() {
    var inputField = document.getElementById('topic-input-field');
    var confirmBtn = document.getElementById('topic-input-confirm');
    var addBtn = document.getElementById('btn-add-topic');
    
    var topicName = inputField ? inputField.value.trim() : '';
    if (!topicName) {
        onHideTopicInput();
        return;
    }
    
    if (confirmBtn) {
        confirmBtn.disabled = true;
    }
    if (addBtn) {
        addBtn.disabled = true;
        addBtn.style.opacity = '0.5';
    }
    
    try {
        var createResult = await window.api.create_topic(topicName);
        if (!createResult || !createResult.success) {
            alert(createResult ? createResult.message : '创建主题失败');
            if (inputField) inputField.focus();
            return;
        }
        
        console.log('[Topic] 主题创建成功:', topicName);
        
        onHideTopicInput();
        
        await loadTopicTree();
        
        var batchResult = await window.api.batch_auto_assign_topics();
        if (batchResult && batchResult.success) {
            if (batchResult.pending && batchResult.pending.length > 0) {
                loadTopicPendingPanel(batchResult.pending);
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = '';
            }

            var msg = '主题「' + topicName + '」创建成功。扫描完成：';
            msg += '自动分配 ' + batchResult.auto_assigned + ' 个';
            msg += '，待确认 ' + batchResult.need_confirm + ' 个';
            console.log('[Topic] ' + msg);
        } else {
            console.error('[Topic] batch after create failed:', batchResult);
        }
    } catch (e) {
        console.error('[Topic] add topic error:', e);
    } finally {
        if (confirmBtn) {
            confirmBtn.disabled = false;
        }
        if (addBtn) {
            addBtn.disabled = false;
            addBtn.style.opacity = '1';
        }
    }
}

function setupTopicInputEvents() {
    var inputField = document.getElementById('topic-input-field');
    var cancelBtn = document.getElementById('topic-input-cancel');
    var confirmBtn = document.getElementById('topic-input-confirm');
    
    if (inputField) {
        inputField.addEventListener('input', onTopicInputChange);
        inputField.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                onConfirmTopic();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                onHideTopicInput();
            }
        });
    }
    
    if (cancelBtn) {
        cancelBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            onHideTopicInput();
        });
    }
    
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            onConfirmTopic();
        });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupTopicInputEvents);
} else {
    setupTopicInputEvents();
}

async function loadTopicView() {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;

    var result;
    try {
        result = await window.api.get_topic_tree();
        console.log('[Topic] API result:', result);
    } catch (e) {
        console.error('[Topic] loadTopicView error:', e);
        container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">' + escapeHtml(e.message || '未知错误') + '</span></div>';
        return;
    }

    await loadTopicTree();

    if (result && result.pending) {
        var topicNames = (result.topics || []).map(function(t) { return t.name; });
        loadTopicPendingPanel(result.pending, topicNames);
    }
}

function loadTopicPendingPanel(pending, topicNames) {
    topicNames = topicNames || [];
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return;

    if (!pending || pending.length === 0) {
        panel.innerHTML = '<div class="topic-pending-empty"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg><div>全部主题已确认</div></div>';
        return;
    }

    var html = '<div class="topic-pending-header">待确认主题 <span class="topic-pending-count">' + pending.length + '</span></div>';
    html += '<div class="topic-pending-list">';

    pending.forEach(function(p, i) {
        html += '<div class="topic-pending-card" draggable="true" data-file="' + escapeAttr(p.file) + '" data-index="' + i + '">';
        html += '<div class="topic-pending-filename">' + escapeHtml(p.title || p.file) + '</div>';
        html += '<div class="topic-pending-candidates">';
        (p.candidates || []).forEach(function(c) {
            html += '<button class="topic-candidate-btn" data-topic="' + escapeAttr(c) + '" data-file="' + escapeAttr(p.file) + '" onclick="onCandidateClick(this)">' + escapeHtml(c) + '</button>';
        });
        html += '</div>';
        if (topicNames.length > 0) {
            html += '<div class="topic-select-row">';
            html += '<select class="topic-select" data-file="' + escapeAttr(p.file) + '" onchange="onTopicSelectChange(this)">';
            html += '<option value="">-- 选择已有主题 --</option>';
            topicNames.forEach(function(name) {
                html += '<option value="' + escapeAttr(name) + '">' + escapeHtml(name) + '</option>';
            });
            html += '</select>';
            html += '</div>';
        }
        html += '<div class="topic-custom-row">';
        html += '<input type="text" class="topic-custom-input" placeholder="自定义主题..." data-file="' + escapeAttr(p.file) + '">';
        html += '<button class="topic-custom-btn" onclick="onConfirmBtnClick(this)">确定</button>';
        html += '</div>';
        html += '</div>';
    });

    html += '</div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.topic-custom-input').forEach(function(input) {
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                onInputEnter(this);
            }
        });
        input.addEventListener('input', function() {
            onInputChange(this);
        });
    });

    setupPendingCardDragDrop(panel);
}

var _pendingDragData = { filePath: null, cardEl: null };

function setupPendingCardDragDrop(panel) {
    panel.addEventListener('dragstart', function(e) {
        var card = e.target.closest('.topic-pending-card');
        if (!card) return;
        if (card.classList.contains('resolving') || card.classList.contains('resolved')) return;

        var filePath = card.getAttribute('data-file');
        if (!filePath) return;

        _pendingDragData.filePath = filePath;
        _pendingDragData.cardEl = card;
        card.classList.add('dragging');

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', filePath);
    });

    panel.addEventListener('dragend', function(e) {
        var card = e.target.closest('.topic-pending-card');
        if (card) card.classList.remove('dragging');
        _pendingDragData.filePath = null;
        _pendingDragData.cardEl = null;
    });
}

function onCandidateClick(btnEl) {
    var card = btnEl.closest('.topic-pending-card');
    if (!card) return;

    var btns = card.querySelectorAll('.topic-candidate-btn');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
    btnEl.classList.add('topic-candidate-selected');

    var input = card.querySelector('.topic-custom-input');
    if (input) {
        input.value = '';
    }
}

function onInputChange(inputEl) {
    var card = inputEl.closest('.topic-pending-card');
    if (!card) return;
    var btns = card.querySelectorAll('.topic-candidate-btn.topic-candidate-selected');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
}

async function onTopicSelectChange(selectEl) {
    var topicName = selectEl.value;
    if (!topicName) return;

    var card = selectEl.closest('.topic-pending-card');
    var filePath = card ? card.getAttribute('data-file') : null;
    if (!filePath) return;

    selectEl.disabled = true;
    card.classList.add('resolving');

    try {
        var result = await window.api.resolve_topic(filePath, topicName);
        if (result && result.success) {
            card.classList.remove('resolving');
            card.classList.add('resolved');
            animateCardOut(card);
        } else {
            card.classList.remove('resolving');
            selectEl.disabled = false;
            selectEl.value = '';
            alert('确认主题失败：' + (result ? result.message : '未知错误'));
        }
    } catch (err) {
        card.classList.remove('resolving');
        selectEl.disabled = false;
        selectEl.value = '';
        console.error('[Topic] select resolve error:', err);
        alert('确认主题失败：' + (err.message || '发生错误'));
    }
}

function onInputEnter(inputEl) {
    var card = inputEl.closest('.topic-pending-card');
    if (!card) return;
    doConfirmTopic(card);
}

function onConfirmBtnClick(btnEl) {
    var card = btnEl.closest('.topic-pending-card');
    if (!card) return;
    doConfirmTopic(card);
}

function doConfirmTopic(cardEl) {
    if (cardEl.classList.contains('resolving')) return;

    var file = cardEl.getAttribute('data-file');
    if (!file) return;

    var input = cardEl.querySelector('.topic-custom-input');
    var custom = (input && input.value) ? input.value.trim() : '';

    var selectedBtn = cardEl.querySelector('.topic-candidate-btn.topic-candidate-selected');
    var selectedTopic = selectedBtn ? selectedBtn.getAttribute('data-topic') || '' : '';

    var topic = custom || selectedTopic;
    if (!topic) return;

    var btns = cardEl.querySelectorAll('.topic-candidate-btn');
    var customBtn = cardEl.querySelector('.topic-custom-btn');

    btns.forEach(function(b) {
        if (b.getAttribute('data-topic') === topic) {
            b.classList.add('topic-candidate-selected');
        } else {
            b.classList.add('topic-candidate-disabled');
        }
    });

    if (input) input.disabled = true;
    if (customBtn) customBtn.disabled = true;
    cardEl.classList.add('resolving');

    window.api.resolve_topic(file, topic).then(function(result) {
        if (result && result.success) {
            cardEl.classList.add('resolved');
            animateCardOut(cardEl);
        } else {
            cardEl.classList.remove('resolving');
            btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
            if (input) input.disabled = false;
            if (customBtn) customBtn.disabled = false;
            console.error('[Topic] resolve failed:', result);
        }
    }).catch(function(e) {
        console.error('[Topic] resolve error:', e);
        cardEl.classList.remove('resolving');
        btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
        if (input) input.disabled = false;
        if (customBtn) customBtn.disabled = false;
    });
}

function animateCardOut(cardEl) {
    cardEl.style.transition = 'opacity 0.25s ease, transform 0.25s ease, margin 0.25s ease, padding 0.25s ease, min-height 0.25s ease';
    cardEl.style.opacity = '0';
    cardEl.style.transform = 'translateY(-8px) scale(0.98)';
    cardEl.style.marginTop = '0';
    cardEl.style.marginBottom = '0';
    cardEl.style.paddingTop = '0';
    cardEl.style.paddingBottom = '0';
    cardEl.style.minHeight = '0';
    cardEl.style.overflow = 'hidden';

    setTimeout(function() {
        var list = cardEl.parentElement;
        if (list && list.classList && list.classList.contains('topic-pending-list')) {
            cardEl.remove();
            var remaining = list.querySelectorAll('.topic-pending-card:not(.resolved)').length;
            if (remaining === 0) {
                loadTopicView();
            } else {
                loadTopicTree();
            }
        }
    }, 300);
}

function loadGraphView() {
    var container = document.getElementById('sidebar-graph');
    if (!container) return;
    container.innerHTML = '<div class="sidebar-view-empty"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2.5"></circle><circle cx="5" cy="19" r="2.5"></circle><circle cx="19" cy="19" r="2.5"></circle><line x1="12" y1="7.5" x2="5" y2="16.5"></line><line x1="12" y1="7.5" x2="19" y2="16.5"></line><line x1="7.5" y1="19" x2="16.5" y2="19"></line></svg><div>图谱视图</div><span style="font-size:11px;color:var(--text-muted)">开发中...</span></div>';
}

window.TreeModule = {
    loadTreeState: loadTreeState,
    saveTreeState: saveTreeState,
    toggleTreeFolder: toggleTreeFolder,
    renderFileTree: renderFileTree,
    loadFileTree: loadFileTree,
    selectFile: selectFile,
    switchSidebarView: switchSidebarView,
    updateWebAIStatus: function() {},
    updateConvAIStatus: function() {}
};

window.switchSidebarView = switchSidebarView;