function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g,'&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

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

function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _deactivatePendingBtn() {
    if (typeof _pendingViewVisible !== 'undefined') {
        _pendingViewVisible = false;
    }
    var btn = document.getElementById('titlebar-pending-btn');
    if (btn) btn.classList.remove('active');
}

function showGraphHomeView() {
    var contentPanel = document.getElementById('content-panel');
    var previewPanel = document.getElementById('preview-panel');
    var graphHome = document.getElementById('graph-home-view');
    var contentArea = document.getElementById('content-area');
    var graphPanel = document.getElementById('graph-panel');
    var pendingView = document.getElementById('pending-view');
    if (contentPanel) contentPanel.style.display = 'flex';
    if (previewPanel) previewPanel.style.display = 'none';
    if (graphPanel) graphPanel.style.display = 'none';
    if (graphHome) graphHome.style.display = '';
    if (contentArea) contentArea.style.display = 'none';
    if (pendingView) pendingView.style.display = 'none';
    _deactivatePendingBtn();
    updateHomeStats();
}

function updateHomeStats() {
    var fileCount = window.AppState.lastFileTreeData ? _countFiles(window.AppState.lastFileTreeData) : 0;
    var el1 = document.getElementById('home-stat-notes');
    var el2 = document.getElementById('home-stat-topics');
    var el3 = document.getElementById('home-stat-links');
    if (el1) el1.textContent = fileCount;

    if (window.api && window.api.get_topic_tree) {
        window.api.get_topic_tree().then(function(result) {
            if (result && result.topics) {
                var count = 0;
                function countTopics(nodes) {
                    if (!nodes) return;
                    for (var i = 0; i < nodes.length; i++) {
                        count++;
                        if (nodes[i].children) countTopics(nodes[i].children);
                    }
                }
                countTopics(result.topics);
                if (el2) el2.textContent = count;
            }
        }).catch(function() {});
    }

    if (window.api && window.api.get_relation_graph) {
        window.api.get_relation_graph().then(function(result) {
            if (result && result.edges) {
                var linkCount = 0;
                for (var i = 0; i < result.edges.length; i++) {
                    if (result.edges[i].type === 'link') linkCount++;
                }
                if (el3) el3.textContent = linkCount;
            }
        }).catch(function() {});
    }
}

function Path_stem(p) {
    if (!p) return p;
    var parts = p.split('/');
    var name = parts[parts.length - 1];
    var dotIdx = name.lastIndexOf('.');
    return dotIdx > 0 ? name.substring(0, dotIdx) : name;
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

    var fileTree = document.getElementById('file-tree');
    var sidebarTags = document.getElementById('sidebar-tags');
    var sidebarGraph = document.getElementById('sidebar-graph');
    var sidebar = document.querySelector('.sidebar-left');
    var resizer = document.getElementById('sidebar-resizer');

    var footerTree = document.getElementById('sidebar-footer-tree');
    var footerTags = document.getElementById('sidebar-footer-tags');
    var footerGraph = document.getElementById('sidebar-footer-graph');

    var tagInput = document.getElementById('sidebar-tag-input');

    var views = [fileTree, sidebarTags, sidebarGraph];
    var footers = [footerTree, footerTags, footerGraph];

    views.forEach(function(v) { if (v) v.style.display = 'none'; });
    footers.forEach(function(f) { if (f) f.style.display = 'none'; });
    if (tagInput) tagInput.style.display = 'none';

    if (view === 'tree') {
        if (fileTree) fileTree.style.display = '';
        if (footerTree) footerTree.style.display = '';
        if (sidebar) sidebar.classList.remove('sidebar-narrow');
        if (resizer) resizer.style.display = '';
    } else if (view === 'tags') {
        if (sidebarTags) sidebarTags.style.display = '';
        if (footerTags) footerTags.style.display = '';
        if (sidebar) sidebar.classList.add('sidebar-narrow');
        if (resizer) resizer.style.display = 'none';
    } else if (view === 'graph') {
        if (sidebarGraph) sidebarGraph.style.display = '';
        if (footerGraph) footerGraph.style.display = '';
        if (sidebar) sidebar.classList.add('sidebar-narrow');
        if (resizer) resizer.style.display = 'none';
    }

    var contentPanel = document.getElementById('content-panel');
    var previewPanel = document.getElementById('preview-panel');
    var graphHome = document.getElementById('graph-home-view');
    var contentArea = document.getElementById('content-area');

    var isPreviewShowing = previewPanel && previewPanel.style.display !== 'none';

    if (isPreviewShowing) {
        if (contentPanel) contentPanel.style.display = 'none';
    } else {
        if (contentPanel) contentPanel.style.display = 'flex';
        if (window.AppState.selectedFilePath) {
            if (graphHome) graphHome.style.display = 'none';
            if (contentArea) contentArea.style.display = '';
        } else {
            if (graphHome) graphHome.style.display = '';
            if (contentArea) contentArea.style.display = 'none';
        }
    }

    if (view === 'tags') loadTagsView().then(function() { updateSidebarStats(); }).catch(function() {});
    if (view === 'graph' && window.LinksModule) { window.LinksModule.loadGraphView(); setTimeout(updateSidebarStats, 500); }
    updateSidebarStats();
}

window.switchSidebarView = switchSidebarView;
window.updateSidebarStats = updateSidebarStats;
window.setSidebarStatus = setSidebarStatus;
window.showGraphHomeView = showGraphHomeView;
window.updateHomeStats = updateHomeStats;
