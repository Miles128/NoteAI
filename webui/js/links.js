window.LinksModule = (function() {
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
        return String(str).replace(/&/g, '&amp;').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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

        if (confirmedLinks.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            if (emptyEl) emptyEl.textContent = '暂无链接';
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

    function openLinkedFile(filePath) {
        if (window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(filePath);
        }
    }

    return {
        loadGraphView: loadGraphView,
        loadLinksData: loadLinksData,
        onDiscoverLinks: onDiscoverLinks,
        openLinkedFile: openLinkedFile,
    };
})();
