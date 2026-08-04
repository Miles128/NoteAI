(function() { 'use strict';

var _pendingViewVisible = false;
var _pendingData = null;
var _allTopics = [];
var _pendingLoadSeq = 0;

function togglePendingView() {
    _pendingViewVisible = !_pendingViewVisible;
    var btn = document.getElementById('titlebar-pending-btn');
    if (btn) btn.classList.toggle('active', _pendingViewVisible);

    if (_pendingViewVisible) {
        showPendingViewContent();
    } else {
        hidePendingView();
    }
}

function showPendingViewContent() {
    if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.deactivate) window.SemanticWorkbenchModule.deactivate();
    // Hide ALL other right-panel views — no splits
    // pending-view lives inside content-panel. Reading a note hides that parent,
    // so restore it before switching its child views.
    var contentPanel = document.getElementById('content-panel');
    if (contentPanel) contentPanel.style.display = 'flex';

    var views = ['home-dashboard', 'graph-home-view', 'graph-panel', 'semantic-workbench', 'content-area', 'preview-panel',
                 'topic-pending-panel', 'ai-suggestion-panel'];
    views.forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    var pendingView = document.getElementById('pending-view');
    if (pendingView) pendingView.style.display = '';

    loadPendingItems();
}

function hidePendingView() {
    var pendingView = document.getElementById('pending-view');
    if (pendingView) pendingView.style.display = 'none';

    if (window.AppState.selectedFilePath) {
        var contentArea = document.getElementById('content-area');
        var previewPanel = document.getElementById('preview-panel');
        var contentPanel = document.getElementById('content-panel');
        if (contentPanel) contentPanel.style.display = 'none';
        if (contentArea) contentArea.style.display = 'none';
        if (previewPanel) previewPanel.style.display = 'flex';
    } else {
        // Default back to workspace home
        var contentPanel = document.getElementById('content-panel');
        var graphPanel = document.getElementById('graph-panel');
        var home = document.getElementById('home-dashboard');
        if (contentPanel) contentPanel.style.display = 'flex';
        if (graphPanel) graphPanel.style.display = 'none';
        if (home) home.style.display = '';
        window.updateHomeStats();
        if (window.HomeDashboardModule && window.HomeDashboardModule.refresh) {
            window.HomeDashboardModule.refresh();
        }
    }
}

function _loadAllTopics() {
    if (!window.api || !window.api.getTopicTree) {
        return Promise.resolve([]);
    }
    return window.api.getTopicTree().then(function(result) {
        var topics = (result && result.topics) ? result.topics : [];
        _allTopics = [];
        function walk(nodes, prefix) {
            (nodes || []).forEach(function(node) {
                if (!node.name) return;
                var name = prefix ? prefix + ' > ' + node.name : node.name;
                _allTopics.push(name);
                if (node.children && node.children.length) {
                    walk(node.children, name);
                }
            });
        }
        walk(topics, '');
        return _allTopics;
    }).catch(function() {
        _allTopics = [];
        return [];
    });
}

function loadPendingItems() {
    var seq = ++_pendingLoadSeq;
    var listEl = document.getElementById('pending-view-list');
    var countEl = document.getElementById('pending-view-count');
    if (!listEl) return;

    listEl.innerHTML = '<div class="pending-view-empty">' + window.t('common.loading') + '</div>';

    var pendingP = (window.api && window.api.getAllPending)
        ? window.api.getAllPending()
        : Promise.resolve({ items: [], count: 0, topic_options: [] });
    var logP = (window.api && window.api.getActivityLog)
        ? window.api.getActivityLog(50).catch(function() { return null; })
        : Promise.resolve({ entries: [] });

    Promise.all([pendingP, logP]).then(function(results) {
        if (seq !== _pendingLoadSeq) return;
        var result = results[0];
        var logResult = results[1];
        _pendingData = result;
        var items = (result && result.items) ? result.items : [];
        var count = (result && result.count) ? result.count : items.length;
        renderPendingSummary((result && result.summary) || {});
        var topicOpts = (result && result.topic_options) ? result.topic_options : [];

        if (topicOpts.length) {
            _allTopics = topicOpts;
        }

        if (countEl) countEl.textContent = window.t('common.pendingCount', { count: count });

        renderPendingList(items, listEl);

        if (!topicOpts.length && items.some(function(item) {
            return item.type === 'topic' || item.action === 'assign_topic';
        })) {
            _loadAllTopics().then(function() {
                if (seq === _pendingLoadSeq) renderPendingList(items, listEl);
            });
        }

        renderPendingActivityLog(seq, logResult, countEl, count);
    }).catch(function(e) {
        if (seq !== _pendingLoadSeq) return;
        listEl.innerHTML = '<div class="pending-view-empty">' + window.t('pending.loadFailed', { error: window.escapeHtml(String(e)) }) + '</div>';
    });
}

function renderPendingList(items, listEl) {
    if (!items || items.length === 0) {
        listEl.innerHTML = '<div class="pending-view-empty">' + window.t('pending.allDone') + '</div>';
        return;
    }

    var html = '';
    items.forEach(function(item, idx) {
        if (item.type === 'topic') {
            html += renderPendingTopicItem(item, idx);
        } else if (item.type === 'link_batch') {
            html += renderPendingLinkBatchItem(item, idx);
        } else if (item.type === 'link') {
            html += renderPendingLinkItem(item, idx);
        } else if (item.type === 'lint') {
            html += renderPendingInfoItem(item, idx, 'lint');
        } else if (item.type === 'cascade_fail') {
            html += renderPendingInfoItem(item, idx, 'cascade');
        } else if (item.type === 'convert_fail') {
            html += renderPendingInfoItem(item, idx, 'convert');
        } else if (item.type === 'ingest') {
            html += renderPendingInfoItem(item, idx, 'ingest');
        } else if (item.type === 'merge_candidate') {
            html += renderPendingInfoItem(item, idx, 'merge_candidate');
        } else if (item.type === 'topic_merge_candidate') {
            html += renderPendingInfoItem(item, idx, 'topic_merge_candidate');
        } else if (item.type === 'entity_quality') {
            html += renderPendingInfoItem(item, idx, 'entity_quality');
        }
    });
    listEl.innerHTML = html || '<div class="pending-view-empty">' + window.t('pending.allDone') + '</div>';
}

function renderPendingSummary(summary) {
    var el = document.getElementById('pending-summary');
    if (!el) return;
    var rows = [
        ['ingest', 'pending.typeIngest'], ['cascade_fail', 'pending.typeCascade'],
        ['convert_fail', 'pending.typeConvert'], ['topic', 'pending.typeTopic'],
        ['link', 'pending.typeLink'], ['lint', 'pending.typeLint'],
        ['merge_candidate', 'pending.typeMergeCandidate'],
        ['topic_merge_candidate', 'pending.typeTopicMergeCandidate'],
        ['entity_quality', 'pending.typeEntityQuality']
    ].filter(function(row) { return summary[row[0]]; });
    el.innerHTML = rows.map(function(row) {
        return '<span>' + window.escapeHtml(window.t(row[1])) + ' <strong>' + summary[row[0]] + '</strong></span>';
    }).join('');
}

function renderPendingActivityLog(seq, logResult, countEl, pendingCount) {
    var logEl = document.getElementById('pending-view-log');
    if (!logEl) return;
    if (seq !== _pendingLoadSeq) return;

    if (logResult === null) {
        logEl.innerHTML = '<div class="pending-view-empty">' + window.t('common.loading') + '</div>';
        return;
    }

    var logEntries = (logResult && logResult.entries) ? logResult.entries : [];
    if (countEl) countEl.textContent = window.t('common.pendingCount', { count: pendingCount + logEntries.length });

    if (logEntries.length === 0) {
        logEl.innerHTML = '<div class="pending-view-empty">' + window.t('pending.logEmpty') + '</div>';
        return;
    }
    var logHtml = '';
    for (var i = logEntries.length - 1; i >= 0; i--) {
        var e = logEntries[i];
        var d = new Date(e.ts * 1000);
        var time = d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
        logHtml += '<div class="pending-log-item"><span class="pending-log-time">' + time + '</span><span class="pending-log-msg">' + window.escapeHtml(e.msg) + '</span></div>';
    }
    logEl.innerHTML = logHtml;
}

function renderPendingTopicItem(item, idx) {
    var title = window.escapeHtml(item.title || window.Path_stem(item.file));

    var html = '<div class="pending-item" data-pending-idx="' + idx + '" data-file="' + encodeURIComponent(item.file || '') + '">';
    html += '<span class="pending-item-type type-topic">' + window.t('pending.typeTopic') + '</span>';
    html += '<div class="pending-item-title">' + title + '</div>';

    html += '<div class="pending-item-assign">';
    html += '<select class="pending-topic-select" data-action="select-topic">';
    html += '<option value="">' + window.t('pending.selectTopic') + '</option>';
    _allTopics.forEach(function(t) {
        html += '<option value="' + window.escapeAttr(t) + '">' + window.escapeHtml(t) + '</option>';
    });
    html += '</select>';
    html += '<span class="pending-assign-or">' + window.t('common.or') + '</span>';
    html += '<input type="text" class="pending-custom-input" id="pending-custom-input-' + idx + '" placeholder="' + window.t('pending.customTopicPlaceholder') + '">';
    html += '<button class="pending-assign-btn" data-action="resolve-topic">' + window.t('common.confirm') + '</button>';
    html += '</div>';

    html += '</div>';
    return html;
}

function renderPendingLinkBatchItem(item, idx) {
    var count = item.count || 0;
    var message = item.message || window.t('pending.linkBatchSummary', { count: count });
    var html = '<div class="pending-item pending-item-info" data-pending-idx="' + idx + '">';
    html += '<span class="pending-item-type type-link">' + window.t('pending.typeLink') + '</span>';
    html += '<div class="pending-item-title">' + window.escapeHtml(message) + '</div>';
    html += '<div class="pending-item-actions">';
    html += '<button data-action="open-links-panel">' + window.t('pending.openLinksPanel') + '</button>';
    html += '<button data-action="confirm-all-links">' + window.t('links.confirmAllBtn') + '</button>';
    html += '</div>';
    html += '</div>';
    return html;
}

function renderPendingLinkItem(item, idx) {
    var source = window.escapeHtml(item.source || '');
    var target = window.escapeHtml(item.target || '');
    var context = window.escapeHtml(item.context || '');

    var html = '<div class="pending-item" data-pending-idx="' + idx + '" data-source="' + encodeURIComponent(item.source || '') + '" data-target="' + encodeURIComponent(item.target || '') + '">';
    html += '<span class="pending-item-type type-link">' + window.t('pending.typeLink') + '</span>';
    html += '<div class="pending-item-title">' + source + ' → ' + target + '</div>';
    if (context) {
        html += '<div class="pending-item-path">' + context + '</div>';
    }
    html += '<div class="pending-item-actions">';
    html += '<button data-action="confirm-link">' + window.t('pending.confirmLink') + '</button>';
    html += '<button class="btn-reject" data-action="reject-link">' + window.t('pending.rejectLink') + '</button>';
    html += '</div>';
    html += '</div>';
    return html;
}

function renderPendingInfoItem(item, idx, kind) {
    var labelKey = kind === 'lint' ? 'pending.typeLint' : (kind === 'cascade' ? 'pending.typeCascade' : (kind === 'ingest' ? 'pending.typeIngest' : (kind === 'merge_candidate' ? 'pending.typeMergeCandidate' : (kind === 'topic_merge_candidate' ? 'pending.typeTopicMergeCandidate' : (kind === 'entity_quality' ? 'pending.typeEntityQuality' : 'pending.typeConvert')))));
    var title = item.message || item.topic || item.file || item.file_path || item.error || '';
    var detail = item.file_path || item.file || item.topic || item.error || '';
    if (kind === 'merge_candidate') {
        title = (item.files || []).map(function(path) { return window.Path_stem(path); }).join(' · ');
        detail = window.t('pending.mergeCandidateScore', { score: Math.round((item.score || 0) * 100) });
    }
    if (kind === 'topic_merge_candidate') {
        title = (item.topics || []).join(' ↔ ');
        detail = window.t('pending.mergeCandidateScore', { score: Math.round((item.score || 0) * 100) });
    }
    if (kind === 'cascade' && item.error) detail = item.error;
    if (kind === 'convert' && item.error) detail = (item.file || '') + (item.file && item.error ? ' · ' : '') + item.error;
    var html = '<div class="pending-item pending-item-info" data-pending-idx="' + idx + '" data-topic="' + encodeURIComponent(item.topic || '') + '" data-topics="' + encodeURIComponent(JSON.stringify(item.topics || [])) + '" data-current-topic="' + encodeURIComponent(item.current_topic || '') + '" data-file="' + encodeURIComponent(item.file || item.file_path || '') + '" data-files="' + encodeURIComponent(JSON.stringify(item.files || [])) + '" data-related-file="' + encodeURIComponent(item.related_file || '') + '" data-action-kind="' + window.escapeAttr(item.action || '') + '">';
    html += '<span class="pending-item-type type-' + kind + '">' + window.t(labelKey) + '</span>';
    html += '<div class="pending-item-title">' + window.escapeHtml(title || window.t('pending.itemNeedsReview')) + '</div>';
    if (detail && detail !== title) {
        html += '<div class="pending-item-path">' + window.escapeHtml(detail) + '</div>';
    }
    if (item.action === 'retry_cascade' || item.action === 'retry_convert' || item.action === 'retry_ingest' || item.action === 'refresh_survey') {
        var retryLabel = item.action === 'refresh_survey' ? window.t('pending.rewriteSurvey') : window.t('pending.retryItem');
        html += '<div class="pending-item-actions"><button data-action="retry-item">' + retryLabel + '</button>';
        if (item.action !== 'retry_ingest' && item.action !== 'refresh_survey') {
            html += '<button class="btn-reject" data-action="dismiss-item">' + window.t('pending.dismissItem') + '</button>';
        }
        html += '</div>';
    } else if (item.action === 'review_duplicate') {
        html += '<div class="pending-item-path">' + window.escapeHtml(item.related_file || '') + '</div>';
        html += '<div class="pending-item-actions"><button data-action="review-duplicate">' + window.t('pending.reviewDuplicate') + '</button></div>';
    } else if (item.action === 'review_merge_group') {
        html += '<div class="pending-item-actions"><button data-action="review-merge-group">' + window.t('pending.reviewMergeGroup') + '</button></div>';
    } else if (item.action === 'review_topic_merge') {
        html += '<div class="pending-item-actions"><button data-action="review-topic-merge">' + window.t('pending.reviewTopicMerge') + '</button></div>';
    } else if (item.action === 'open_file') {
        html += '<div class="pending-item-actions"><button data-action="open-file">' + window.t('home.openPending') + '</button></div>';
    } else if (item.action === 'assign_topic') {
        var suggestedTopic = item.topic || '';
        var currentTopic = item.current_topic || '';
        html += '<div class="pending-item-actions">';
        html += '<button data-action="move-suggested">' + window.escapeHtml(window.t('pending.moveToTopic', { topic: suggestedTopic })) + '</button>';
        html += '<button class="btn-reject" data-action="keep-current">' + window.escapeHtml(window.t('pending.keepInTopic', { topic: currentTopic })) + '</button>';
        html += '</div>';
    } else if (item.action === 'open_entity_quality') {
        html += '<div class="pending-item-actions"><button data-action="open-entity-quality">' + window.t('semantic.openEntity') + '</button></div>';
    }
    html += '</div>';
    return html;
}

function _findPendingItem(el) {
    var item = el.closest('.pending-item');
    if (!item) return null;
    return {
        el: item,
        idx: parseInt(item.getAttribute('data-pending-idx'), 10),
        filePath: decodeURIComponent(item.getAttribute('data-file') || ''),
        relatedFile: decodeURIComponent(item.getAttribute('data-related-file') || ''),
        source: decodeURIComponent(item.getAttribute('data-source') || ''),
        target: decodeURIComponent(item.getAttribute('data-target') || ''),
        topic: decodeURIComponent(item.getAttribute('data-topic') || ''),
        currentTopic: decodeURIComponent(item.getAttribute('data-current-topic') || ''),
        files: JSON.parse(decodeURIComponent(item.getAttribute('data-files') || '%5B%5D')),
        topics: JSON.parse(decodeURIComponent(item.getAttribute('data-topics') || '%5B%5D')),
        actionKind: item.getAttribute('data-action-kind') || ''
    };
}

function _handlePendingClick(e) {
    var btn = e.target.closest('[data-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-action');
    var info = _findPendingItem(btn);
    if (!info) return;

    if (action === 'move-suggested') {
        if (!info.topic) return;
        resolvePendingTopicItem(info.filePath, info.topic, info.idx);
        return;
    }
    if (action === 'keep-current') {
        keepPendingTopicItem(info);
        return;
    }
    if (action === 'resolve-topic') {
        var select = info.el.querySelector('.pending-topic-select');
        var input = info.el.querySelector('.pending-custom-input');
        var topic = '';
        if (input && input.value.trim()) {
            topic = input.value.trim();
        } else if (select && select.value) {
            topic = select.value;
        }
        if (!topic) return;
        resolvePendingTopicItem(info.filePath, topic, info.idx);
    } else if (action === 'open-file') {
        if (info.filePath && window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(info.filePath, window.Path_stem(info.filePath));
        }
    } else if (action === 'open-entity-quality') {
        if (window.SemanticWorkbenchModule) window.SemanticWorkbenchModule.show('quality');
    } else if (action === 'review-duplicate') {
        reviewDuplicateItem(info);
    } else if (action === 'review-merge-group') {
        reviewMergeGroup(info);
    } else if (action === 'review-topic-merge') {
        reviewTopicMerge(info);
    } else if (action === 'confirm-link') {
        confirmPendingLink(info.source, info.target, info.idx);
    } else if (action === 'open-links-panel') {
        if (typeof window.togglePendingLinksPanel === 'function') {
            window.togglePendingLinksPanel(true);
        }
    } else if (action === 'confirm-all-links') {
        confirmAllPendingLinks(info.idx);
    } else if (action === 'reject-link') {
        rejectPendingLink(info.source, info.target, info.idx);
    } else if (action === 'retry-item') {
        retryPendingItem(info);
    } else if (action === 'dismiss-item') {
        dismissPendingItem(info);
    }
}

function reviewMergeGroup(info) {
    if (!window.api || !window.api.mergeNoteGroup || !info.files || info.files.length < 2) return;
    var list = info.files.join('\n');
    if (!window.confirm(window.t('pending.mergeGroupConfirm', { count: info.files.length }) + '\n\n' + list)) return;
    var title = window.prompt(window.t('pending.mergeTitlePrompt'), window.Path_stem(info.files[0]) + '（整合）');
    if (title === null) return;
    var deleteAuthorized = window.confirm(window.t('pending.deleteOriginalsOnce') + '\n\n' + list);
    window.api.mergeNoteGroup(info.files, title, deleteAuthorized).then(function(result) {
        if (result && result.success) {
            removePendingItem(info.idx);
            if (typeof window.updateStatus === 'function') window.updateStatus(result.message || window.t('pending.mergeDone'));
            if (window.TreeModule && window.TreeModule.loadFileTree) window.TreeModule.loadFileTree();
        } else if (typeof window.updateStatus === 'function') {
            window.updateStatus((result && result.message) || window.t('pending.operationFailed'));
        }
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') window.updateStatus(e.message || window.t('pending.operationFailed'));
    });
}

function reviewTopicMerge(info) {
    if (!window.api || !window.api.suggestTopicMergeNames || !info.topics || info.topics.length !== 2) return;
    if (typeof window.updateStatus === 'function') window.updateStatus(window.t('pending.namingTopic'));
    window.api.suggestTopicMergeNames(info.topics).then(function(result) {
        if (!result || !result.success || !result.names || !result.names.length) throw new Error((result && result.message) || window.t('pending.operationFailed'));
        var choices = result.names.map(function(item, index) { return (index + 1) + '. ' + item.name + ' — ' + item.reason; }).join('\n');
        var newTopic = window.prompt(window.t('pending.chooseMergedTopic') + '\n\n' + choices, result.names[0].name);
        if (!newTopic) return null;
        if (!window.confirm(window.t('pending.confirmTopicMerge', { old: info.topics.join('、'), name: newTopic }))) return null;
        return window.api.mergeSimilarTopics(info.topics, newTopic);
    }).then(function(result) {
        if (!result) return;
        if (result.success) {
            removePendingItem(info.idx);
            if (typeof window.updateStatus === 'function') window.updateStatus(result.message || window.t('pending.mergeDone'));
            if (window.TreeModule && window.TreeModule.loadFileTree) window.TreeModule.loadFileTree();
        } else if (typeof window.updateStatus === 'function') {
            window.updateStatus(result.message || window.t('pending.operationFailed'));
        }
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') window.updateStatus(e.message || window.t('pending.operationFailed'));
    });
}

function keepPendingTopicItem(info) {
    if (!window.api || !window.api.keepNoteInTopic) return;
    window.api.keepNoteInTopic(info.filePath, info.currentTopic, info.topic).then(function(result) {
        if (result && result.success) {
            removePendingItem(info.idx);
        } else {
            if (typeof window.updateStatus === 'function') window.updateStatus((result && result.message) || window.t('pending.operationFailed'));
            loadPendingItems();
        }
    }).catch(function(e) {
        console.warn('[PendingView] keep topic failed:', e);
        loadPendingItems();
    });
}

function reviewDuplicateItem(info) {
    if (!window.api || !window.api.getDuplicateReview || !info.filePath || !info.relatedFile) return;
    window.api.getDuplicateReview(info.filePath, info.relatedFile).then(function(review) {
        if (!review || !review.success) throw new Error((review && review.message) || '无法读取重复笔记');
        var left = (review.primary && review.primary.body) || '';
        var right = (review.related && review.related.body) || '';
        var message = (review.exact ? window.t('pending.exactDuplicate') : window.t('pending.nearDuplicate')) + '\n\n' +
            info.filePath + '\n' + left.slice(0, 900) + '\n\n---\n\n' + info.relatedFile + '\n' + right.slice(0, 900);
        if (!window.confirm(message + '\n\n' + window.t('pending.mergeConfirm'))) return;
        var title = window.prompt(window.t('pending.mergeTitlePrompt'), (review.primary.title || '笔记') + '（整合）');
        if (title === null) return;
        return window.api.mergeDuplicateNotes(info.filePath, info.relatedFile, title);
    }).then(function(result) {
        if (!result) return;
        if (result.success) {
            if (typeof window.updateStatus === 'function') window.updateStatus(result.message || window.t('pending.mergeDone'));
            loadPendingItems();
            refreshPendingBtnState();
            if (window.TreeModule && window.TreeModule.loadFileTree) window.TreeModule.loadFileTree();
        } else if (typeof window.updateStatus === 'function') {
            window.updateStatus(result.message || window.t('pending.operationFailed'));
        }
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') window.updateStatus(e.message || String(e));
    });
}

function retryPendingItem(info) {
    var request;
    if (info.actionKind === 'retry_cascade' || info.actionKind === 'refresh_survey') request = window.api.retryCascadeTopic(info.topic);
    else if (info.actionKind === 'retry_convert') request = window.api.retryConvertFile(info.filePath);
    else if (info.actionKind === 'retry_ingest') request = window.api.retryIngest({ mode: 'full' });
    else return;
    if (typeof window.updateStatus === 'function') window.updateStatus(window.t('pending.retryStarted'));
    request.then(function(result) {
        if (result && result.success === false && typeof window.updateStatus === 'function') {
            window.updateStatus(result.message || window.t('pending.operationFailed'));
        }
        loadPendingItems();
        refreshPendingBtnState();
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') window.updateStatus(e.message || window.t('pending.operationFailed'));
        loadPendingItems();
    });
}

function dismissPendingItem(info) {
    var request;
    if (info.actionKind === 'retry_cascade') request = window.api.dismissCascadeFailure(info.topic);
    else if (info.actionKind === 'retry_convert') request = window.api.dismissConvertFailure(info.filePath);
    else return;
    request.then(function() { loadPendingItems(); refreshPendingBtnState(); }).catch(function() { loadPendingItems(); });
}

function resolvePendingTopicItem(filePath, topic, idx) {
    if (!window.api || !window.api.resolveTopic) return;
    window.api.resolveTopic(filePath, topic).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        } else {
            var msg = (result && result.message) ? result.message : window.t('pending.operationFailed');
            if (typeof window.updateStatus === 'function') window.updateStatus(msg);
            loadPendingItems();
        }
    }).catch(function(e) {
        console.warn('[PendingView] resolve topic failed:', e);
        loadPendingItems();
    });
}

function confirmPendingLink(fromPath, toPath, idx) {
    if (!window.api || !window.api.confirmLink) return;
    window.api.confirmLink(fromPath, toPath).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        } else {
            var msg = (result && result.message) ? result.message : window.t('pending.operationFailed');
            if (typeof window.updateStatus === 'function') window.updateStatus(msg);
            loadPendingItems();
        }
    }).catch(function(e) {
        console.warn('[PendingView] confirm link failed:', e);
        loadPendingItems();
    });
}

function confirmAllPendingLinks(idx) {
    if (!window.api || !window.api.confirmAllLinks) return;
    window.api.confirmAllLinks().then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
            refreshPendingBtnState();
        } else {
            loadPendingItems();
        }
    }).catch(function(e) {
        console.warn('[PendingView] confirm all links failed:', e);
        loadPendingItems();
    });
}

function rejectPendingLink(fromPath, toPath, idx) {
    if (!window.api || !window.api.rejectLink) return;
    window.api.rejectLink(fromPath, toPath).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        } else {
            loadPendingItems();
        }
    }).catch(function(e) {
        console.warn('[PendingView] reject link failed:', e);
        loadPendingItems();
    });
}

function removePendingItem(idx) {
    var itemEl = document.querySelector('.pending-item[data-pending-idx="' + idx + '"]');
    if (itemEl) {
        itemEl.style.transition = 'opacity 0.3s, transform 0.3s';
        itemEl.style.opacity = '0';
        itemEl.style.transform = 'translateX(20px)';
        setTimeout(function() {
            itemEl.remove();
            updatePendingCount();
            refreshPendingBtnState();
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        }, 300);
    }
}

function updatePendingCount() {
    var remaining = document.querySelectorAll('.pending-item').length;
    var countEl = document.getElementById('pending-view-count');
    if (countEl) countEl.textContent = window.t('common.pendingRemaining', { count: remaining });
    if (remaining === 0) {
        var listEl = document.getElementById('pending-view-list');
        if (listEl) listEl.innerHTML = '<div class="pending-view-empty">' + window.t('pending.allDoneCelebration') + '</div>';
    }
}

function refreshPendingBtnState() {
    if (!window.api || !window.api.getAllPending) return;
    window.api.getAllPending().then(function(result) {
        var count = (result && result.count) ? result.count : 0;
        var btn = document.getElementById('titlebar-pending-btn');
        if (btn) {
            var badge = btn.querySelector('.pending-badge');
            if (count > 0) {
                btn.classList.add('has-pending');
                btn.title = window.t('pending.todoBadge', { count: count });
                if (badge) {
                    badge.textContent = count > 99 ? '99+' : count;
                    badge.style.display = '';
                }
            } else {
                btn.classList.remove('has-pending');
                btn.title = window.t('pending.todoBadgeEmpty');
                if (badge) badge.style.display = 'none';
            }
            var inboxCount = document.getElementById('vault-inbox-count');
            if (inboxCount) inboxCount.textContent = count > 99 ? '99+' : String(count);
        }
    }).catch(function() {});
}

function _setButtonBusy(btn, busy, labelKey) {
    if (!btn) return;
    btn.disabled = !!busy;
    if (labelKey) btn.textContent = window.t(labelKey);
}

function runPendingHealthCheck() {
    var btn = document.getElementById('pending-lint-run-btn');
    if (!window.api || !window.api.runKbLint) return;
    _setButtonBusy(btn, true, 'pending.healthCheckRunning');
    window.api.runKbLint().then(function() {
        loadPendingItems();
        refreshPendingBtnState();
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('pending.loadFailed', { error: e.message || String(e) }));
        }
    }).finally(function() {
        _setButtonBusy(btn, false, 'pending.healthCheck');
    });
}

function scanPendingMergeCandidates() {
    var btn = document.getElementById('pending-merge-scan-btn');
    if (!window.api || !window.api.scanMergeCandidates) return;
    _setButtonBusy(btn, true, 'pending.scanningMergeCandidates');
    window.api.scanMergeCandidates().then(function(result) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('pending.mergeScanDone', { count: (result && result.candidate_count) || 0 }));
        }
        loadPendingItems();
        refreshPendingBtnState();
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') window.updateStatus(e.message || window.t('pending.operationFailed'));
    }).finally(function() {
        _setButtonBusy(btn, false, 'pending.scanMergeCandidates');
    });
}

function retryAllPendingSurveys() {
    var btn = document.getElementById('pending-cascade-retry-all-btn');
    if (!window.api || !window.api.retryAllCascadeFailures) return;
    _setButtonBusy(btn, true, 'pending.retrying');
    window.api.retryAllCascadeFailures().then(function(result) {
        if (typeof window.updateStatus === 'function') window.updateStatus((result && result.message) || window.t('pending.retryStarted'));
        loadPendingItems();
        refreshPendingBtnState();
    }).catch(function(e) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('pending.loadFailed', { error: e.message || String(e) }));
        }
    }).finally(function() {
        _setButtonBusy(btn, false, 'pending.retryAllSurveys');
    });
}

document.addEventListener('click', _handlePendingClick);
document.addEventListener('DOMContentLoaded', function() {
    var lintBtn = document.getElementById('pending-lint-run-btn');
    var mergeScanBtn = document.getElementById('pending-merge-scan-btn');
    var retryBtn = document.getElementById('pending-cascade-retry-all-btn');
    if (lintBtn && !lintBtn.dataset.pendingBound) {
        lintBtn.addEventListener('click', runPendingHealthCheck);
        lintBtn.dataset.pendingBound = '1';
    }
    if (mergeScanBtn && !mergeScanBtn.dataset.pendingBound) {
        mergeScanBtn.addEventListener('click', scanPendingMergeCandidates);
        mergeScanBtn.dataset.pendingBound = '1';
    }
    if (retryBtn && !retryBtn.dataset.pendingBound) {
        retryBtn.addEventListener('click', retryAllPendingSurveys);
        retryBtn.dataset.pendingBound = '1';
    }
});

window.togglePendingView = togglePendingView;
window.refreshPendingBtnState = refreshPendingBtnState;
window.loadPendingItems = loadPendingItems;

Object.defineProperty(window, '_pendingViewVisible', {
    get: function() { return _pendingViewVisible; },
    set: function(v) { _pendingViewVisible = v; },
    configurable: true
});

})();
