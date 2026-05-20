(function() { 'use strict';

var _lastTopicData = null;
var _aiSuggestions = [];
var _existingTopics = [];
var _pendingDragData = { filePath: null, cardEl: null };

function _buildTopicTree(topics) {
    var root = { children: {}, files: [], name: '', label: '' };
    topics.forEach(function(topic) {
        var parts = topic.name.split(' > ');
        var node = root;
        for (var i = 0; i < parts.length; i++) {
            var part = parts[i];
            if (!node.children[part]) {
                node.children[part] = { children: {}, files: [], name: parts.slice(0, i + 1).join(' > '), label: part };
            }
            node = node.children[part];
        }
        if (topic.files && topic.files.length > 0) {
            node.files = topic.files;
        }
    });
    return root;
}

function _renderTopicTree(node, expandedTopics, depth) {
    depth = depth || 0;
    var html = '';
    var keys = Object.keys(node.children).sort(function(a, b) {
        return a.toLowerCase().localeCompare(b.toLowerCase());
    });
    keys.forEach(function(key) {
        var child = node.children[key];
        var hasChildren = Object.keys(child.children).length > 0;
        var hasFiles = child.files.length > 0;
        var isExpanded = expandedTopics[child.name] ? ' expanded' : '';
        var indent = depth * 16;
        var totalFiles = _countAllFiles(child);

        html += '<div class="sidebar-tag-group' + isExpanded + '" data-topic-name="' + escapeAttr(child.name) + '">';
        html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')" data-topic-name="' + escapeAttr(child.name) + '" style="padding-left:' + (8 + indent) + 'px">';
        if (hasChildren || hasFiles) {
            html += '<span class="sidebar-tag-toggle">' + window.Icons.get('chevronDown') + '</span>';
        } else {
            html += '<span class="sidebar-tag-toggle" style="visibility:hidden">' + window.Icons.get('chevronDown') + '</span>';
        }
        html += '<span class="sidebar-tag-name" data-topic-name="' + escapeAttr(child.name) + '">' + escapeHtml(child.label) + '</span>';
        if (totalFiles > 0) {
            html += '<span class="sidebar-tag-count">' + totalFiles + '</span>';
        }
        html += '</div>';

        if (hasChildren) {
            html += '<div class="sidebar-tag-children">';
            html += _renderTopicTree(child, expandedTopics, depth + 1);
            html += '</div>';
        }

        if (hasFiles) {
            html += '<div class="sidebar-tag-files">';
            child.files.forEach(function(f) {
                var display = f.title || '未命名';
                var path = f.path || '';
                if (path) {
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + escapeAttr(path) + '" onclick="window.TreeModule.selectFile(\'' + escapeAttr(path) + '\', \'' + escapeAttr(display) + '\')" style="padding-left:' + (24 + indent) + 'px">';
                } else {
                    html += '<div class="sidebar-tag-file tree-item" style="padding-left:' + (24 + indent) + 'px">';
                }
                html += '<span class="tree-name">' + escapeHtml(display) + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        html += '</div>';
    });
    return html;
}

function _countAllFiles(node) {
    var count = node.files.length;
    var keys = Object.keys(node.children);
    for (var i = 0; i < keys.length; i++) {
        count += _countAllFiles(node.children[keys[i]]);
    }
    return count;
}

async function loadTopicTree(silent) {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;
    if (!silent) {
        container.innerHTML = '<div class="sidebar-view-loading">加载主题...</div>';
    }

    try {
        var result = await window.api.getTopicTree();

        if (!result || typeof result !== 'object') {
            container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size: 12px;color:var(--text-muted)">API 返回异常</span></div>';
            return;
        }

        var dataStr = JSON.stringify(result);
        if (silent && dataStr === _lastTopicData) return;
        _lastTopicData = dataStr;
        window.AppState.lastTopicData = dataStr;

        if (result.success === false) {
            container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size: 12px;color:var(--text-muted)">' + escapeHtml(result.message || '后端错误') + '</span></div>';
            return;
        }

        var topics = result.topics || [];
        var hasTopics = topics.length > 0;

        if (!hasTopics) {
            container.innerHTML = '<div class="sidebar-view-empty">暂无已确认主题</div>';
            return;
        }

        var expandedTopics = {};
        container.querySelectorAll('.sidebar-tag-group.expanded').forEach(function(el) {
            var name = el.getAttribute('data-topic-name');
            if (name) expandedTopics[name] = true;
        });

        var treeData = _buildTopicTree(result.topics);

        var html = '<div class="sidebar-tags-list">';
        html += _renderTopicTree(treeData, expandedTopics);
        html += '</div>';

        html += '<div class="topic-context-menu" id="topic-context-menu" style="display:none;">';
        html += '<div class="topic-menu-item" data-action="rename">重命名</div>';
        html += '</div>';

        container.innerHTML = html;

        setupTopicDragDrop(container);
        setupTopicContextMenu(container);
        window.updateSidebarStats();
    } catch (e) {
        console.error('[Topic] loadTopicTree error:', e);
        container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size: 12px;color:var(--text-muted)">' + escapeHtml(e.message || '未知错误') + '</span></div>';
    }
}

function setupTopicDragDrop(container) {
    if (container._topicDragDropReady) return;
    container._topicDragDropReady = true;

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

        if (pendingCard) {
            if (rowEl) {
                rowEl.classList.add('drag-over');
            } else if (groupEl) {
                var row = groupEl.querySelector('.sidebar-tag-row');
                if (row) row.classList.add('drag-over');
            }
            return;
        }

        if (dragData.srcTopic === targetTopic) return;

        if (rowEl) {
            rowEl.classList.add('drag-over');
        } else if (groupEl) {
            var row2 = groupEl.querySelector('.sidebar-tag-row');
            if (row2) row2.classList.add('drag-over');
        }
    });

    container.addEventListener('dragleave', function(e) {
        var rowEl = e.target.closest('.sidebar-tag-row');
        if (rowEl) rowEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e) {
        e.preventDefault();
        e.stopPropagation();

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
                var result = await window.api.resolveTopic(pendingFile, targetTopic);
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
            var result2 = await window.api.moveFileToTopic(filePath, targetTopic2);
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
        icon: window.Icons.get('fileEdit'),
        action: function() {
            if (tagNameEl) {
                startTopicRename(tagNameEl, topicName);
            }
        }
    });

    items.push({
        label: '添加子主题',
        icon: window.Icons.get('plus'),
        action: function() {
            onAddSubTopic(topicName);
        }
    });

    items.push({
        label: '删除主题',
        icon: window.Icons.get('trash'),
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
        icon: window.Icons.get('folder'),
        action: function() { revealInFinder(path); }
    });

    items.push({
        label: '在新窗口打开',
        icon: window.Icons.get('folderOpen'),
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

        if (input._renameCleanup) input._renameCleanup();

        var newName = input.value.trim();
        input.remove();
        tagNameEl.style.display = originalDisplay || '';

        if (cancel || !newName || newName === oldTopicName) {
            return;
        }

        console.log('[Topic] Rename:', oldTopicName, '->', newName);

        window.api.renameTopic(oldTopicName, newName).then(function(result) {
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
    input._renameCleanup = function() {
        parentRow.removeEventListener('click', rowClickHandler);
    };
}

function onAddSubTopic(parentTopic) {
    var subName = prompt('请输入子主题名称：\n\n将添加到「' + parentTopic + '」下');
    if (!subName || !subName.trim()) return;
    subName = subName.trim();

    var fullPath = parentTopic + '/' + subName;

    window.api.createTopic(fullPath).then(function(result) {
        if (result && result.success) {
            loadTopicTree();
        } else {
            alert('创建子主题失败：' + (result ? result.message : '未知错误'));
        }
    }).catch(function(e) {
        console.error('[Topic] add sub-topic error:', e);
        alert('创建子主题出错');
    });
}

async function onDeleteTopic(topicName) {
    var confirmed = await window._customConfirm('确定要删除主题「' + topicName + '」吗？\n\n该主题下的文件将从 WIKI.md 中移除，文件的 topic 标签也会被删除，之后会重新尝试自动匹配主题。');
    if (!confirmed) return;

    window.api.deleteTopic(topicName).then(function(result) {
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
        var syncResult = await window.api.syncWikiWithFiles();
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
        var result = await window.api.batchAutoAssignTopics();
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

function showAISuggestionPanel() {
    var panel = document.getElementById('ai-suggestion-panel');
    if (!panel) return;

    panel.style.display = 'flex';
    panel.innerHTML = '';

    var header = document.createElement('div');
    header.className = 'ai-suggestion-header';
    header.innerHTML = '<span class="ai-suggestion-title">AI 主题建议</span>' +
        '<button class="ai-suggestion-close" onclick="closeAISuggestionPanel()" title="关闭">' +
        window.Icons.get('close', 14) + '</button>';
    panel.appendChild(header);

    var list = document.createElement('div');
    list.className = 'ai-suggestion-list';
    list.id = 'ai-suggestion-list';

    var existingSet = {};
    for (var ei = 0; ei < _existingTopics.length; ei++) {
        existingSet[_existingTopics[ei].toLowerCase()] = true;
    }

    for (var i = 0; i < _aiSuggestions.length; i++) {
        var s = _aiSuggestions[i];
        var card = document.createElement('div');
        card.className = 'ai-suggestion-card';
        card.dataset.index = i;

        var typeLabel = { 'new_topic': '新建主题', 'assign_topic': '归档文件', 'merge_topic': '合并主题', 'change_topic': '变更主题' }[s.type] || s.type;

        var body = '';
        if (s.type === 'change_topic') {
            var currentTopic = s.current_topic || '';
            var suggestedTopic = s.suggested_topic || '';
            var isExisting = existingSet[suggestedTopic.toLowerCase()] === true;
            var topicTag = isExisting
                ? '<span class="ai-sg-topic-tag existing">已有主题</span>'
                : '<span class="ai-sg-topic-tag new">全新主题</span>';

            body = '<div class="ai-sg-change-detail">' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">文件</span><span class="ai-sg-change-value">' + escapeHtml(s.file || '') + '</span></div>' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">原始主题</span>' +
                (currentTopic ? '<span class="ai-sg-change-value">' + escapeHtml(currentTopic) + '</span>' : '<span class="ai-sg-change-value empty">当前没有主题</span>') +
                '</div>' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">建议主题</span><span class="ai-sg-change-value">' + escapeHtml(suggestedTopic) + topicTag + '</span></div>' +
                '</div>' +
                '<div class="ai-sg-topic-select-area">' +
                '<select class="ai-sg-topic-select" data-card-index="' + i + '">' +
                '<option value="">-- 选择已有主题 --</option>';

            for (var ti = 0; ti < _existingTopics.length; ti++) {
                var tname = _existingTopics[ti];
                var selected = (tname === suggestedTopic) ? ' selected' : '';
                body += '<option value="' + escapeAttr(tname) + '"' + selected + '>' + escapeHtml(tname) + '</option>';
            }

            body += '</select>' +
                '<input type="text" class="ai-sg-topic-input" placeholder="或输入新主题..." data-card-index="' + i + '" value="">' +
                '</div>';
        } else if (s.type === 'new_topic') {
            body = '<div class="ai-sg-body">创建主题 <b>' + escapeHtml(s.topic) + '</b>' +
                (s.files && s.files.length > 0 ? '，包含 ' + s.files.map(function(f) { return escapeHtml(f); }).join('、') : '') + '</div>';
        } else if (s.type === 'assign_topic') {
            body = '<div class="ai-sg-body">将 <b>' + escapeHtml(s.file) + '</b> 归入主题 <b>' + escapeHtml(s.topic) + '</b></div>';
        } else if (s.type === 'merge_topic') {
            body = '<div class="ai-sg-body">将 <b>' + escapeHtml(s.source_topic) + '</b> 合并到 <b>' + escapeHtml(s.target_topic) + '</b></div>';
        }

        card.innerHTML = '<div class="ai-sg-header">' +
            '<span class="ai-sg-type ai-sg-type-' + s.type + '">' + typeLabel + '</span>' +
            '<div class="ai-sg-actions">' +
            '<button class="ai-sg-yes" data-action="accept" title="采纳">' + window.Icons.get('check', 14) + '</button>' +
            '<button class="ai-sg-no" data-action="reject" title="忽略">' + window.Icons.get('close', 14) + '</button>' +
            '</div></div>' +
            body +
            (s.reason ? '<div class="ai-sg-reason">' + escapeHtml(s.reason) + '</div>' : '');

        list.appendChild(card);
    }

    panel.appendChild(list);

    list.addEventListener('click', function(e) {
        var btn = e.target.closest('button');
        if (!btn) return;
        var card = btn.closest('.ai-suggestion-card');
        if (!card) return;
        var idx = parseInt(card.dataset.index);
        var action = btn.dataset.action;

        if (action === 'accept') {
            applyAISuggestion(idx, card);
        } else if (action === 'reject') {
            card.style.opacity = '0.3';
            card.style.pointerEvents = 'none';
            _aiSuggestions[idx] = null;
            checkAllSuggestionsDone();
        }
    });
}

async function applyAISuggestion(idx, cardEl) {
    var suggestion = _aiSuggestions[idx];
    if (!suggestion) return;

    if (suggestion.type === 'change_topic') {
        var inputEl = cardEl.querySelector('.ai-sg-topic-input');
        var selectEl = cardEl.querySelector('.ai-sg-topic-select');
        var customTopic = inputEl ? inputEl.value.trim() : '';
        var selectedTopic = selectEl ? selectEl.value : '';
        var finalTopic = customTopic || selectedTopic || suggestion.suggested_topic;
        if (!finalTopic) {
            alert('请选择或输入一个主题');
            return;
        }
        suggestion = Object.assign({}, suggestion, { suggested_topic: finalTopic });
    }

    cardEl.style.opacity = '0.5';
    try {
        var result = await window.api.applyTopicSuggestion(suggestion);
        if (result && result.success) {
            cardEl.style.opacity = '0.3';
            cardEl.style.pointerEvents = 'none';
            _aiSuggestions[idx] = null;
            checkAllSuggestionsDone();
            loadTopicView();
        } else {
            alert('应用失败：' + (result ? result.message || '未知错误' : '未知错误'));
            cardEl.style.opacity = '1';
        }
    } catch (e) {
        alert('应用出错：' + (e.message || e));
        cardEl.style.opacity = '1';
    }
}

function checkAllSuggestionsDone() {
    var remaining = _aiSuggestions.filter(function(s) { return s !== null; });
    if (remaining.length === 0) {
        closeAISuggestionPanel();
        updateStatus('所有建议已处理');
    }
}

function closeAISuggestionPanel() {
    var panel = document.getElementById('ai-suggestion-panel');
    if (panel) panel.style.display = 'none';
}

async function onAITopicAnalyze() {
    var btn = document.getElementById('btn-ai-analyze');
    if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
    window.setSidebarStatus('topic', '正在扫描文件...', true);
    updateStatus('AI 正在扫描全量文件分析主题...');

    try {
        try {
            var treeResult = await window.api.getTopicTree();
            if (treeResult && treeResult.topics) {
                _existingTopics = treeResult.topics.map(function(t) { return t.name; });
            }
        } catch (e) {
            _existingTopics = [];
        }

        window.setSidebarStatus('topic', '正在连接大模型...', true);
        var result = await window.api.aiTopicAnalyze();
        if (result && result.success && result.suggestions && result.suggestions.length > 0) {
            _aiSuggestions = result.suggestions;
            showAISuggestionPanel();
            window.setSidebarStatus('topic', result.suggestions.length + ' 条建议');
            updateStatus('AI 分析完成，共 ' + result.suggestions.length + ' 条建议');
        } else if (result && result.success) {
            window.setSidebarStatus('topic', '主题分配合理');
            updateStatus('AI 分析完成，所有文件主题分配合理');
            _aiSuggestions = [];
        } else {
            window.setSidebarStatus('topic', result && result.message ? result.message : '分析失败');
            updateStatus(result && result.message ? result.message : 'AI 分析未返回结果');
            _aiSuggestions = [];
        }
    } catch (e) {
        window.setSidebarStatus('topic', '分析出错');
        updateStatus('AI 分析出错: ' + (e.message || e));
    } finally {
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
        setTimeout(window.updateSidebarStats, 2000);
    }
}

window._surveyStreamText = '';
window._surveyStreamUnlisten = null;
window._surveyFlushTimer = null;
window._surveyBuffer = '';
window._surveyDisplayText = '';

function _flushSurveyBuffer() {
    if (!window._surveyBuffer || window._surveyBuffer.length === 0) {
        if (window._surveyFlushTimer) {
            clearInterval(window._surveyFlushTimer);
            window._surveyFlushTimer = null;
        }
        return;
    }
    var chunkSize = 2;
    var take = window._surveyBuffer.substring(0, chunkSize);
    window._surveyBuffer = window._surveyBuffer.substring(chunkSize);
    window._surveyDisplayText += take;
    if (window.TiptapEditor && window.TiptapEditor.instance && window.marked) {
        var html = window.marked.parse(window._surveyDisplayText);
        if (typeof DOMPurify !== 'undefined') { html = DOMPurify.sanitize(html); }
        window.TiptapEditor.instance.commands.setContent(html, false);
    }
    var editorEl = document.getElementById('tiptap-editor');
    if (editorEl) {
        editorEl.scrollTop = editorEl.scrollHeight;
    }
    if (window._surveyBuffer.length === 0 && window._surveyFlushTimer) {
        clearInterval(window._surveyFlushTimer);
        window._surveyFlushTimer = null;
    }
}

async function onAITopicSurvey() {
    var headings = [];
    try {
        var treeResult = await window.api.getTopicTree();
        if (treeResult && treeResult.topics) {
            headings = treeResult.topics.map(function(t) { return t.name; });
        }
    } catch (e) {
        console.error('[Survey] get topics failed:', e);
    }
    if (headings.length === 0) {
        alert('当前没有主题，请先创建主题');
        return;
    }

    var topic = prompt('请输入要撰写综述的主题：\n\n现有主题：' + headings.join('、'));
    if (!topic || !topic.trim()) return;
    topic = topic.trim();

    var btn = document.getElementById('btn-ai-survey');
    if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
    window.setSidebarStatus('topic', '正在连接大模型...', true);
    updateStatus('AI 正在撰写「' + topic + '」综述...');

    window._surveyStreamText = '';
    window._surveyBuffer = '';
    window._surveyDisplayText = '';

    if (window.TiptapEditor && window.TiptapEditor.instance) {
        window.TiptapEditor.instance.commands.setContent('<p>正在撰写综述...</p>', false);
        window.TiptapEditor.instance.setEditable(false);
    }

    var editorContainer = document.getElementById('tiptap-editor-container');
    if (editorContainer) editorContainer.style.display = '';
    var previewPanel = document.getElementById('preview-panel');
    if (previewPanel) previewPanel.style.display = 'none';

    var eventAPI = window.__TAURI__ && window.__TAURI__.event;
    if (eventAPI) {
        window._surveyStreamUnlisten = await eventAPI.listen('python-event', function(event) {
            var data = event.payload;
            if (!data) return;
            if (data.type === 'survey_chunk' && data.topic === topic) {
                window._surveyStreamText += (data.token || '');
                window._surveyBuffer += (data.token || '');
                if (!window._surveyFlushTimer) {
                    window._surveyFlushTimer = setInterval(_flushSurveyBuffer, 40);
                }
            } else if (data.type === 'survey_done' && data.topic === topic) {
                if (window._surveyFlushTimer) {
                    clearInterval(window._surveyFlushTimer);
                    window._surveyFlushTimer = null;
                }
                window._surveyDisplayText = window._surveyStreamText;
                window._surveyBuffer = '';
                if (window.TiptapEditor && window.TiptapEditor.instance && window.marked) {
                    var html = window.marked.parse(window._surveyDisplayText);
                    window.TiptapEditor.instance.commands.setContent(html, false);
                }
                if (window._surveyStreamUnlisten) {
                    window._surveyStreamUnlisten();
                    window._surveyStreamUnlisten = null;
                }
                if (data.success) {
                    updateStatus('综述撰写完成，已保存为 ' + data.file_path);
                    window.setSidebarStatus('topic', '综述已保存');
                } else {
                    alert('撰写失败：' + (data.message || '未知错误'));
                    updateStatus('综述撰写失败');
                    window.setSidebarStatus('topic', '撰写失败');
                }
                if (window.TiptapEditor && window.TiptapEditor.instance) {
                    window.TiptapEditor.instance.setEditable(true);
                }
                setTimeout(window.updateSidebarStats, 2000);
            }
        });
    }

    try {
        await window.api.aiTopicSurvey(topic);
    } catch (e) {
        alert('撰写出错：' + (e.message || e));
        updateStatus('综述撰写出错');
    } finally {
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
        if (window._surveyFlushTimer) {
            clearInterval(window._surveyFlushTimer);
            window._surveyFlushTimer = null;
        }
        if (window._surveyStreamUnlisten) {
            window._surveyStreamUnlisten();
            window._surveyStreamUnlisten = null;
        }
        if (window.TiptapEditor && window.TiptapEditor.instance) {
            window.TiptapEditor.instance.setEditable(true);
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
        var createResult = await window.api.createTopic(topicName);
        if (!createResult || !createResult.success) {
            alert(createResult ? createResult.message : '创建主题失败');
            if (inputField) inputField.focus();
            return;
        }

        console.log('[Topic] 主题创建成功:', topicName);

        onHideTopicInput();

        await loadTopicTree();

        var batchResult = await window.api.batchAutoAssignTopics();
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

async function loadTopicView() {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;

    var result;
    try {
        result = await window.api.getTopicTree();
        console.log('[Topic] API result:', result);
    } catch (e) {
        console.error('[Topic] loadTopicView error:', e);
        container.innerHTML = '<div class="sidebar-view-empty">加载主题失败<br><span style="font-size: 12px;color:var(--text-muted)">' + escapeHtml(e.message || '未知错误') + '</span></div>';
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
        panel.style.display = 'none';
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
        html += '<div class="topic-assign-row">';
        if (topicNames.length > 0) {
            html += '<select class="topic-select" data-file="' + escapeAttr(p.file) + '" onchange="onTopicSelectChange(this)">';
            html += '<option value="">-- 选择已有主题 --</option>';
            topicNames.forEach(function(name) {
                html += '<option value="' + escapeAttr(name) + '">' + escapeHtml(name) + '</option>';
            });
            html += '</select>';
        }
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

function onTopicSelectChange(selectEl) {
    var topicName = selectEl.value;
    if (!topicName) return;

    var card = selectEl.closest('.topic-pending-card');
    if (!card) return;

    var customInput = card.querySelector('.topic-custom-input');
    if (customInput) {
        customInput.value = topicName;
        customInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    var btns = card.querySelectorAll('.topic-candidate-btn');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
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

    // Also read from the <select> dropdown
    var selectEl = cardEl.querySelector('.topic-select');
    var selectVal = (selectEl && selectEl.value) ? selectEl.value : '';

    var selectedBtn = cardEl.querySelector('.topic-candidate-btn.topic-candidate-selected');
    var selectedTopic = selectedBtn ? selectedBtn.getAttribute('data-topic') || '' : '';

    var topic = custom || selectVal || selectedTopic;
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
    if (selectEl) selectEl.disabled = true;
    if (customBtn) customBtn.disabled = true;
    cardEl.classList.add('resolving');

    window.api.resolveTopic(file, topic).then(function(result) {
        if (result && result.success) {
            cardEl.classList.add('resolved');
            animateCardOut(cardEl);
        } else {
            cardEl.classList.remove('resolving');
            btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
            if (input) input.disabled = false;
            if (selectEl) selectEl.disabled = false;
            if (customBtn) customBtn.disabled = false;
            alert('确认主题失败：' + (result ? result.message : '未知错误'));
        }
    }).catch(function(e) {
        console.error('[Topic] resolve error:', e);
        cardEl.classList.remove('resolving');
        btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
        if (input) input.disabled = false;
        if (selectEl) selectEl.disabled = false;
        if (customBtn) customBtn.disabled = false;
        alert('确认主题失败：' + (e.message || '发生错误'));
    });
}

function animateCardOut(cardEl) {
    cardEl.style.transition = 'opacity 0.3s ease, transform 0.3s ease, margin 0.3s ease, padding 0.3s ease, min-height 0.3s ease';
    cardEl.style.opacity = '0';
    cardEl.style.transform = 'translateY(-20px) scale(0.96)';
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
            var countEl = list.parentElement && list.parentElement.querySelector('.topic-pending-count');
            if (countEl) countEl.textContent = remaining;
            if (remaining === 0) {
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = 'none';
                loadTopicView();
            } else {
                loadTopicTree();
            }
        }
    }, 350);
}

function hasTopicPending() {
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return false;
    var cards = panel.querySelectorAll('.topic-pending-card:not(.resolved)');
    return cards.length > 0;
}

window.loadTopicTree = loadTopicTree;
window.loadTopicView = loadTopicView;
window.loadTopicPendingPanel = loadTopicPendingPanel;
window.onBatchAutoAssignTopics = onBatchAutoAssignTopics;
window.onAITopicAnalyze = onAITopicAnalyze;
window.onAITopicSurvey = onAITopicSurvey;
window.onShowTopicInput = onShowTopicInput;
window.onHideTopicInput = onHideTopicInput;
window.onTopicInputChange = onTopicInputChange;
window.onConfirmTopic = onConfirmTopic;
window.closeAISuggestionPanel = closeAISuggestionPanel;
window.onCandidateClick = onCandidateClick;
window.onInputChange = onInputChange;
window.onTopicSelectChange = onTopicSelectChange;
window.onInputEnter = onInputEnter;
window.onConfirmBtnClick = onConfirmBtnClick;
window.hasTopicPending = hasTopicPending;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupTopicInputEvents);
} else {
    setupTopicInputEvents();
}

})();

