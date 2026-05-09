var _pendingViewVisible = false;
var _pendingData = null;

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
    var pendingView = document.getElementById('pending-view');
    var graphHome = document.getElementById('graph-home-view');
    var contentArea = document.getElementById('content-area');
    var previewPanel = document.getElementById('preview-panel');

    if (previewPanel) previewPanel.style.display = 'none';
    if (graphHome) graphHome.style.display = 'none';
    if (contentArea) contentArea.style.display = 'none';
    if (pendingView) pendingView.style.display = '';

    loadPendingItems();
}

function hidePendingView() {
    var pendingView = document.getElementById('pending-view');
    if (pendingView) pendingView.style.display = 'none';

    if (window.AppState.selectedFilePath) {
        var contentArea = document.getElementById('content-area');
        if (contentArea) contentArea.style.display = '';
    } else {
        var graphHome = document.getElementById('graph-home-view');
        if (graphHome) graphHome.style.display = '';
    }
}

function loadPendingItems() {
    var listEl = document.getElementById('pending-view-list');
    var countEl = document.getElementById('pending-view-count');
    if (!listEl) return;

    listEl.innerHTML = '<div class="pending-view-empty">加载中...</div>';

    if (!window.api || !window.api.get_all_pending) return;
    window.api.get_all_pending().then(function(result) {
        _pendingData = result;
        var items = (result && result.items) ? result.items : [];
        var count = (result && result.count) ? result.count : items.length;

        if (countEl) countEl.textContent = count + ' 项待处理';

        if (items.length === 0) {
            listEl.innerHTML = '<div class="pending-view-empty">所有事项已处理完毕 🎉</div>';
            return;
        }

        var html = '';
        items.forEach(function(item, idx) {
            if (item.type === 'topic') {
                html += renderPendingTopicItem(item, idx);
            } else if (item.type === 'link') {
                html += renderPendingLinkItem(item, idx);
            }
        });
        listEl.innerHTML = html;
    }).catch(function(e) {
        listEl.innerHTML = '<div class="pending-view-empty">加载失败: ' + escapeHtml(String(e)) + '</div>';
    });
}

function renderPendingTopicItem(item, idx) {
    var title = escapeHtml(item.title || Path_stem(item.file));
    var filePath = escapeAttr(item.file);
    var candidates = item.candidates || [];

    var html = '<div class="pending-item" data-pending-idx="' + idx + '">';
    html += '<span class="pending-item-type type-topic">主题确认</span>';
    html += '<div class="pending-item-title">' + title + '</div>';
    html += '<div class="pending-item-path">' + escapeHtml(item.file) + '</div>';

    if (candidates.length > 0) {
        html += '<div class="pending-item-candidates">';
        candidates.forEach(function(c) {
            html += '<button class="pending-candidate-btn" onclick="resolvePendingTopicItem(\'' + filePath + '\',\'' + escapeAttr(c) + '\',' + idx + ')">' + escapeHtml(c) + '</button>';
        });
        html += '</div>';
    }

    html += '<div class="pending-item-custom">';
    html += '<input type="text" id="pending-custom-input-' + idx + '" placeholder="输入自定义主题...">';
    html += '<button onclick="resolvePendingTopicCustom(\'' + filePath + '\',' + idx + ')">确认</button>';
    html += '</div>';

    html += '</div>';
    return html;
}

function renderPendingLinkItem(item, idx) {
    var source = escapeHtml(item.source || '');
    var target = escapeHtml(item.target || '');
    var context = escapeHtml(item.context || '');

    var html = '<div class="pending-item" data-pending-idx="' + idx + '">';
    html += '<span class="pending-item-type type-link">链接确认</span>';
    html += '<div class="pending-item-title">' + source + ' → ' + target + '</div>';
    if (context) {
        html += '<div class="pending-item-path">' + context + '</div>';
    }
    html += '<div class="pending-item-actions">';
    html += '<button onclick="confirmPendingLink(\'' + escapeAttr(item.source) + '\',\'' + escapeAttr(item.target) + '\',' + idx + ')">确认链接</button>';
    html += '<button class="btn-reject" onclick="rejectPendingLink(\'' + escapeAttr(item.source) + '\',\'' + escapeAttr(item.target) + '\',' + idx + ')">拒绝</button>';
    html += '</div>';
    html += '</div>';
    return html;
}

function resolvePendingTopicItem(filePath, topic, idx) {
    if (!window.api || !window.api.resolve_topic) return;
    window.api.resolve_topic(filePath, topic).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        }
    }).catch(function(e) {
        console.warn('[PendingView] resolve topic failed:', e);
    });
}

function resolvePendingTopicCustom(filePath, idx) {
    var input = document.getElementById('pending-custom-input-' + idx);
    if (!input || !input.value.trim()) return;
    resolvePendingTopicItem(filePath, input.value.trim(), idx);
}

function confirmPendingLink(fromPath, toPath, idx) {
    if (!window.api || !window.api.confirm_link) return;
    window.api.confirm_link(fromPath, toPath).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        }
    }).catch(function(e) {
        console.warn('[PendingView] confirm link failed:', e);
    });
}

function rejectPendingLink(fromPath, toPath, idx) {
    if (!window.api || !window.api.reject_link) return;
    window.api.reject_link(fromPath, toPath).then(function(result) {
        if (result && result.success) {
            removePendingItem(idx);
        }
    }).catch(function(e) {
        console.warn('[PendingView] reject link failed:', e);
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
    if (countEl) countEl.textContent = remaining + ' 项待处理';
    if (remaining === 0) {
        var listEl = document.getElementById('pending-view-list');
        if (listEl) listEl.innerHTML = '<div class="pending-view-empty">所有事项已处理完毕 🎉</div>';
    }
}

function refreshPendingBtnState() {
    if (!window.api || !window.api.get_all_pending) return;
    window.api.get_all_pending().then(function(result) {
        var count = (result && result.count) ? result.count : 0;
        var btn = document.getElementById('titlebar-pending-btn');
        if (btn) {
            if (count > 0) {
                btn.classList.add('has-pending');
                btn.title = '待办事项 (' + count + ')';
            } else {
                btn.classList.remove('has-pending');
                btn.title = '待办事项';
            }
        }
    }).catch(function() {});
}

window.togglePendingView = togglePendingView;
window.refreshPendingBtnState = refreshPendingBtnState;
window.loadPendingItems = loadPendingItems;
