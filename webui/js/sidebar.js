(function() { 'use strict';

function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var expandBtn = document.getElementById('sidebar-expand-btn');
    var resizer = document.getElementById('sidebar-resizer');
    if (!sidebar) return;
    if (sidebar.classList.contains('collapsed')) {
        sidebar.classList.remove('collapsed');
        if (expandBtn) expandBtn.style.display = 'none';
        if (resizer) resizer.style.display = '';
    } else {
        sidebar.classList.add('collapsed');
        if (expandBtn) expandBtn.style.display = 'flex';
        if (resizer) resizer.style.display = 'none';
    }
}

function _deactivatePendingBtn() {
    if (typeof window._pendingViewVisible !== 'undefined') {
        _pendingViewVisible = false;
    }
    var btn = document.getElementById('titlebar-pending-btn');
    if (btn) btn.classList.remove('active');
    var pendingView = document.getElementById('pending-view');
    if (pendingView) pendingView.style.display = 'none';
}

function showGraphHomeView() {
    var contentPanel = document.getElementById('content-panel');
    var previewPanel = document.getElementById('preview-panel');
    var contentArea = document.getElementById('content-area');
    var graphPanel = document.getElementById('graph-panel');
    var pendingView = document.getElementById('pending-view');
    if (contentPanel) contentPanel.style.display = 'flex';
    if (previewPanel) previewPanel.style.display = 'none';
    if (graphPanel) graphPanel.style.display = 'flex';
    if (contentArea) contentArea.style.display = 'none';
    if (pendingView) pendingView.style.display = 'none';
    var gh = document.getElementById('graph-home-view');
    if (gh) gh.style.display = 'none';
    _deactivatePendingBtn();
    updateHomeStats();
    if (window.Graph3Tier && window.Graph3Tier.load) {
        window.Graph3Tier.load();
    }
}

function updateHomeStats() {
    var fileCount = window.AppState.lastFileTreeData ? _countFiles(window.AppState.lastFileTreeData) : 0;
    var topicCount = window.AppState.lastFileTreeData ? _countTopicFolders(window.AppState.lastFileTreeData) : 0;

    // Home overlay stats
    var el1 = document.getElementById('home-stat-notes');
    var el2 = document.getElementById('home-stat-topics');
    var el3 = document.getElementById('home-stat-links');
    if (el1) el1.textContent = fileCount;
    if (el2) el2.textContent = topicCount;

    // Graph header stats
    var gs1 = document.getElementById('graph-stat-notes');
    var gs2 = document.getElementById('graph-stat-topics');
    var gs3 = document.getElementById('graph-stat-links');
    if (gs1) gs1.textContent = fileCount;
    if (gs2) gs2.textContent = topicCount;

    if (window.api && window.api.getLinkStats) {
        window.api.getLinkStats().then(function(result) {
            if (result && result.success) {
                var linkCount = result.confirmed || 0;
                if (el3) el3.textContent = linkCount;
                if (gs3) gs3.textContent = linkCount;
            }
        }).catch(function() {});
    }
}

function _countFiles(nodes) {
    if (!nodes) return 0;
    var count = 0;
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].type === 'file' && nodes[i].name && nodes[i].name.toLowerCase().endsWith('.md')) count++;
        if (nodes[i].children) count += _countFiles(nodes[i].children);
    }
    return count;
}

function _countTopicFolders(nodes) {
    if (!nodes) return 0;
    var count = 0;
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].type === 'folder') {
            var depth = (nodes[i].path.match(/\//g) || []).length;
            // Count only folders that are topic-like (inside Notes/ directory, depth >= 1)
            if (nodes[i].path.indexOf('Notes/') >= 0) count++;
        }
        if (nodes[i].children) count += _countTopicFolders(nodes[i].children);
    }
    return count;
}

function updateSidebarStats() {
    var el = document.getElementById('sidebar-status-tree');
    if (el) {
        var fileCount = window.AppState.lastFileTreeData ? _countFiles(window.AppState.lastFileTreeData) : 0;
        el.textContent = fileCount + ' 篇笔记';
    }
    var tagsEl = document.getElementById('sidebar-status-tags');
    if (tagsEl) {
        var tagCount = document.querySelectorAll('#sidebar-tags .sidebar-tag-group[data-tag-name]').length;
        tagsEl.textContent = tagCount + ' 个标签';
    }
    var graphEl = document.getElementById('sidebar-status-graph');
    if (graphEl) {
        var linkCount = document.querySelectorAll('#sidebar-graph .link-card.link-confirmed').length;
        graphEl.textContent = linkCount + ' 个链接';
    }
}

function setSidebarStatus(view, text, isActive) {
    var el = document.getElementById('sidebar-status-' + view);
    if (el) {
        el.textContent = text;
        if (isActive !== undefined) {
            el.classList.toggle('active', !!isActive);
        } else {
            el.classList.remove('active');
        }
    }
}

function switchSidebarView(view) {
    window.AppState.currentSidebarView = view;

    var sidebar = document.querySelector('.sidebar-left');
    var resizer = document.getElementById('sidebar-resizer');
    var tagInput = document.getElementById('sidebar-tag-input');

    document.querySelectorAll('.sidebar-pane').forEach(function(pane) {
        pane.classList.remove('is-active');
        pane.hidden = true;
    });
    document.querySelectorAll('.sidebar-dock-panel').forEach(function(dock) {
        dock.classList.remove('is-active');
        dock.hidden = true;
    });
    if (tagInput) tagInput.style.display = 'none';

    var activePane = document.getElementById('sidebar-pane-' + view);
    if (activePane) {
        activePane.classList.add('is-active');
        activePane.hidden = false;
    }
    var activeDock = document.querySelector('.sidebar-dock-panel[data-sidebar-dock="' + view + '"]');
    if (activeDock) {
        activeDock.classList.add('is-active');
        activeDock.hidden = false;
    }

    if (view === 'tree') {
        if (sidebar) sidebar.classList.remove('sidebar-narrow');
        if (resizer) resizer.style.display = '';
    } else if (view === 'tags') {
        if (sidebar) sidebar.classList.add('sidebar-narrow');
        if (resizer) resizer.style.display = 'none';
    } else if (view === 'graph') {
        if (sidebar) sidebar.classList.add('sidebar-narrow');
        if (resizer) resizer.style.display = 'none';
    }

    var contentPanel = document.getElementById('content-panel');
    var previewPanel = document.getElementById('preview-panel');
    var contentArea = document.getElementById('content-area');
    var graphPanel = document.getElementById('graph-panel');

    var isPreviewShowing = previewPanel && previewPanel.style.display !== 'none';

    if (isPreviewShowing) {
        if (contentPanel) contentPanel.style.display = 'none';
    } else {
        if (contentPanel) contentPanel.style.display = 'flex';
        if (window.AppState.selectedFilePath) {
            if (graphPanel) graphPanel.style.display = 'none';
            if (contentArea) contentArea.style.display = '';
        } else {
            if (contentArea) contentArea.style.display = 'none';
        }
    }

    if (view === 'tags') loadTagsView().then(function() { updateSidebarStats(); }).catch(function() {});
    if (view === 'graph' && window.LinksModule) { window.LinksModule.loadGraphView(); setTimeout(updateSidebarStats, 500); }

    // 联动知识图谱过滤
    if (window.Graph3Tier && window.Graph3Tier.load) {
        if (view === 'tags') {
            window.Graph3Tier.load('tag');
        } else if (view === 'graph') {
            window.Graph3Tier.load('all');
        } else if (view === 'tree') {
            window.Graph3Tier.load('topic');
        }
    }
    updateSidebarStats();
}

window.switchSidebarView = switchSidebarView;
window.updateSidebarStats = updateSidebarStats;
window.setSidebarStatus = setSidebarStatus;
window.showGraphHomeView = showGraphHomeView;
window.updateHomeStats = updateHomeStats;

window.toggleSidebar = toggleSidebar;
window._deactivatePendingBtn = _deactivatePendingBtn;

function _initSidebarDock() {
    var view = window.AppState.currentSidebarView || 'tree';
    switchSidebarView(view);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initSidebarDock);
} else {
    _initSidebarDock();
}

})();

