window.LinksModule = (function() {
    var _pendingLinksData = [];
    var _linkDiscoveryUnlisten = null;

    function Path_stem(p) {
        if (!p) return p;
        var parts = p.split('/');
        var name = parts[parts.length - 1];
        return name.replace(/\.[^.]+$/, '');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function escapeAttr(str) {
        if (!str) return '';
        return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/&/g, '&amp;');
    }

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

        html += '<div class="link-list" id="link-list"></div>';
        html += '<div class="link-empty" id="link-empty"></div>';
        html += '</div>';

        container.innerHTML = html;
        loadLinksData();
    }

    async function loadLinksData() {
        var listEl = document.getElementById('link-list');
        var emptyEl = document.getElementById('link-empty');
        if (!listEl) return;

        var selPath = window.AppState ? window.AppState.selectedFilePath : null;
        var result = await window.api.get_backlinks(selPath || '');
        if (!result || !result.success) {
            if (emptyEl) emptyEl.textContent = '无法加载链接数据';
            return;
        }

        var allLinks = result.links || [];
        var confirmedLinks = allLinks.filter(function(l) { return l.status === 'confirmed'; });
        var pendingLinks = allLinks.filter(function(l) { return l.status === 'pending'; });

        if (confirmedLinks.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            listEl.innerHTML = '';
        } else {
            if (emptyEl) emptyEl.style.display = 'none';

            var html = '';
            for (var i = 0; i < confirmedLinks.length; i++) {
                var link = confirmedLinks[i];
                var dirClass = link.direction === 'incoming' ? 'link-incoming' : 'link-outgoing';
                var fromPath = link.from || link.file || '';
                var toPath = link.to || link.other || '';
                var fromName = fromPath ? Path_stem(fromPath) : fromPath;
                var toName = toPath ? Path_stem(toPath) : toPath;

                html += '<div class="link-card ' + dirClass + ' link-confirmed">';
                html += '<div class="link-card-relation">';
                html += '<span class="link-node link-from" data-file-path="' + escapeAttr(fromPath) + '">' + escapeHtml(fromName) + '</span>';
                html += '<span class="link-arrow ' + dirClass + '">→</span>';
                html += '<span class="link-node link-to" data-file-path="' + escapeAttr(toPath) + '">' + escapeHtml(toName) + '</span>';
                html += '</div>';
                if (link.reason) {
                    html += '<div class="link-card-reason">' + escapeHtml(link.reason) + '</div>';
                }
                html += '</div>';
            }

            listEl.innerHTML = html;

            listEl.onclick = function(ev) {
                var node = ev.target.closest('.link-node');
                if (node && node.dataset.filePath) {
                    openLinkedFile(node.dataset.filePath);
                }
            };
        }

        loadPendingLinksPanel(pendingLinks);

        var currentView = window.AppState ? window.AppState.currentSidebarView : 'tree';
        if (currentView === 'graph' && pendingLinks.length > 0) {
            var pendingLinksPanel = document.getElementById('pending-links-panel');
            if (pendingLinksPanel) pendingLinksPanel.style.display = 'flex';
        }
    }

    function togglePendingLinksPanel() {
        var panel = document.getElementById('pending-links-panel');
        if (!panel) return;

        if (panel.style.display === 'none' || !panel.style.display) {
            panel.style.display = 'flex';
        } else {
            panel.style.display = 'none';
        }
    }

    function loadPendingLinksPanel(pendingLinks) {
        _pendingLinksData = pendingLinks || [];
        var listEl = document.getElementById('pending-links-list');
        var emptyEl = document.getElementById('pending-links-empty');
        if (!listEl) return;

        if (_pendingLinksData.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            listEl.innerHTML = '';
            return;
        }

        if (emptyEl) emptyEl.style.display = 'none';

        var html = '';
        for (var i = 0; i < _pendingLinksData.length; i++) {
            var link = _pendingLinksData[i];
            var dirClass = link.direction === 'incoming' ? 'link-incoming' : 'link-outgoing';
            var fromPath = link.from || link.file || '';
            var toPath = link.to || link.other || '';
            var fromName = fromPath ? Path_stem(fromPath) : fromPath;
            var toName = toPath ? Path_stem(toPath) : toPath;

            html += '<div class="link-card ' + dirClass + ' link-pending" data-from="' + escapeAttr(fromPath) + '" data-to="' + escapeAttr(toPath) + '">';
            html += '<div class="link-card-header">';
            html += '<span class="link-status-badge link-pending">待确认</span>';
            html += '<div class="link-card-actions">';
            html += '<button class="link-action-btn link-confirm-btn" data-action="confirm" title="确认">✓</button>';
            html += '<button class="link-action-btn link-reject-btn" data-action="reject" title="删除">✕</button>';
            html += '</div>';
            html += '</div>';
            html += '<div class="link-card-relation">';
            html += '<span class="link-node link-from" data-file-path="' + escapeAttr(fromPath) + '">' + escapeHtml(fromName) + '</span>';
            html += '<span class="link-arrow ' + dirClass + '">→</span>';
            html += '<span class="link-node link-to" data-file-path="' + escapeAttr(toPath) + '">' + escapeHtml(toName) + '</span>';
            html += '</div>';
            if (link.reason) {
                html += '<div class="link-card-reason">' + escapeHtml(link.reason) + '</div>';
            }
            html += '</div>';
        }

        listEl.innerHTML = html;

        listEl.onclick = function(ev) {
            var target = ev.target;
            var card = target.closest('.link-card');
            if (!card) {
                var node = target.closest('.link-node');
                if (node && node.dataset.filePath) {
                    openLinkedFile(node.dataset.filePath);
                }
                return;
            }
            var from = card.dataset.from || '';
            var to = card.dataset.to || '';
            if (target.dataset.action === 'confirm') {
                onConfirmLink(from, to);
            } else if (target.dataset.action === 'reject') {
                onRejectLink(from, to);
            }
        };
    }

    async function onDiscoverLinks() {
        var btn = document.getElementById('btn-discover-links');
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

        if (btn) { btn.disabled = true; btn.title = '检查中...'; }
        if (progressEl) progressEl.style.display = '';
        if (progressFill) progressFill.style.width = '5%';
        if (progressText) progressText.textContent = '正在测试 API 连接...';
        if (emptyEl) emptyEl.style.display = 'none';

        try {
            var connResult = await window.api.invoke('test_api_connection', {});
            if (!connResult || !connResult.success) {
                if (progressText) progressText.textContent = 'API 连接失败: ' + ((connResult && connResult.message) || '未知错误');
                if (btn) { btn.disabled = false; btn.title = '发现链接：AI 分析文章关联'; }
                return;
            }
        } catch (e) {
            if (progressText) progressText.textContent = 'API 连接测试出错: ' + (e.message || e);
            if (btn) { btn.disabled = false; btn.title = '发现链接：AI 分析文章关联'; }
            return;
        }

        if (btn) btn.title = '分析中...';
        if (progressFill) progressFill.style.width = '10%';
        if (progressText) progressText.textContent = '正在读取文件并构建候选对...';

        if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
        var _isTauri = !!(window.__TAURI__ || window.__TAURI_INTERNALS__);
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
                            if (btn) { btn.disabled = false; btn.title = '发现链接：AI 分析文章关联'; }
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
                if (btn) { btn.disabled = false; btn.title = '发现链接：AI 分析文章关联'; }
            }
        } catch (e) {
            if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
            if (progressText) progressText.textContent = '错误: ' + (e.message || e);
            if (btn) { btn.disabled = false; btn.title = '发现链接：AI 分析文章关联'; }
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
        if (window.AppState) window.AppState.linkFilter = filter;
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

    return {
        loadGraphView: loadGraphView,
        loadLinksData: loadLinksData,
        togglePendingLinksPanel: togglePendingLinksPanel,
        loadPendingLinksPanel: loadPendingLinksPanel,
        onDiscoverLinks: onDiscoverLinks,
        onConfirmLink: onConfirmLink,
        onRejectLink: onRejectLink,
        onConfirmAllLinks: onConfirmAllLinks,
        onLinkFilter: onLinkFilter,
        openLinkedFile: openLinkedFile,
        get pendingLinksData() { return _pendingLinksData; }
    };
})();
