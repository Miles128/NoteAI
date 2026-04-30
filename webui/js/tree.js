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

            var html = '<div class="tree-item ' + (isFolder ? 'folder' : 'file') + '" data-path="' + ep + '" data-name="' + en + '">';

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

    if (!isFolder) {
        items.push({ label: '打开', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>', action: function() { itemEl.click(); } });
        items.push({ label: '在 Finder 中显示', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>', action: function() { revealInFinder(path); } });
        items.push('divider');
        items.push({ label: '删除', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>', action: function() { deleteFile(path, name); } });
    } else {
        items.push({ label: '在 Finder 中显示', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>', action: function() { revealInFinder(path); } });
        items.push('divider');
        items.push({ label: '删除文件夹', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>', action: function() { deleteFile(path, name); } });
    }

    items.forEach(function(item) {
        if (item === 'divider') {
            var d = document.createElement('div');
            d.className = 'ctx-menu-divider';
            menu.appendChild(d);
        } else {
            var el = document.createElement('div');
            el.className = 'ctx-menu-item';
            el.innerHTML = item.icon + '<span>' + item.label + '</span>';
            el.addEventListener('click', function() {
                hideTreeContextMenu();
                item.action();
            });
            menu.appendChild(el);
        }
    });

    document.body.appendChild(menu);

    var x = e.clientX;
    var y = e.clientY;
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 4;
    if (y + mh > window.innerHeight) y = window.innerHeight - mh - 4;
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
                html += '<div class="sidebar-tag-group">';
                html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')">';
                html += '<svg class="sidebar-tag-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
                html += '<span class="sidebar-tag-name">' + escapeHtml(tag.name) + '</span>';
                html += '<span class="sidebar-tag-count">' + tag.count + '</span>';
                html += '</div>';
                html += '<div class="sidebar-tag-files">';
                tag.files.forEach(function(file) {
                    var fileName = file.split('/').pop();
                    html += '<div class="sidebar-tag-file tree-item" onclick="window.TreeModule.selectFile(\'' + escapeAttr(file) + '\', \'' + escapeAttr(fileName) + '\')">';
                    html += '<span class="tree-indent-unit"></span>';
                    html += '<span class="tree-name">' + escapeHtml(fileName) + '</span>';
                    html += '</div>';
                });
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;
        }

        var actionBar = document.createElement('div');
        actionBar.className = 'sidebar-tags-action';
        actionBar.innerHTML = '<button class="sidebar-tags-action-btn" onclick="doAutoTag()">自动匹配标签</button><button class="sidebar-tags-action-btn" onclick="doSaveTagsMd()">保存 tags.md</button>';
        container.appendChild(actionBar);
    } catch (e) {
        container.innerHTML = '<div class="sidebar-view-empty">加载标签失败</div>';
    }
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

async function loadTopicView() {
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
            html += '<div class="sidebar-tag-group">';
            html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')">';
            html += '<svg class="sidebar-tag-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
            html += '<span class="sidebar-tag-name">' + escapeHtml(topic.name) + '</span>';
            html += '<span class="sidebar-tag-count">' + topic.files.length + '</span>';
            html += '</div>';
            html += '<div class="sidebar-tag-files">';
            topic.files.forEach(function(f) {
                var display = f.title || '未命名';
                var path = f.path || '';
                if (path) {
                    html += '<div class="sidebar-tag-file tree-item" onclick="window.TreeModule.selectFile(\'' + escapeAttr(path) + '\', \'' + escapeAttr(display) + '\')">';
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

        container.innerHTML = html;

        loadTopicPendingPanel(result.pending || []);
    } catch (e) {
        console.error('[Topic] loadTopicView error:', e);
        container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size:11px;color:var(--text-muted)">' + escapeHtml(e.message || '未知错误') + '</span></div>';
    }
}

function loadTopicPendingPanel(pending) {
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return;

    if (!pending || pending.length === 0) {
        panel.innerHTML = '<div class="topic-pending-empty"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg><div>全部主题已确认</div></div>';
        return;
    }

    var html = '<div class="topic-pending-header">待确认主题 <span class="topic-pending-count">' + pending.length + '</span></div>';
    html += '<div class="topic-pending-list">';

    pending.forEach(function(p, i) {
        html += '<div class="topic-pending-card" data-file="' + escapeAttr(p.file) + '" data-index="' + i + '">';
        html += '<div class="topic-pending-filename">' + escapeHtml(p.title || p.file) + '</div>';
        html += '<div class="topic-pending-candidates">';
        (p.candidates || []).forEach(function(c) {
            html += '<button class="topic-candidate-btn" data-topic="' + escapeAttr(c) + '" data-file="' + escapeAttr(p.file) + '" onclick="onCandidateClick(this)">' + escapeHtml(c) + '</button>';
        });
        html += '</div>';
        html += '<div class="topic-custom-row">';
        html += '<input type="text" class="topic-custom-input" placeholder="自定义主题..." data-file="' + escapeAttr(p.file) + '" onkeydown="if(event.key===\'Enter\')onCustomEnter(this)">';
        html += '<button class="topic-custom-btn" onclick="onCustomBtnClick(this)">确定</button>';
        html += '</div>';
        html += '</div>';
    });

    html += '</div>';
    panel.innerHTML = html;
}

function onCandidateClick(btnEl) {
    var card = btnEl.closest('.topic-pending-card');
    if (!card) return;

    var file = btnEl.getAttribute('data-file');
    var topic = btnEl.getAttribute('data-topic');
    if (!file || !topic) return;

    doResolveTopic(card, file, topic);
}

function onCustomEnter(inputEl) {
    var val = (inputEl.value || '').trim();
    if (!val) return;
    var card = inputEl.closest('.topic-pending-card');
    var file = inputEl.getAttribute('data-file');
    if (!card || !file) return;
    doResolveTopic(card, file, val);
}

function onCustomBtnClick(btnEl) {
    var row = btnEl.closest('.topic-custom-row');
    if (!row) return;
    var input = row.querySelector('.topic-custom-input');
    if (!input) return;
    onCustomEnter(input);
}

async function doResolveTopic(cardEl, filePath, topic) {
    if (cardEl.classList.contains('resolving')) return;

    var btns = cardEl.querySelectorAll('.topic-candidate-btn');
    var customInput = cardEl.querySelector('.topic-custom-input');
    var customBtn = cardEl.querySelector('.topic-custom-btn');

    btns.forEach(function(b) {
        if (b.getAttribute('data-topic') === topic) {
            b.classList.add('topic-candidate-selected');
        } else {
            b.classList.add('topic-candidate-disabled');
        }
    });

    if (customInput) {
        customInput.disabled = true;
    }
    if (customBtn) {
        customBtn.disabled = true;
    }

    cardEl.classList.add('resolving');

    try {
        var result = await window.api.resolve_topic(filePath, topic);
        if (result && result.success) {
            cardEl.classList.add('resolved');
            animateCardOut(cardEl);
        } else {
            cardEl.classList.remove('resolving');
            btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
            if (customInput) customInput.disabled = false;
            if (customBtn) customBtn.disabled = false;
            console.error('[Topic] resolve failed:', result);
        }
    } catch (e) {
        console.error('[Topic] resolve error:', e);
        cardEl.classList.remove('resolving');
        btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
        if (customInput) customInput.disabled = false;
        if (customBtn) customBtn.disabled = false;
    }
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