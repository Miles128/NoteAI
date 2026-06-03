(function() {
"use strict";
window.LinksModule = (function() {
    var _linkDiscoveryUnlisten = null;

    function loadGraphView() {
        var container = document.getElementById('sidebar-graph');
        if (!container) return;

        var html = '<div class="link-view">';
        html += '<div class="link-view-header">';
        html += '<span class="link-view-title">' + window.t('links.title') + '</span>';
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
        var result = await window.api.getBacklinks(selPath || '');
        if (!result || !result.success) {
            if (emptyEl) emptyEl.textContent = window.t('links.loadFailed');
            return;
        }

        var allLinks = result.links || [];
        var confirmedLinks = allLinks.filter(function(l) { return l.status === 'confirmed'; });

        if (confirmedLinks.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            if (emptyEl) emptyEl.textContent = window.t('links.empty');
            listEl.innerHTML = '';
        } else {
            if (emptyEl) emptyEl.style.display = 'none';

            var html = '';
            for (var i = 0; i < confirmedLinks.length; i++) {
                var link = confirmedLinks[i];
                var dirClass = link.direction === 'incoming' ? 'link-incoming' : 'link-outgoing';
                var fromPath = link.from || link.file || '';
                var toPath = link.to || link.other || '';
                var fromName = fromPath ? window.Path_stem(fromPath) : fromPath;
                var toName = toPath ? window.Path_stem(toPath) : toPath;

                html += '<div class="link-card ' + dirClass + ' link-confirmed">';
                html += '<div class="link-card-relation">';
                html += '<span class="link-node link-from" data-file-path="' + window.escapeAttr(fromPath) + '">' + window.escapeHtml(fromName) + '</span>';
                html += '<span class="link-arrow ' + dirClass + '">→</span>';
                html += '<span class="link-node link-to" data-file-path="' + window.escapeAttr(toPath) + '">' + window.escapeHtml(toName) + '</span>';
                html += '</div>';
                if (link.reason) {
                    html += '<div class="link-card-reason">' + window.escapeHtml(link.reason) + '</div>';
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
            var apiCfg = await window.api.getApiConfig();
            if (!apiCfg || !apiCfg.api_key) {
                alert(window.t('links.configureApiKey'));
                return;
            }
        } catch (e) {
            alert(window.t('links.apiConfigFailed') + (e.message || e));
            return;
        }

        if (btn) { btn.disabled = true; btn.title = window.t('links.checking'); }
        if (progressEl) progressEl.style.display = '';
        if (progressFill) progressFill.style.width = '5%';
        if (progressText) progressText.textContent = window.t('links.testingApi');
        if (emptyEl) emptyEl.style.display = 'none';

        try {
            var connResult = await window.api.invoke('test_api_connection', {});
            if (!connResult || !connResult.success) {
                if (progressText) progressText.textContent = window.t('links.apiFailed') + ((connResult && connResult.message) || window.t('common.unknownError'));
                if (btn) { btn.disabled = false; btn.title = window.t('sidebar.discoverLinksTitle'); }
                return;
            }
        } catch (e) {
            if (progressText) progressText.textContent = window.t('links.apiTestError') + (e.message || e);
            if (btn) { btn.disabled = false; btn.title = window.t('sidebar.discoverLinksTitle'); }
            return;
        }

        if (btn) btn.title = window.t('links.analyzing');
        if (progressFill) progressFill.style.width = '10%';
        if (progressText) progressText.textContent = window.t('links.buildingPairs');

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
                                    var msg = result.new_links > 0 ? window.t('links.discoverDone', { files: result.files_scanned || '?', count: result.new_links }) : window.t('links.discoverNone', { files: result.files_scanned || '?' });
                                    progressText.textContent = msg;
                                } else {
                                    progressText.textContent = result.message || window.t('links.discoverFailed');
                                }
                            }
                            if (btn) { btn.disabled = false; btn.title = window.t('sidebar.discoverLinksTitle'); }
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
            var startResult = await window.api.discoverLinks();
            if (!startResult || !startResult.success) {
                if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
                if (progressText) progressText.textContent = (startResult && startResult.message) || window.t('links.startFailed');
                if (btn) { btn.disabled = false; btn.title = window.t('sidebar.discoverLinksTitle'); }
            }
        } catch (e) {
            if (_linkDiscoveryUnlisten) { _linkDiscoveryUnlisten(); _linkDiscoveryUnlisten = null; }
            if (progressText) progressText.textContent = window.t('app.errorPrefix') + (e.message || e);
            if (btn) { btn.disabled = false; btn.title = window.t('sidebar.discoverLinksTitle'); }
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

window.onConfirmAllLinks = function() {
    if (window.api && window.api.confirmAllLinks) {
        window.api.confirmAllLinks().then(function(r) {
            if (r && r.success && window.LinksModule && window.LinksModule.loadLinksData) {
                window.LinksModule.loadLinksData();
            }
        }).catch(function(e) { console.error('[links] confirmAllLinks error:', e); });
    }
};

})();

