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
    if (!e.target.closest('.tree-item') && !e.target.closest('.sidebar-tag-row') && !e.target.closest('.sidebar-tag-file')) hideTreeContextMenu();
});

var _lastFileTreeData = null;

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
        var dataStr = JSON.stringify(treeData);
        if (dataStr === _lastFileTreeData) return;
        _lastFileTreeData = dataStr;

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
    if (_currentSidebarView === 'graph') {
        loadLinksData();
    }
    if (_currentSidebarView === 'relation') {
        loadRelationGraphData();
    }
}

var _currentSidebarView = 'tree';

function switchSidebarView(view) {
    _currentSidebarView = view;

    var fileTree = document.getElementById('file-tree');
    var sidebarTags = document.getElementById('sidebar-tags');
    var sidebarTopic = document.getElementById('sidebar-topic');
    var sidebarGraph = document.getElementById('sidebar-graph');
    var sidebarRelation = document.getElementById('sidebar-relation');
    var sidebar = document.querySelector('.sidebar-left');
    var resizer = document.getElementById('sidebar-resizer');

    if (sidebar) sidebar.style.display = 'flex';
    if (resizer) resizer.style.display = '';

    if (fileTree) fileTree.style.display = view === 'tree' ? '' : 'none';
    if (sidebarTags) sidebarTags.style.display = view === 'tags' ? '' : 'none';
    if (sidebarTopic) sidebarTopic.style.display = view === 'topic' ? '' : 'none';
    if (sidebarGraph) sidebarGraph.style.display = view === 'graph' ? '' : 'none';
    if (sidebarRelation) sidebarRelation.style.display = view === 'relation' ? '' : 'none';

    document.querySelectorAll('.sidebar-view-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.sidebar === view);
    });

    var footerTopic = document.getElementById('sidebar-footer-topic');
    var footerGraph = document.getElementById('sidebar-footer-graph');
    var footerRelation = document.getElementById('sidebar-footer-relation');
    if (footerTopic) footerTopic.style.display = view === 'topic' ? '' : 'none';
    if (footerGraph) footerGraph.style.display = view === 'graph' ? '' : 'none';
    if (footerRelation) footerRelation.style.display = view === 'relation' ? '' : 'none';

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
    if (view === 'relation') loadRelationGraphView();
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function Path_stem(p) {
    if (!p) return p;
    var parts = p.replace(/\\/g, '/').split('/');
    var name = parts[parts.length - 1];
    var dotIdx = name.lastIndexOf('.');
    return dotIdx > 0 ? name.substring(0, dotIdx) : name;
}

var _linkFilter = 'all';
var _graphFilter = 'all';
var _graphData = null;
var _graphAnimId = null;

function loadGraphView() {
    var container = document.getElementById('sidebar-graph');
    if (!container) return;

    var html = '<div class="link-view">';
    html += '<div class="link-view-header">';
    html += '<span class="link-view-title">双向链接</span>';
    html += '</div>';

    html += '<div class="link-progress" id="link-progress" style="display:none;">';
    html += '<div class="link-progress-bar"><div class="link-progress-fill" id="link-progress-fill"></div></div>';
    html += '<div class="link-progress-text" id="link-progress-text"></div>';
    html += '</div>';

    html += '<div class="link-filter-bar" id="link-filter-bar" style="display:none;">';
    html += '<button class="link-filter-btn active" data-filter="all" onclick="onLinkFilter(\'all\')">全部</button>';
    html += '<button class="link-filter-btn" data-filter="pending" onclick="onLinkFilter(\'pending\')">待确认</button>';
    html += '<button class="link-filter-btn" data-filter="confirmed" onclick="onLinkFilter(\'confirmed\')">已确认</button>';
    html += '<button class="link-confirm-all-btn" onclick="onConfirmAllLinks()" title="一键确认所有待确认链接">全部确认</button>';
    html += '</div>';

    html += '<div class="link-list" id="link-list"></div>';
    html += '<div class="link-empty" id="link-empty">点击「发现链接」让 AI 分析文章关联</div>';
    html += '</div>';

    container.innerHTML = html;
    loadLinksData();
}

async function loadLinksData() {
    var listEl = document.getElementById('link-list');
    var emptyEl = document.getElementById('link-empty');
    var filterBar = document.getElementById('link-filter-bar');
    if (!listEl) return;

    var result = await window.api.get_backlinks(selectedFilePath || '');
    if (!result || !result.success) {
        if (emptyEl) emptyEl.textContent = '无法加载链接数据';
        return;
    }

    var allLinks = result.links || [];
    if (allLinks.length === 0) {
        if (emptyEl) emptyEl.style.display = '';
        if (filterBar) filterBar.style.display = 'none';
        listEl.innerHTML = '';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (filterBar) filterBar.style.display = '';

    var filtered = allLinks;
    if (_linkFilter === 'pending') filtered = allLinks.filter(function(l) { return l.status === 'pending'; });
    else if (_linkFilter === 'confirmed') filtered = allLinks.filter(function(l) { return l.status === 'confirmed'; });

    if (filtered.length === 0 && allLinks.length > 0) {
        listEl.innerHTML = '<div class="link-empty-sub">没有匹配的链接</div>';
        return;
    }

    var html = '';
    for (var i = 0; i < filtered.length; i++) {
        var link = filtered[i];
        var dirClass = link.direction === 'incoming' ? 'link-incoming' : 'link-outgoing';
        var statusClass = link.status === 'confirmed' ? 'link-confirmed' : 'link-pending';
        var statusLabel = link.status === 'confirmed' ? '已确认' : '待确认';
        var fromPath = link.from || link.file || '';
        var toPath = link.to || link.other || '';
        var fromName = fromPath ? Path_stem(fromPath) : fromPath;
        var toName = toPath ? Path_stem(toPath) : toPath;
        var confirmCall = 'onConfirmLink(\'' + escapeHtml(fromPath) + '\',\'' + escapeHtml(toPath) + '\')';
        var rejectCall = 'onRejectLink(\'' + escapeHtml(fromPath) + '\',\'' + escapeHtml(toPath) + '\')';

        html += '<div class="link-card ' + dirClass + ' ' + statusClass + '">';
        html += '<div class="link-card-header">';
        html += '<span class="link-status-badge ' + statusClass + '">' + statusLabel + '</span>';
        if (link.status === 'pending') {
            html += '<div class="link-card-actions">';
            html += '<button class="link-action-btn link-confirm-btn" onclick="event.stopPropagation();' + confirmCall + '" title="确认">✓</button>';
            html += '<button class="link-action-btn link-reject-btn" onclick="event.stopPropagation();' + rejectCall + '" title="删除">✕</button>';
            html += '</div>';
        }
        html += '</div>';
        html += '<div class="link-card-relation">';
        html += '<span class="link-node link-from" onclick="openLinkedFile(\'' + escapeHtml(fromPath) + '\')">' + escapeHtml(fromName) + '</span>';
        html += '<span class="link-arrow ' + dirClass + '">→</span>';
        html += '<span class="link-node link-to" onclick="openLinkedFile(\'' + escapeHtml(toPath) + '\')">' + escapeHtml(toName) + '</span>';
        html += '</div>';
        if (link.reason) {
            html += '<div class="link-card-reason">' + escapeHtml(link.reason) + '</div>';
        }
        html += '</div>';
    }

    listEl.innerHTML = html;
}

var _linkDiscoveryUnlisten = null;

async function onDiscoverLinks() {
    var btn = document.getElementById('btn-discover-links');
    var btnSpan = btn ? btn.querySelector('span') : null;
    var progressEl = document.getElementById('link-progress');
    var progressFill = document.getElementById('link-progress-fill');
    var progressText = document.getElementById('link-progress-text');
    var emptyEl = document.getElementById('link-empty');

    try {
        var apiCfg = await window.api.get_api_config();
        if (!apiCfg || !apiCfg.api_key) {
            alert('请先在设置中配置 API Key');
            return;
        }
    } catch (e) {
        alert('无法获取 API 配置: ' + (e.message || e));
        return;
    }

    if (btn) { btn.disabled = true; if (btnSpan) btnSpan.textContent = '检查中...'; }
    if (progressEl) progressEl.style.display = '';
    if (progressFill) progressFill.style.width = '5%';
    if (progressText) progressText.textContent = '正在测试 API 连接...';
    if (emptyEl) emptyEl.style.display = 'none';

    try {
        var connResult = await window.api.invoke('test_api_connection', {});
        if (!connResult || !connResult.success) {
            if (progressText) progressText.textContent = 'API 连接失败: ' + ((connResult && connResult.message) || '未知错误');
            if (btn) { btn.disabled = false; if (btnSpan) btnSpan.textContent = '发现链接'; }
            return;
        }
    } catch (e) {
        if (progressText) progressText.textContent = 'API 连接测试出错: ' + (e.message || e);
        if (btn) { btn.disabled = false; if (btnSpan) btnSpan.textContent = '发现链接'; }
        return;
    }

    if (btnSpan) btnSpan.textContent = '分析中...';
    if (progressFill) progressFill.style.width = '10%';
    if (progressText) progressText.textContent = '正在读取文件并构建候选对...';

    if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
    if (_isTauri) {
        var eventAPI = window.__TAURI__ && (window.__TAURI__.event || (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event));
        if (eventAPI) {
            try {
                _linkDiscoveryUnlisten = await eventAPI.listen('python-event', function(event) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'progress' && data.element_id === 'link-discovery-progress') {
                        if (progressText) progressText.textContent = data.message || '';
                        if (progressFill && data.progress !== undefined) {
                            var p = Math.min(10 + data.progress * 0.85, 95);
                            progressFill.style.width = p + '%';
                        }
                    }

                    if (data.type === 'link_discovery_complete') {
                        if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
                        var result = data.data || {};
                        if (progressFill) progressFill.style.width = '100%';
                        if (progressText) {
                            if (result.success) {
                                var msg = '完成：扫描 ' + (result.files_scanned || '?') + ' 个文件';
                                if (result.new_links > 0) {
                                    msg += '，发现 ' + result.new_links + ' 个新关联';
                                } else {
                                    msg += '，未发现新关联';
                                }
                                progressText.textContent = msg;
                            } else {
                                progressText.textContent = result.message || '发现失败';
                            }
                        }
                        if (btn) { btn.disabled = false; if (btnSpan) btnSpan.textContent = '发现链接'; }
                        setTimeout(function() {
                            if (progressEl) progressEl.style.display = 'none';
                            loadGraphView();
                        }, 2000);
                    }
                });
            } catch (e) {
                console.error('[Link] Failed to listen for events:', e);
            }
        }
    }

    try {
        var startResult = await window.api.discover_links();
        if (!startResult || !startResult.success) {
            if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
            if (progressText) progressText.textContent = (startResult && startResult.message) || '启动失败';
            if (btn) { btn.disabled = false; if (btnSpan) btnSpan.textContent = '发现链接'; }
        }
    } catch (e) {
        if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
        if (progressText) progressText.textContent = '错误: ' + (e.message || e);
        if (btn) { btn.disabled = false; if (btnSpan) btnSpan.textContent = '发现链接'; }
    }
}

async function onConfirmLink(fromPath, toPath) {
    var result = await window.api.confirm_link(fromPath, toPath);
    if (result.success) { loadLinksData(); } else { alert('确认失败: ' + (result.message || '')); }
}

async function onRejectLink(fromPath, toPath) {
    var result = await window.api.reject_link(fromPath, toPath);
    if (result.success) { loadLinksData(); } else { alert('删除失败: ' + (result.message || '')); }
}

async function onConfirmAllLinks() {
    var result = await window.api.confirm_all_links();
    if (result.success) { loadLinksData(); } else { alert('操作失败: ' + (result.message || '')); }
}

function onLinkFilter(filter) {
    _linkFilter = filter;
    document.querySelectorAll('.link-filter-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    loadLinksData();
}

function openLinkedFile(filePath) {
    if (window.TreeModule && window.TreeModule.selectFile) {
        window.TreeModule.selectFile(filePath);
    }
}

function loadRelationGraphView() {
    var container = document.getElementById('sidebar-relation');
    if (!container) return;

    var html = '<div class="graph-view">';
    html += '<div class="graph-filter-bar">';
    html += '<button class="graph-filter-btn active" data-gfilter="all" onclick="onGraphFilter(\'all\')">全部</button>';
    html += '<button class="graph-filter-btn" data-gfilter="topic" onclick="onGraphFilter(\'topic\')">主题</button>';
    html += '<button class="graph-filter-btn" data-gfilter="tag" onclick="onGraphFilter(\'tag\')">标签</button>';
    html += '<button class="graph-filter-btn" data-gfilter="link" onclick="onGraphFilter(\'link\')">链接</button>';
    html += '</div>';
    html += '<div class="graph-canvas-wrap"><canvas id="graph-canvas"></canvas></div>';
    html += '<div class="graph-legend">';
    html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#4A90D9"></span>文件</span>';
    html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#E8913A"></span>主题</span>';
    html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#50B87F"></span>标签</span>';
    html += '</div>';
    html += '<div class="graph-tooltip" id="graph-tooltip" style="display:none;"></div>';
    html += '</div>';

    container.innerHTML = html;
    loadRelationGraphData();
}

async function loadRelationGraphData() {
    var result = await window.api.get_relation_graph();
    if (!result || !result.success) return;
    _graphData = result;
    requestAnimationFrame(function() {
        setTimeout(initGraphSimulation, 50);
    });
}

function onGraphFilter(filter) {
    _graphFilter = filter;
    document.querySelectorAll('.graph-filter-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.gfilter === filter);
    });
    if (_graphData) initGraphSimulation();
}

function initGraphSimulation() {
    if (_graphAnimId) { cancelAnimationFrame(_graphAnimId); _graphAnimId = null; }

    var canvas = document.getElementById('graph-canvas');
    if (!canvas) return;
    var wrap = canvas.parentElement;
    if (!wrap) return;
    var dpr = window.devicePixelRatio || 1;
    var w = wrap.clientWidth;
    var h = wrap.clientHeight;
    if (w < 10 || h < 10) {
        setTimeout(initGraphSimulation, 100);
        return;
    }
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    var nodes = [];
    var edges = [];
    var nodeMap = {};

    var filteredEdges = _graphData.edges;
    if (_graphFilter !== 'all') {
        filteredEdges = filteredEdges.filter(function(e) { return e.type === _graphFilter; });
    }

    var usedNodeIds = new Set();
    filteredEdges.forEach(function(e) { usedNodeIds.add(e.source); usedNodeIds.add(e.target); });

    _graphData.nodes.forEach(function(n) {
        if (usedNodeIds.has(n.id)) {
            var node = {
                id: n.id, label: n.label, nodeType: n.nodeType,
                x: w / 2 + (Math.random() - 0.5) * w * 0.6,
                y: h / 2 + (Math.random() - 0.5) * h * 0.6,
                vx: 0, vy: 0
            };
            nodes.push(node);
            nodeMap[n.id] = node;
        }
    });

    filteredEdges.forEach(function(e) {
        if (nodeMap[e.source] && nodeMap[e.target]) {
            edges.push({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type });
        }
    });

    var alpha = 1;
    var alphaDecay = 0.02;
    var alphaMin = 0.001;

    function tick() {
        if (alpha < alphaMin) { alpha = alphaMin; }
        var k = alpha * 0.3;
        for (var i = 0; i < edges.length; i++) {
            var e = edges[i];
            var dx = e.target.x - e.source.x;
            var dy = e.target.y - e.source.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
            var force = (dist - 60) * k * 0.05;
            var fx = dx / dist * force;
            var fy = dy / dist * force;
            e.source.vx += fx; e.source.vy += fy;
            e.target.vx -= fx; e.target.vy -= fy;
        }
        var repulse = alpha * 80;
        for (var i = 0; i < nodes.length; i++) {
            for (var j = i + 1; j < nodes.length; j++) {
                var dx = nodes[j].x - nodes[i].x;
                var dy = nodes[j].y - nodes[i].y;
                var dist2 = dx * dx + dy * dy || 1;
                var f = repulse / dist2;
                var dist = Math.sqrt(dist2);
                nodes[i].vx -= dx / dist * f; nodes[i].vy -= dy / dist * f;
                nodes[j].vx += dx / dist * f; nodes[j].vy += dy / dist * f;
            }
        }
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            n.vx += (w / 2 - n.x) * 0.001;
            n.vy += (h / 2 - n.y) * 0.001;
            n.vx *= 0.6; n.vy *= 0.6;
            n.x += n.vx; n.y += n.vy;
            if (n.x < 20) n.x = 20; if (n.x > w - 20) n.x = w - 20;
            if (n.y < 20) n.y = 20; if (n.y > h - 20) n.y = h - 20;
        }
        alpha *= (1 - alphaDecay);
    }

    var edgeColors = { topic: 'rgba(232,145,58,0.4)', tag: 'rgba(80,184,127,0.4)', link: 'rgba(74,144,217,0.4)' };
    var nodeColors = { file: '#4A90D9', topic: '#E8913A', tag: '#50B87F' };

    function draw() {
        ctx.clearRect(0, 0, w, h);
        for (var i = 0; i < edges.length; i++) {
            var e = edges[i];
            ctx.beginPath();
            ctx.moveTo(e.source.x, e.source.y);
            ctx.lineTo(e.target.x, e.target.y);
            ctx.strokeStyle = edgeColors[e.type] || 'rgba(150,150,150,0.3)';
            ctx.lineWidth = 1;
            ctx.stroke();
        }
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var r = n.nodeType === 'file' ? 4 : 6;
            ctx.beginPath();
            ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
            ctx.fillStyle = nodeColors[n.nodeType] || '#999';
            ctx.fill();
            if (n.nodeType !== 'file' || nodes.length < 40) {
                ctx.fillStyle = '#888';
                ctx.font = '9px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(n.label, n.x, n.y + r + 10);
            }
        }
    }

    var _hoveredNode = null;
    var tooltip = document.getElementById('graph-tooltip');

    canvas.onmousemove = function(ev) {
        var rect = canvas.getBoundingClientRect();
        var mx = ev.clientX - rect.left;
        var my = ev.clientY - rect.top;
        _hoveredNode = null;
        for (var i = nodes.length - 1; i >= 0; i--) {
            var n = nodes[i];
            var dx = mx - n.x;
            var dy = my - n.y;
            if (dx * dx + dy * dy < 100) { _hoveredNode = n; break; }
        }
        if (_hoveredNode && tooltip) {
            tooltip.style.display = 'block';
            tooltip.style.left = (_hoveredNode.x + 12) + 'px';
            tooltip.style.top = (_hoveredNode.y - 8) + 'px';
            var typeLabel = { file: '文件', topic: '主题', tag: '标签' }[_hoveredNode.nodeType] || '';
            tooltip.textContent = typeLabel + ': ' + _hoveredNode.label;
        } else if (tooltip) {
            tooltip.style.display = 'none';
        }
    };

    canvas.onclick = function() {
        if (_hoveredNode && _hoveredNode.nodeType === 'file') {
            selectFile(_hoveredNode.id, _hoveredNode.label + '.md');
        }
    };

    canvas.onmouseleave = function() {
        if (tooltip) tooltip.style.display = 'none';
        _hoveredNode = null;
    };

    function loop() {
        tick();
        draw();
        if (alpha > alphaMin * 1.1) {
            _graphAnimId = requestAnimationFrame(loop);
        } else {
            _graphAnimId = null;
        }
    }
    loop();
}

function escapeAttr(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

var _lastTagsData = null;

async function loadTagsView(silent) {
    var container = document.getElementById('sidebar-tags');
    if (!container) return;
    if (!silent) {
        container.innerHTML = '<div class="sidebar-view-loading">加载标签...</div>';
    }

    try {
        await window.api.ensure_tags_md();
        var result = await window.api.get_all_tags();

        var dataStr = JSON.stringify(result);
        if (silent && dataStr === _lastTagsData) return;
        _lastTagsData = dataStr;

        if (!result || !result.tags || result.tags.length === 0) {
            container.innerHTML = '<div class="sidebar-view-empty">暂无标签<br><span style="font-size:11px;color:var(--text-muted)">点击下方按钮自动匹配标签</span></div>';
        } else {
            var expandedTags = {};
            container.querySelectorAll('.sidebar-tag-group.expanded').forEach(function(el) {
                var name = el.getAttribute('data-tag-name');
                if (name) expandedTags[name] = true;
            });

            var html = '<div class="sidebar-tags-list">';
            result.tags.forEach(function(tag) {
                var isExpanded = expandedTags[tag.name] ? ' expanded' : '';
                html += '<div class="sidebar-tag-group' + isExpanded + '" data-tag-name="' + escapeAttr(tag.name) + '">';
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
        var rowEl = e.target.closest('.sidebar-tag-row');

        if (fileEl) {
            e.preventDefault();
            e.stopPropagation();
            showTagsContextMenu(e, fileEl);
        } else if (rowEl) {
            e.preventDefault();
            e.stopPropagation();
            showTagRowContextMenu(e, rowEl);
        }
    });
}

function showTagRowContextMenu(e, rowEl) {
    hideTreeContextMenu();

    var tagName = rowEl.getAttribute('data-tag-name');
    var tagNameEl = rowEl.querySelector('.sidebar-tag-name');
    if (!tagName) return;

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({
        label: '更改名称',
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>',
        action: function() {
            if (tagNameEl) {
                startTagRename(tagNameEl, tagName);
            }
        }
    });

    items.push({
        label: '删除标签',
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>',
        action: function() {
            onDeleteTag(tagName);
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

function startTagRename(tagNameEl, oldTagName) {
    var parentRow = tagNameEl.closest('.sidebar-tag-row');
    if (!parentRow) return;

    var originalDisplay = tagNameEl.style.display;

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'topic-rename-input';
    input.value = oldTagName;
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

        if (cancel || !newName || newName === oldTagName) {
            return;
        }

        window.api.rename_tag(oldTagName, newName).then(function(result) {
            if (result && result.success) {
                loadTagsView(true);
            } else {
                alert('重命名标签失败：' + (result && result.message ? result.message : '未知错误'));
            }
        }).catch(function(e) {
            console.error('[Tag] rename error:', e);
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
}

function onDeleteTag(tagName) {
    var confirmed = confirm('确定要删除标签「' + tagName + '」吗？\n\n该标签将从所有文件的 YAML tags 中移除，同时更新 WIKI.md。');
    if (!confirmed) return;

    window.api.delete_tag(tagName).then(function(result) {
        if (result && result.success) {
            loadTagsView(true);
        } else {
            alert('删除标签失败：' + (result && result.message ? result.message : '未知错误'));
        }
    }).catch(function(e) {
        console.error('[Tag] delete error:', e);
        alert('删除标签出错');
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

var _lastTopicData = null;

async function loadTopicTree(silent) {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;
    if (!silent) {
        container.innerHTML = '<div class="sidebar-view-loading">加载主题...</div>';
    }

    try {
        var result = await window.api.get_topic_tree();

        if (!result || typeof result !== 'object') {
            container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">API 返回异常</span></div>';
            return;
        }

        var dataStr = JSON.stringify(result);
        if (silent && dataStr === _lastTopicData) return;
        _lastTopicData = dataStr;

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

        var expandedTopics = {};
        container.querySelectorAll('.sidebar-tag-group.expanded').forEach(function(el) {
            var name = el.getAttribute('data-topic-name');
            if (name) expandedTopics[name] = true;
        });

        var html = '<div class="sidebar-tags-list">';
        result.topics.forEach(function(topic) {
            var isExpanded = expandedTopics[topic.name] ? ' expanded' : '';
            html += '<div class="sidebar-tag-group' + isExpanded + '" data-topic-name="' + escapeAttr(topic.name) + '">';
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

    items.push({ 
        label: '删除主题', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>', 
        action: function() { 
            onDeleteTopic(topicName);
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

function onDeleteTopic(topicName) {
    var confirmed = confirm('确定要删除主题「' + topicName + '」吗？\n\n该主题下的文件将从 WIKI.md 中移除，文件的 topic 标签也会被删除，之后会重新尝试自动匹配主题。');
    if (!confirmed) return;

    window.api.delete_topic(topicName).then(function(result) {
        if (result && result.success) {
            loadTopicTree();
            if (result.reassigned > 0) {
                console.log('[Topic] Reassigned ' + result.reassigned + ' files');
            }
            if (result.pending > 0) {
                console.log('[Topic] ' + result.pending + ' files need manual assignment');
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = '';
            }
        } else {
            alert('删除主题失败：' + (result && result.message ? result.message : '未知错误'));
        }
    }).catch(function(e) {
        console.error('[Topic] delete error:', e);
        alert('删除主题出错');
    });
}

async function onBatchAutoAssignTopics() {
    var btn = document.getElementById('btn-auto-topic');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }

    try {
        console.log('[Topic] Step 1: Sync WIKI.md with file YAML topics...');
        var syncResult = await window.api.sync_wiki_with_files();
        console.log('[Topic] Sync result:', syncResult);

        if (syncResult && syncResult.success) {
            var syncMsg = '同步完成：移动 ' + syncResult.moved +
                '，新增 ' + syncResult.added +
                '，移除 ' + syncResult.removed +
                '，删除空主题 ' + syncResult.deleted_topics;
            console.log('[Topic] ' + syncMsg);
        }

        await loadTopicTree();

        console.log('[Topic] Step 2: Auto assign topics for files without topic...');
        var result = await window.api.batch_auto_assign_topics();
        if (result && result.success) {
            await loadTopicTree();

            if (result.pending && result.pending.length > 0) {
                var topicNames = [];
                document.querySelectorAll('#sidebar-topic .sidebar-tag-group').forEach(function(el) {
                    var n = el.getAttribute('data-topic-name');
                    if (n) topicNames.push(n);
                });
                loadTopicPendingPanel(result.pending, topicNames);
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
                var topicNames2 = [];
                document.querySelectorAll('#sidebar-topic .sidebar-tag-group').forEach(function(el) {
                    var n = el.getAttribute('data-topic-name');
                    if (n) topicNames2.push(n);
                });
                loadTopicPendingPanel(batchResult.pending, topicNames2);
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
window.onDiscoverLinks = onDiscoverLinks;
window.onConfirmLink = onConfirmLink;
window.onRejectLink = onRejectLink;
window.onConfirmAllLinks = onConfirmAllLinks;
window.onLinkFilter = onLinkFilter;
window.openLinkedFile = openLinkedFile;