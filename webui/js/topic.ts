(function() { 'use strict';

var _lastTopicData: string | null = null;
var _aiSuggestions: any[] = [];
var _existingTopics: string[] = [];
var _pendingDragData: { filePath: string | null; cardEl: Element | null } = { filePath: null, cardEl: null };

var Icons = window.Icons as { get(name: string, size?: number): string };

interface TopicTreeNode {
    children: Record<string, TopicTreeNode>;
    files: any[];
    name: string;
    label: string;
}

function _buildTopicTree(topics: any[]): TopicTreeNode {
    var root: TopicTreeNode = { children: {}, files: [], name: '', label: '' };
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

function _renderTopicTree(node: TopicTreeNode, expandedTopics: Record<string, boolean>, depth?: number): string {
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

        html += '<div class="sidebar-tag-group' + isExpanded + '" data-topic-name="' + window.escapeAttr(child.name) + '">';
        html += '<div class="sidebar-tag-row" onclick="window.topicRowClick(this)" data-topic-name="' + window.escapeAttr(child.name) + '" style="padding-left:' + (8 + indent) + 'px">';
        if (hasChildren || hasFiles) {
            html += '<span class="sidebar-tag-toggle" onclick="event.stopPropagation(); this.parentElement.classList.toggle(\'expanded\')">' + Icons.get('chevronDown') + '</span>';
        } else {
            html += '<span class="sidebar-tag-toggle" style="visibility:hidden">' + Icons.get('chevronDown') + '</span>';
        }
        html += '<span class="sidebar-tag-name" data-topic-name="' + window.escapeAttr(child.name) + '">' + window.escapeHtml(child.label) + '</span>';
        if (totalFiles > 0) {
            html += '<span class="sidebar-tag-count">' + totalFiles + '</span>';
        }
        // 一级主题行挂综述状态：开关 / 无综述标记 / 综述预览 / 可更新
        var surveyStaleShown = false;
        if (depth === 0) {
            var ov = (window._surveyOverviewMap || {})[child.name] || {};
            var enabled = ov.enabled !== false;
            if (!enabled) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-off" title="' + window.escapeAttr(window.t('topic.surveyOffTitle')) + '">' + window.escapeHtml(window.t('topic.surveyOff')) + '</span>';
            } else if (!ov.has_survey) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-missing" title="' + window.escapeAttr(window.t('topic.noSurveyTitle')) + '">' + window.escapeHtml(window.t('topic.noSurvey')) + '</span>';
            } else {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-ok" onclick="event.stopPropagation(); window.previewTopicSurvey(\'' + window.escapeAttr(child.name) + '\')">' + window.escapeHtml(window.t('topic.surveyDoc')) + '</span>';
                if (ov.stale) {
                    surveyStaleShown = true;
                    html += '<span class="sidebar-tag-survey sidebar-tag-survey-stale" onclick="event.stopPropagation(); window.updateTopicSurvey(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.surveyUpdateTitle')) + '">' + window.escapeHtml(window.t('topic.surveyStale')) + '</span>';
                }
            }
            // P5：语义知识页（wiki/semantic/*_语义.md）可更新提示，来自 get_topic_tree 的 stale_topics；
            // 综述 stale 徽标已展示同一级主题时不重复展示
            if ((window._topicStaleMap || {})[child.name] && !surveyStaleShown) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-stale" onclick="event.stopPropagation(); window.previewSemanticWikiPage(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.wikiStaleTitle')) + '">' + window.escapeHtml(window.t('topic.wikiStale')) + '</span>';
            }
            html += '<span class="sidebar-tag-survey-toggle' + (enabled ? ' on' : '') + '" onclick="event.stopPropagation(); window.toggleTopicSurvey(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.surveyToggleTitle')) + '"></span>';
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
                var display = f.title || window.t('download.unnamed');
                var path = f.path || '';
                if (path) {
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + window.escapeAttr(path) + '" onclick="window.TreeModule.selectFile(\'' + window.escapeAttr(path) + '\', \'' + window.escapeAttr(display) + '\')" style="padding-left:' + (24 + indent) + 'px">';
                } else {
                    html += '<div class="sidebar-tag-file tree-item" style="padding-left:' + (24 + indent) + 'px">';
                }
                html += '<span class="tree-name">' + window.escapeHtml(display) + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        html += '</div>';
    });
    return html;
}

function _countAllFiles(node: TopicTreeNode): number {
    var count = node.files.length;
    var keys = Object.keys(node.children);
    for (var i = 0; i < keys.length; i++) {
        count += _countAllFiles(node.children[keys[i]]);
    }
    return count;
}

function _surveyState(topic: string): any {
    return (window._surveyOverviewMap || {})[topic] || { enabled: true, has_survey: false, stale: false, survey_path: '' };
}

function _openSurveyPreview(topic: string): boolean {
    var ov = _surveyState(topic);
    if (ov.has_survey && ov.survey_path && typeof window.showPreview === 'function') {
        window.showPreview({ path: ov.survey_path, name: topic + ' ' + window.t('topic.surveyDoc') });
        return true;
    }
    return false;
}

function topicRowClick(rowEl: HTMLElement) {
    var topic = rowEl.getAttribute('data-topic-name') || '';
    // 有综述的主题：点行直接打开综述预览；否则展开/收起
    if (_openSurveyPreview(topic)) return;
    rowEl.parentElement!.classList.toggle('expanded');
}

function previewTopicSurvey(topic: string) {
    _openSurveyPreview(topic);
}

// P5：语义知识页路径与后端 wiki._target_path 对齐（wiki/semantic/{安全段}_语义.md）
function _semanticWikiPagePath(topic: string): string {
    var safe = String(topic == null ? '' : topic).trim().replace(/[\\/:*?"<>|]/g, '_').replace(/^[. ]+|[. ]+$/g, '');
    if (!safe) return '';
    return 'wiki/semantic/' + safe + '_语义.md';
}

function previewSemanticWikiPage(topic: string) {
    var path = _semanticWikiPagePath(topic);
    if (!path || typeof window.showPreview !== 'function') return;
    window.showPreview({ path: path, name: topic + ' · 语义知识' });
}

async function toggleTopicSurvey(topic: string): Promise<void> {
    var ov = _surveyState(topic);
    var enable = ov.enabled !== false;
    var actionText = enable ? window.t('topic.surveyTurnOff') : window.t('topic.surveyTurnOn');
    var message = window.t('topic.surveyToggleConfirm', { topic: topic, action: actionText });
    var ok = false;
    if (typeof window._customConfirm === 'function') {
        ok = await window._customConfirm(message);
    } else {
        ok = window.confirm(message);
    }
    if (!ok) return;
    try {
        var r = await window.api.toggleSurvey(topic);
        if (r && r.success === false) {
            alert(r.message || window.t('common.errorOccurred'));
            return;
        }
        if (window._surveyOverviewMap) {
            window._surveyOverviewMap[topic] = Object.assign({}, ov, { enabled: !enable });
        }
        await loadTopicTree(true, true);
    } catch (e) {
        console.error('[Topic] toggleSurvey error:', e);
        alert((e as Error).message || window.t('common.unknownError'));
    }
}

function updateTopicSurvey(topic: string) {
    onAITopicSurvey(topic);
}

async function loadTopicTree(silent?: boolean, forceRefresh?: boolean): Promise<void> {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;
    if (!silent) {
        container.innerHTML = '<div class="sidebar-view-loading">' + window.t('topic.loading') + '</div>';
    }

    try {
        var result = await window.api.getTopicTree();

        // 并行拉取综述状态总览（开关 / 是否有综述 / 可更新）
        var overview: Record<string, any> = {};
        try {
            var ovResult = await window.api.getSurveyOverview();
            if (ovResult && typeof ovResult === 'object' && ovResult.overview) {
                overview = ovResult.overview;
            }
        } catch (e) {
            console.warn('[Topic] getSurveyOverview failed:', e);
        }
        window._surveyOverviewMap = overview;

        if (!result || typeof result !== 'object') {
            container.innerHTML = '<div class="sidebar-view-empty">' + window.t('topic.invalidResponse') + '</div>';
            return;
        }

        var dataStr = JSON.stringify(result);
        if (!forceRefresh && silent && dataStr === _lastTopicData) return;
        _lastTopicData = dataStr;
        window.AppState.lastTopicData = dataStr;

        if (result.success === false) {
            container.innerHTML = '<div class="sidebar-view-empty"><span>' + window.escapeHtml(result.message || window.t('common.backendError')) + '</span></div>';
            return;
        }

        // P5：语义知识页可更新主题集（仅 wiki 已有该主题段时纳入），供一级主题行渲染徽标
        var staleMap: Record<string, boolean> = {};
        (result.stale_topics || []).forEach(function(name: string) {
            staleMap[name] = true;
        });
        window._topicStaleMap = staleMap;

        var topics = result.topics || [];
        var hasTopics = topics.length > 0;

        if (!hasTopics) {
            container.innerHTML = '<div class="sidebar-view-empty">' + window.t('topic.noTopics') + '</div>';
            return;
        }

        var expandedTopics: Record<string, boolean> = {};
        container.querySelectorAll('.sidebar-tag-group.expanded').forEach(function(el) {
            var name = el.getAttribute('data-topic-name');
            if (name) expandedTopics[name] = true;
        });

        var treeData = _buildTopicTree(result.topics);

        var html = '<div class="sidebar-tags-list">';
        html += _renderTopicTree(treeData, expandedTopics);
        html += '</div>';

        html += '<div class="topic-context-menu" id="topic-context-menu" style="display:none;">';
        html += '<div class="topic-menu-item" data-action="rename">' + window.t('topic.rename') + '</div>';
        html += '</div>';

        container.innerHTML = html;

        setupTopicDragDrop(container);
        setupTopicContextMenu(container);
        window.updateSidebarStats();
    } catch (e) {
        console.error('[Topic] loadTopicTree error:', e);
                container.innerHTML = '<div class="sidebar-view-empty"><span>' + window.escapeHtml((e as Error).message || window.t('common.unknownError')) + '</span></div>';
    }
}

function setupTopicDragDrop(container: HTMLElement) {
    if ((container as any)._topicDragDropReady) return;
    (container as any)._topicDragDropReady = true;

    var dragData: { filePath: string | null; fileName: string | null; srcTopic: string | null } = { filePath: null, fileName: null, srcTopic: null };

    container.addEventListener('dragstart', function(e: DragEvent) {
        var fileEl = (e.target as Element).closest('.sidebar-tag-file');
        if (!fileEl) return;

        var filePath = fileEl.getAttribute('data-file-path');
        if (!filePath) return;

        var srcGroup = fileEl.closest('.sidebar-tag-group');
        var srcTopic = srcGroup ? srcGroup.getAttribute('data-topic-name') : null;

        dragData.filePath = filePath;
        dragData.fileName = fileEl.querySelector('.tree-name')?.textContent || window.t('common.file');
        dragData.srcTopic = srcTopic;
        fileEl.classList.add('dragging');

        e.dataTransfer!.effectAllowed = 'move';
        e.dataTransfer!.setData('text/plain', filePath);
        e.dataTransfer!.setData('application/x-topic-src', srcTopic || '');
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

    container.addEventListener('dragover', function(e: DragEvent) {
        var pendingCard = document.querySelector('.topic-pending-card.dragging');
        if (!dragData.filePath && !pendingCard) return;
        e.preventDefault();
        e.dataTransfer!.dropEffect = 'move';

        var rowEl = (e.target as Element).closest('.sidebar-tag-row');
        var groupEl = (e.target as Element).closest('.sidebar-tag-group');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        var targetTopic: string | null = null;
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

    container.addEventListener('dragleave', function(e: DragEvent) {
        var rowEl = (e.target as Element).closest('.sidebar-tag-row');
        if (rowEl) rowEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e: DragEvent) {
        e.preventDefault();
        e.stopPropagation();

        var pendingCard = document.querySelector('.topic-pending-card.dragging');
        if (pendingCard) {
            var pendingFile = pendingCard.getAttribute('data-file');
            var targetEl = (e.target as Element).closest('.sidebar-tag-row') || (e.target as Element).closest('.sidebar-tag-group');
            var targetTopic = targetEl ? targetEl.getAttribute('data-topic-name') : null;

            if (!targetTopic || !pendingFile) {
                cleanupDragState(container);
                return;
            }

            try {
                var result = await window.api.resolveTopic(pendingFile, targetTopic);
                if (result && result.success) {
                    pendingCard.classList.add('resolved');
                    animateCardOut(pendingCard as HTMLElement);
                } else {
                    alert(window.t('topic.confirmTopicFailed') + (result ? result.message : window.t('common.unknownError')));
                }
            } catch (err) {
                console.error('[Topic] resolve via drag error:', err);
                alert(window.t('topic.confirmTopicFailed') + ((err as Error).message || window.t('common.errorOccurred')));
            }

            cleanupDragState(container);
            return;
        }

        var filePath = dragData.filePath;
        if (!filePath) {
            cleanupDragState(container);
            return;
        }

        var targetEl2 = (e.target as Element).closest('.sidebar-tag-row') || (e.target as Element).closest('.sidebar-tag-group');
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
                alert(window.t('topic.moveFailed') + (result2 ? result2.message : window.t('common.unknownError')));
            }
        } catch (err) {
            console.error('[Topic] move error:', err);
            alert(window.t('topic.moveFailed') + ((err as Error).message || window.t('common.errorOccurred')));
        }

        cleanupDragState(container);
    });

    function cleanupDragState(cont: HTMLElement) {
        cont.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });
    }
}

function setupTopicContextMenu(container: HTMLElement) {
    container.addEventListener('contextmenu', function(e: MouseEvent) {
        var fileEl = (e.target as Element).closest('.sidebar-tag-file');
        var rowEl = (e.target as Element).closest('.sidebar-tag-row');

        if (fileEl) {
            e.preventDefault();
            e.stopPropagation();
            showTopicFileContextMenu(e, fileEl as HTMLElement);
        } else if (rowEl) {
            e.preventDefault();
            e.stopPropagation();
            showTopicContextMenu(e, rowEl as HTMLElement);
        }
    });
}

function showTopicContextMenu(e: MouseEvent, rowEl: HTMLElement) {
    window.hideTreeContextMenu();

    const topicName = rowEl.getAttribute('data-topic-name');
    var tagNameEl = rowEl.querySelector('.sidebar-tag-name');
    if (!topicName) return;

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items: { label: string; icon: string; action: () => void }[] = [];

    items.push({
        label: window.t('topic.changeName'),
        icon: Icons.get('fileEdit'),
        action: function() {
            if (tagNameEl) {
                startTopicRename(tagNameEl as HTMLElement, topicName);
            }
        }
    });

    items.push({
        label: window.t('topic.addSubTopic'),
        icon: Icons.get('plus'),
        action: function() {
            onAddSubTopic(topicName);
        }
    });

    items.push({
        label: window.t('tree.deleteTopic'),
        icon: Icons.get('trash'),
        action: function() {
            onDeleteTopic(topicName);
        }
    });

    items.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'ctx-menu-item';
        el.innerHTML = item.icon + '<span>' + item.label + '</span>';
        el.addEventListener('click', function() {
            window.hideTreeContextMenu();
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

function showTopicFileContextMenu(e: MouseEvent, fileEl: HTMLElement) {
    window.hideTreeContextMenu();

    const path = fileEl.getAttribute('data-file-path');
    var name = fileEl.querySelector('.tree-name')?.textContent || window.t('common.file');

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items: { label: string; icon: string; action: () => void }[] = [];

    items.push({
        label: window.t('tree.revealInFinder'),
        icon: Icons.get('folder'),
        action: function() { if (path) window.revealInFinder(path); }
    });

    items.push({
        label: window.t('tree.openInNewWindow'),
        icon: Icons.get('folderOpen'),
        action: function() {
            if (path && window.api && window.api.openFileInNewWindow) {
                window.api.openFileInNewWindow(path, name);
            }
        }
    });

    items.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'ctx-menu-item';
        el.innerHTML = item.icon + '<span>' + item.label + '</span>';
        el.addEventListener('click', function() {
            window.hideTreeContextMenu();
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

function startTopicRename(tagNameEl: HTMLElement, oldTopicName: string) {
    const parentRow = tagNameEl.closest('.sidebar-tag-row');
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
    function finishRename(cancel: boolean) {
        if (finished) return;
        finished = true;

        if ((input as any)._renameCleanup) (input as any)._renameCleanup();

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

    var rowClickHandler = function(e: Event) {
        if (e.target === input || (e.target as Element).closest('.topic-rename-input')) {
            e.stopPropagation();
        }
    };
    parentRow.addEventListener('click', rowClickHandler);
    (input as any)._renameCleanup = function() {
        parentRow.removeEventListener('click', rowClickHandler);
    };
}

function onAddSubTopic(parentTopic: string) {
    var subName = prompt(window.t('topic.enterSubTopicName', { parent: parentTopic }));
    if (!subName || !subName.trim()) return;
    subName = subName.trim();

    var fullPath = parentTopic + '/' + subName;

    window.api.createTopic(fullPath).then(function(result) {
        if (result && result.success) {
            loadTopicTree();
        } else {
            alert(window.t('topic.createSubTopicFailed') + (result ? result.message : window.t('common.unknownError')));
        }
    }).catch(function(e) {
        console.error('[Topic] add sub-topic error:', e);
        alert(window.t('topic.createSubTopicError'));
    });
}

async function onDeleteTopic(topicName: string): Promise<void> {
    var confirmed = await window._customConfirm(window.t('topic.confirmDeleteTopic', { name: topicName }));
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
            alert(window.t('topic.deleteTopicFailed') + (result && result.message ? result.message : window.t('common.unknownError')));
        }
    }).catch(function(e) {
        console.error('[Topic] delete error:', e);
        alert(window.t('topic.deleteTopicError'));
    });
}

async function onBatchAutoAssignTopics(): Promise<void> {
    var btn = document.getElementById('btn-auto-topic') as HTMLButtonElement | null;
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }

    try {
        console.log('[Topic] Step 1: Sync WIKI.md with file YAML topics...');
        var syncResult = await window.api.syncWikiWithFiles();
        console.log('[Topic] Sync result:', syncResult);

        if (syncResult && syncResult.success) {
            var syncMsg = window.t('topic.syncDone', {
                moved: syncResult.moved,
                added: syncResult.added,
                removed: syncResult.removed,
                deleted: syncResult.deleted_topics
            });
            console.log('[Topic] ' + syncMsg);
        }

        await loadTopicTree();

        console.log('[Topic] Step 2: Auto assign topics for files without topic...');
        var result = await window.api.batchAutoAssignTopics();
        if (result && result.success) {
            await loadTopicTree();

            if (result.pending && result.pending.length > 0) {
                var topicNames: string[] = [];
                document.querySelectorAll('#sidebar-topic .sidebar-tag-group').forEach(function(el) {
                    var n = el.getAttribute('data-topic-name');
                    if (n) topicNames.push(n);
                });
                loadTopicPendingPanel(result.pending, topicNames);
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = '';
            }

            var msg = window.t('topic.scanDone', {
                total: result.total,
                assigned: result.auto_assigned,
                pending: result.need_confirm,
                skipped: result.skipped
            });
            console.log('[Topic] ' + msg);
        } else {
            var errMsg = result && result.message ? result.message : window.t('common.unknownError');
            console.error('[Topic] batch failed:', result);
            alert(window.t('topic.autoAssignFailed') + errMsg);
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
    header.innerHTML = '<span class="ai-suggestion-title">' + window.t('topic.aiSuggestionTitle') + '</span>' +
        '<button class="ai-suggestion-close" onclick="closeAISuggestionPanel()" title="' + window.t('common.close') + '">' +
        Icons.get('close', 14) + '</button>';
    panel.appendChild(header);

    var list = document.createElement('div');
    list.className = 'ai-suggestion-list';
    list.id = 'ai-suggestion-list';

    var existingSet: Record<string, boolean> = {};
    for (var ei = 0; ei < _existingTopics.length; ei++) {
        existingSet[_existingTopics[ei].toLowerCase()] = true;
    }

    for (var i = 0; i < _aiSuggestions.length; i++) {
        var s = _aiSuggestions[i];
        var card = document.createElement('div');
        card.className = 'ai-suggestion-card';
        card.dataset.index = String(i);

        var typeLabel: string = {
            'new_topic': window.t('topic.typeNewTopic'),
            'assign_topic': window.t('topic.typeAssignTopic'),
            'merge_topic': window.t('topic.typeMergeTopic'),
            'change_topic': window.t('topic.typeChangeTopic')
        }[s.type as string] || window.escapeHtml(s.type || '');

        var body = '';
        if (s.type === 'change_topic') {
            var currentTopic = s.current_topic || '';
            var suggestedTopic = s.suggested_topic || '';
            var isExisting = existingSet[suggestedTopic.toLowerCase()] === true;
            var topicTag = isExisting
                ? '<span class="ai-sg-topic-tag existing">' + window.t('topic.existingTopic') + '</span>'
                : '<span class="ai-sg-topic-tag new">' + window.t('topic.newTopicTag') + '</span>';

            body = '<div class="ai-sg-change-detail">' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">' + window.t('topic.labelFile') + '</span><span class="ai-sg-change-value">' + window.escapeHtml(s.file || '') + '</span></div>' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">' + window.t('topic.labelOriginalTopic') + '</span>' +
                (currentTopic ? '<span class="ai-sg-change-value">' + window.escapeHtml(currentTopic) + '</span>' : '<span class="ai-sg-change-value empty">' + window.t('topic.noCurrentTopic') + '</span>') +
                '</div>' +
                '<div class="ai-sg-change-row"><span class="ai-sg-change-label">' + window.t('topic.labelSuggestedTopic') + '</span><span class="ai-sg-change-value">' + window.escapeHtml(suggestedTopic) + topicTag + '</span></div>' +
                '</div>' +
                '<div class="ai-sg-topic-select-area">' +
                '<select class="ai-sg-topic-select" data-card-index="' + i + '">' +
                '<option value="">' + window.t('topic.selectExistingTopic') + '</option>';

            for (var ti = 0; ti < _existingTopics.length; ti++) {
                var tname = _existingTopics[ti];
                var selected = (tname === suggestedTopic) ? ' selected' : '';
                body += '<option value="' + window.escapeAttr(tname) + '"' + selected + '>' + window.escapeHtml(tname) + '</option>';
            }

            body += '</select>' +
                '<input type="text" class="ai-sg-topic-input" data-card-index="' + i + '" placeholder="' + window.t('topic.suggestionTopicPlaceholder') + '" value="">' +
                '</div>';
        } else if (s.type === 'new_topic') {
            body = '<div class="ai-sg-body">' + window.t('topic.createTopicBody', {
                topic: '<b>' + window.escapeHtml(s.topic) + '</b>',
                files: (s.files && s.files.length > 0)
                    ? window.t('topic.includesFiles', { files: s.files.map(function(f: string) { return window.escapeHtml(f); }).join('、') })
                    : ''
            }) + '</div>';
        } else if (s.type === 'assign_topic') {
            body = '<div class="ai-sg-body">' + window.t('topic.assignFileBody', {
                file: '<b>' + window.escapeHtml(s.file) + '</b>',
                topic: '<b>' + window.escapeHtml(s.topic) + '</b>'
            }) + '</div>';
        } else if (s.type === 'merge_topic') {
            body = '<div class="ai-sg-body">' + window.t('topic.mergeTopicBody', {
                source: '<b>' + window.escapeHtml(s.source_topic) + '</b>',
                target: '<b>' + window.escapeHtml(s.target_topic) + '</b>'
            }) + '</div>';
        }

        card.innerHTML = '<div class="ai-sg-header">' +
            '<span class="ai-sg-type ai-sg-type-' + window.escapeAttr(s.type || '') + '">' + typeLabel + '</span>' +
            '<div class="ai-sg-actions">' +
            '<button class="ai-sg-yes" data-action="accept" title="' + window.t('topic.acceptSuggestion') + '">' + Icons.get('check', 14) + '</button>' +
            '<button class="ai-sg-no" data-action="reject" title="' + window.t('topic.rejectSuggestion') + '">' + Icons.get('close', 14) + '</button>' +
            '</div></div>' +
            body +
            (s.reason ? '<div class="ai-sg-reason">' + window.escapeHtml(s.reason) + '</div>' : '');

        list.appendChild(card);
    }

    panel.appendChild(list);

    list.addEventListener('click', function(e: MouseEvent) {
        var btn = (e.target as Element).closest('button');
        if (!btn) return;
        var card = btn.closest('.ai-suggestion-card') as HTMLElement | null;
        if (!card) return;
        var idx = parseInt(card.dataset.index || '');
        var action = btn.dataset.action;

        if (action === 'accept') {
            applyAISuggestion(idx, card as HTMLElement);
        } else if (action === 'reject') {
            card.style.opacity = '0.3';
            card.style.pointerEvents = 'none';
            _aiSuggestions[idx] = null;
            checkAllSuggestionsDone();
        }
    });
}

async function applyAISuggestion(idx: number, cardEl: HTMLElement): Promise<void> {
    var suggestion = _aiSuggestions[idx];
    if (!suggestion) return;

    if (suggestion.type === 'change_topic') {
        var inputEl = cardEl.querySelector('.ai-sg-topic-input') as HTMLInputElement | null;
        var selectEl = cardEl.querySelector('.ai-sg-topic-select') as HTMLSelectElement | null;
        var customTopic = inputEl ? inputEl.value.trim() : '';
        var selectedTopic = selectEl ? selectEl.value : '';
        var finalTopic = customTopic || selectedTopic || suggestion.suggested_topic;
        if (!finalTopic) {
            alert(window.t('topic.selectOrEnterTopic'));
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
            alert(window.t('topic.applyFailed') + (result ? result.message || window.t('common.unknownError') : window.t('common.unknownError')));
            cardEl.style.opacity = '1';
        }
    } catch (e) {
        alert(window.t('topic.applyError') + ((e as Error).message || e));
        cardEl.style.opacity = '1';
    }
}

function checkAllSuggestionsDone() {
    var remaining = _aiSuggestions.filter(function(s) { return s !== null; });
    if (remaining.length === 0) {
        closeAISuggestionPanel();
        window.updateStatus(window.t('topic.allSuggestionsProcessed'));
    }
}

function closeAISuggestionPanel() {
    var panel = document.getElementById('ai-suggestion-panel');
    if (panel) panel.style.display = 'none';
}

async function onAITopicAnalyze(): Promise<void> {
    var btn = document.getElementById('btn-ai-analyze') as HTMLButtonElement | null;
    if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
    window.setSidebarStatus('topic', window.t('integrator.scanningFiles'), true);
    window.updateStatus(window.t('topic.aiScanning'));

    try {
        try {
            var treeResult = await window.api.getTopicTree();
            if (treeResult && treeResult.topics) {
                _existingTopics = treeResult.topics.map(function(t: any) { return t.name; });
            }
        } catch (e) {
            _existingTopics = [];
        }

        window.setSidebarStatus('topic', window.t('topic.connectingLlm'), true);
        var result = await window.api.aiTopicAnalyze();
        if (result && result.success && result.suggestions && result.suggestions.length > 0) {
            _aiSuggestions = result.suggestions;
            showAISuggestionPanel();
            window.setSidebarStatus('topic', window.t('topic.suggestionsCount', { count: result.suggestions.length }));
            window.updateStatus(window.t('topic.aiAnalysisDone', { count: result.suggestions.length }));
        } else if (result && result.success) {
            window.setSidebarStatus('topic', window.t('topic.topicsOk'));
            window.updateStatus(window.t('topic.aiAnalysisAllOk'));
            _aiSuggestions = [];
        } else {
            window.setSidebarStatus('topic', result && result.message ? result.message : window.t('topic.analysisFailed'));
            window.updateStatus(result && result.message ? result.message : window.t('topic.aiNoResult'));
            _aiSuggestions = [];
        }
    } catch (e) {
        window.setSidebarStatus('topic', window.t('topic.analysisError'));
        window.updateStatus(window.t('topic.aiAnalysisError') + ((e as Error).message || e));
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

async function onAITopicSurvey(prefillTopic?: string): Promise<void> {
    var headings: string[] = [];
    try {
        var treeResult = await window.api.getTopicTree();
        if (treeResult && treeResult.topics) {
            headings = treeResult.topics.map(function(t: any) { return t.name; });
        }
    } catch (e) {
        console.error('[Survey] get topics failed:', e);
    }
    if (headings.length === 0) {
        alert(window.t('topic.noTopicsYet'));
        return;
    }

    var topic = (prefillTopic || '').trim();
    if (!topic) {
        topic = prompt(window.t('topic.enterSurveyTopic', { topics: headings.join('、') })) || '';
        if (!topic || !topic.trim()) return;
        topic = topic.trim();
    }

    var btn = document.getElementById('btn-ai-survey') as HTMLButtonElement | null;
    if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
    window.setSidebarStatus('topic', window.t('topic.connectingLlm'), true);
    window.updateStatus(window.t('topic.aiWritingSurvey', { topic: topic }));

    window._surveyStreamText = '';
    window._surveyBuffer = '';
    window._surveyDisplayText = '';

    if (window.TiptapEditor && window.TiptapEditor.instance) {
        window.TiptapEditor.instance.commands.setContent('<p>' + window.t('topic.writingSurvey') + '</p>', false);
        window.TiptapEditor.instance.setEditable(false);
    }

    var editorContainer = document.getElementById('tiptap-editor-container');
    if (editorContainer) editorContainer.style.display = '';
    var previewPanel = document.getElementById('preview-panel');
    if (previewPanel) previewPanel.style.display = 'none';

    var eventAPI = window.getTauriEventAPI ? window.getTauriEventAPI() : null;
    if (eventAPI) {
        window._surveyStreamUnlisten = await eventAPI.listen('python-event', function(event: any) {
            var data = event.payload;
            if (!data) return;
            if (data.type === 'survey_chunk' && data.topic === topic) {
                window._surveyStreamText += (data.token || '');
                window._surveyBuffer += (data.token || '');
                if (!window._surveyFlushTimer) {
                    window._surveyFlushTimer = setInterval(_flushSurveyBuffer, 40) as unknown as number;
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
                    window.updateStatus(window.t('topic.surveyDone', { path: data.file_path }));
                    window.setSidebarStatus('topic', window.t('topic.surveySaved'));
                } else {
                    alert(window.t('topic.writeFailed') + (data.message || window.t('common.unknownError')));
                    window.updateStatus(window.t('topic.surveyWriteFailed'));
                    window.setSidebarStatus('topic', window.t('topic.writeFailedShort'));
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
        alert(window.t('topic.writeError') + ((e as Error).message || e));
        window.updateStatus(window.t('topic.surveyWriteError'));
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
    var inputField = document.getElementById('topic-input-field') as HTMLInputElement | null;
    var confirmBtn = document.getElementById('topic-input-confirm') as HTMLButtonElement | null;

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
    var inputField = document.getElementById('topic-input-field') as HTMLInputElement | null;

    if (inputPanel) {
        inputPanel.style.display = 'none';
    }
    if (inputField) {
        inputField.value = '';
    }
}

function onTopicInputChange() {
    var inputField = document.getElementById('topic-input-field') as HTMLInputElement | null;
    var confirmBtn = document.getElementById('topic-input-confirm') as HTMLButtonElement | null;

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

async function onConfirmTopic(): Promise<void> {
    var inputField = document.getElementById('topic-input-field') as HTMLInputElement | null;
    var confirmBtn = document.getElementById('topic-input-confirm') as HTMLButtonElement | null;
    var addBtn = document.getElementById('btn-add-topic') as HTMLButtonElement | null;

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
            alert(createResult ? createResult.message : window.t('topic.createTopicFailed'));
            if (inputField) inputField.focus();
            return;
        }

        console.log('[Topic] 主题创建成功:', topicName);

        onHideTopicInput();

        await loadTopicTree();

        var batchResult = await window.api.batchAutoAssignTopics();
        if (batchResult && batchResult.success) {
            if (batchResult.pending && batchResult.pending.length > 0) {
                var topicNames2: string[] = [];
                document.querySelectorAll('#sidebar-topic .sidebar-tag-group').forEach(function(el) {
                    var n = el.getAttribute('data-topic-name');
                    if (n) topicNames2.push(n);
                });
                loadTopicPendingPanel(batchResult.pending, topicNames2);
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = '';
            }

            var msg = window.t('topic.topicCreatedScan', {
                name: topicName,
                assigned: batchResult.auto_assigned,
                pending: batchResult.need_confirm
            });
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
    var inputField = document.getElementById('topic-input-field') as HTMLInputElement | null;
    var cancelBtn = document.getElementById('topic-input-cancel') as HTMLButtonElement | null;
    var confirmBtn = document.getElementById('topic-input-confirm') as HTMLButtonElement | null;

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

async function loadTopicView(): Promise<void> {
    var container = document.getElementById('sidebar-topic');
    if (!container) return;

    var result;
    try {
        result = await window.api.getTopicTree();
        console.log('[Topic] API result:', result);
    } catch (e) {
        console.error('[Topic] loadTopicView error:', e);
                container.innerHTML = '<div class="sidebar-view-empty"><span>' + window.escapeHtml((e as Error).message || window.t('common.unknownError')) + '</span></div>';
        return;
    }

    await loadTopicTree();

    if (result && result.pending) {
        var topicNames = (result.topics || []).map(function(t: any) { return t.name; });
        loadTopicPendingPanel(result.pending, topicNames);
    }
}

function loadTopicPendingPanel(pending: any[], topicNames?: string[]) {
    topicNames = topicNames || [];
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return;

    if (!pending || pending.length === 0) {
        panel.style.display = 'none';
        return;
    }

    var html = '<div class="topic-pending-header">' + window.t('topic.pendingHeader') + ' <span class="topic-pending-count">' + pending.length + '</span></div>';
    html += '<div class="topic-pending-hint">' + window.t('topic.dragToFolderHint') + '</div>';
    html += '<div class="topic-pending-list">';

    pending.forEach(function(p, i) {
        html += '<div class="topic-pending-card" draggable="true" data-file="' + window.escapeAttr(p.file) + '" data-index="' + i + '">';
        html += '<div class="topic-pending-filename">' + window.escapeHtml(p.title || p.file) + '</div>';
        html += '<div class="topic-pending-candidates">';
        (p.candidates || []).forEach(function(c: string) {
            html += '<button class="topic-candidate-btn" data-topic="' + window.escapeAttr(c) + '" data-file="' + window.escapeAttr(p.file) + '" onclick="onCandidateClick(this)">' + window.escapeHtml(c) + '</button>';
        });
        html += '</div>';
        html += '</div>';
    });

    html += '</div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.topic-custom-input').forEach(function(input) {
        var inputEl = input as HTMLInputElement;
        inputEl.addEventListener('keydown', function(e: KeyboardEvent) {
            if (e.key === 'Enter') {
                onInputEnter(inputEl);
            }
        });
        inputEl.addEventListener('input', function() {
            onInputChange(inputEl);
        });
    });

    setupPendingCardDragDrop(panel);
}

function setupPendingCardDragDrop(panel: HTMLElement) {
    panel.addEventListener('dragstart', function(e: DragEvent) {
        var card = (e.target as Element).closest('.topic-pending-card');
        if (!card) return;
        if (card.classList.contains('resolving') || card.classList.contains('resolved')) return;

        var filePath = card.getAttribute('data-file');
        if (!filePath) return;

        _pendingDragData.filePath = filePath;
        _pendingDragData.cardEl = card;
        card.classList.add('dragging');

        e.dataTransfer!.effectAllowed = 'move';
        e.dataTransfer!.setData('text/plain', filePath);
    });

    panel.addEventListener('dragend', function(e: DragEvent) {
        var card = (e.target as Element).closest('.topic-pending-card');
        if (card) card.classList.remove('dragging');
        _pendingDragData.filePath = null;
        _pendingDragData.cardEl = null;
    });
}

function onCandidateClick(btnEl: HTMLElement) {
    var card = btnEl.closest('.topic-pending-card') as HTMLElement | null;
    if (!card) return;

    var btns = card.querySelectorAll('.topic-candidate-btn');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
    btnEl.classList.add('topic-candidate-selected');

    // A candidate is an explicit user choice. Apply it immediately; drag/drop
    // onto the folder tree remains the second direct-manipulation path.
    doConfirmTopic(card);
}

function onInputChange(inputEl: HTMLInputElement) {
    var card = inputEl.closest('.topic-pending-card');
    if (!card) return;
    var btns = card.querySelectorAll('.topic-candidate-btn.topic-candidate-selected');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
}

function onTopicSelectChange(selectEl: HTMLSelectElement) {
    var topicName = selectEl.value;
    if (!topicName) return;

    var card = selectEl.closest('.topic-pending-card');
    if (!card) return;

    var customInput = card.querySelector('.topic-custom-input') as HTMLInputElement | null;
    if (customInput) {
        customInput.value = topicName;
        customInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    var btns = card.querySelectorAll('.topic-candidate-btn');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
}

function onInputEnter(inputEl: HTMLInputElement) {
    var card = inputEl.closest('.topic-pending-card') as HTMLElement | null;
    if (!card) return;
    doConfirmTopic(card);
}

function onConfirmBtnClick(btnEl: HTMLButtonElement) {
    var card = btnEl.closest('.topic-pending-card') as HTMLElement | null;
    if (!card) return;
    doConfirmTopic(card);
}

function doConfirmTopic(cardEl: HTMLElement) {
    if (cardEl.classList.contains('resolving')) return;

    var file = cardEl.getAttribute('data-file');
    if (!file) return;

    var input = cardEl.querySelector('.topic-custom-input') as HTMLInputElement | null;
    var custom = (input && input.value) ? input.value.trim() : '';

    // Also read from the <select> dropdown
    var selectEl = cardEl.querySelector('.topic-select') as HTMLSelectElement | null;
    var selectVal = (selectEl && selectEl.value) ? selectEl.value : '';

    var selectedBtn = cardEl.querySelector('.topic-candidate-btn.topic-candidate-selected');
    var selectedTopic = selectedBtn ? selectedBtn.getAttribute('data-topic') || '' : '';

    var topic = custom || selectVal || selectedTopic;
    if (!topic) return;

    var btns = cardEl.querySelectorAll('.topic-candidate-btn');
    var customBtn = cardEl.querySelector('.topic-custom-btn') as HTMLButtonElement | null;

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
            alert(window.t('topic.confirmTopicFailed') + (result ? result.message : window.t('common.unknownError')));
        }
    }).catch(function(e) {
        console.error('[Topic] resolve error:', e);
        cardEl.classList.remove('resolving');
        btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
        if (input) input.disabled = false;
        if (selectEl) selectEl.disabled = false;
        if (customBtn) customBtn.disabled = false;
        alert(window.t('topic.confirmTopicFailed') + ((e as Error).message || window.t('common.errorOccurred')));
    });
}

function animateCardOut(cardEl: HTMLElement) {
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
            if (countEl) countEl.textContent = String(remaining);
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

function hasTopicPending(): boolean {
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
window.topicRowClick = topicRowClick;
window.previewTopicSurvey = previewTopicSurvey;
window.previewSemanticWikiPage = previewSemanticWikiPage;
window.toggleTopicSurvey = toggleTopicSurvey;
window.updateTopicSurvey = updateTopicSurvey;
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