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
    // Hide ALL other right-panel views — no splits
    var views = ['graph-home-view', 'graph-panel', 'content-area', 'preview-panel',
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
        // Default back to knowledge graph
        var contentPanel = document.getElementById('content-panel');
        var graphPanel = document.getElementById('graph-panel');
        if (contentPanel) contentPanel.style.display = 'flex';
        if (graphPanel) graphPanel.style.display = 'flex';
        window.updateHomeStats();
        if (window.Graph3Tier && window.Graph3Tier.load) {
            window.Graph3Tier.load();
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
        var topicOpts = (result && result.topic_options) ? result.topic_options : [];

        if (topicOpts.length) {
            _allTopics = topicOpts;
        }

        if (countEl) countEl.textContent = window.t('common.pendingCount', { count: count });

        renderPendingList(items, listEl);

        if (!topicOpts.length && items.some(function(item) { return item.type === 'topic'; })) {
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
        }
    });
    listEl.innerHTML = html || '<div class="pending-view-empty">' + window.t('pending.allDone') + '</div>';
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
    var labelKey = kind === 'lint' ? 'pending.typeLint' : (kind === 'cascade' ? 'pending.typeCascade' : 'pending.typeConvert');
    var title = item.message || item.topic || item.file || item.file_path || item.error || '';
    var detail = item.file_path || item.file || item.topic || item.error || '';
    if (kind === 'cascade' && item.error) detail = item.error;
    if (kind === 'convert' && item.error) detail = (item.file || '') + (item.file && item.error ? ' · ' : '') + item.error;
    var html = '<div class="pending-item pending-item-info" data-pending-idx="' + idx + '">';
    html += '<span class="pending-item-type type-' + kind + '">' + window.t(labelKey) + '</span>';
    html += '<div class="pending-item-title">' + window.escapeHtml(title || window.t('pending.itemNeedsReview')) + '</div>';
    if (detail && detail !== title) {
        html += '<div class="pending-item-path">' + window.escapeHtml(detail) + '</div>';
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
        source: decodeURIComponent(item.getAttribute('data-source') || ''),
        target: decodeURIComponent(item.getAttribute('data-target') || '')
    };
}

function _handlePendingClick(e) {
    var btn = e.target.closest('[data-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-action');
    var info = _findPendingItem(btn);
    if (!info) return;

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
    }
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

function retryAllPendingSurveys() {
    var btn = document.getElementById('pending-cascade-retry-all-btn');
    if (!window.api || !window.api.retryAllCascadeFailures) return;
    _setButtonBusy(btn, true, 'pending.retrying');
    window.api.retryAllCascadeFailures().then(function() {
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
    var retryBtn = document.getElementById('pending-cascade-retry-all-btn');
    if (lintBtn && !lintBtn.dataset.pendingBound) {
        lintBtn.addEventListener('click', runPendingHealthCheck);
        lintBtn.dataset.pendingBound = '1';
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
