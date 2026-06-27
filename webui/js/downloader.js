(function() { 'use strict';

var _webDownloadUnlisten = null;
var _modalDragState = {
    isDragging: false,
    startX: 0,
    startY: 0,
    initialLeft: 0,
    initialTop: 0
};

var _downloadState = {
    isDownloading: false,
    totalUrls: 0,
    currentIndex: 0,
    completedUrls: [],
    failedUrls: [],
    currentProgress: 0,
    currentMessage: ''
};

var _downloadEventRetries = 0;
var _downloadEventMaxRetries = 20;

function initDownloadEventListener() {
    console.log('[Downloader] Initializing event listener...');
    
    var eventAPI = getTauriEventAPI();
    if (eventAPI) {
        _downloadEventRetries = 0;
        eventAPI.listen('python-event', handleGlobalDownloadEvent).then(function(unlisten) {
            _webDownloadUnlisten = unlisten;
            console.log('[Downloader] Event listener initialized successfully');
        }).catch(function(err) {
            console.error('[Downloader] Failed to initialize event listener:', err);
        });
    } else if (_downloadEventRetries < _downloadEventMaxRetries) {
        _downloadEventRetries++;
        console.warn('[Downloader] Tauri event API not ready, retrying in 500ms... (' + _downloadEventRetries + '/' + _downloadEventMaxRetries + ')');
        setTimeout(initDownloadEventListener, 500);
    } else {
        console.error('[Downloader] Tauri event API not available after max retries');
    }
}

function handleGlobalDownloadEvent(event) {
    var data = event.payload;
    if (!data) return;
    
    console.log('[Downloader] Event received:', JSON.stringify(data));
    
    if (data.type === 'progress' && data.element_id === 'web-progress') {
        handleProgressEvent(data);
    } else if (data.type === 'web_download_complete') {
        handleDownloadCompleteEvent(data);
    } else if (data.type === 'web_download_error') {
        handleDownloadErrorEvent(data);
    } else if (data.type === 'rss_poll_complete') {
        var imported = data.data && data.data.imported ? data.data.imported : 0;
        if (imported > 0) {
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('download.rssFetchAllDone', { count: imported }));
            }
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree(true);
            }
        }
    }
}

function handleProgressEvent(data) {
    var progress = data.progress || 0;
    var message = data.message || '';
    
    _downloadState.currentProgress = progress;
    _downloadState.currentMessage = message;
    
    updateProgress('web-progress', progress, message);
    updateStatus(message);
    
    if (progress > 0 && _downloadState.totalUrls > 0) {
        var estimatedCurrent = Math.ceil(progress * _downloadState.totalUrls);
        if (estimatedCurrent > _downloadState.currentIndex) {
            _downloadState.currentIndex = estimatedCurrent;
        }
    }
    
    updateModalProgressDisplay();
}

function handleDownloadCompleteEvent(data) {
    var successCount = data.success_count || 0;
    var total = data.total || 0;
    var results = data.data || [];
    
    _downloadState.isDownloading = false;
    _downloadState.currentProgress = 1;
    _downloadState.currentMessage = window.t('download.done', { success: successCount, total: total });
    _downloadState.completedUrls = results.filter(function(r) { return r.success; });
    _downloadState.failedUrls = results.filter(function(r) { return !r.success; });
    _downloadState.currentIndex = total;
    
    updateProgress('web-progress', 1, window.t('download.done', { success: successCount, total: total }));
    updateStatus(window.t('download.done', { success: successCount, total: total }));
    updateModalProgressDisplay();
    
    if (window.TreeModule && window.TreeModule.loadFileTree) {
        window.TreeModule.loadFileTree();
    }
    
    resetDownloadButtonState();
    showDownloadResultsModal(successCount, total, results);
}

function handleDownloadErrorEvent(data) {
    var errorMsg = data.error || window.t('common.unknownError');
    
    _downloadState.isDownloading = false;
    
    updateProgress('web-progress', 0, window.t('download.failed', { message: errorMsg }));
    updateStatus(window.t('download.failed', { message: errorMsg }));
    
    resetDownloadButtonState();
    alert(window.t('download.failed', { message: errorMsg }));
}

function updateModalProgressDisplay() {
    var progressBar = document.getElementById('modal-web-progress-fill');
    var progressText = document.getElementById('modal-web-status');
    
    if (progressBar) {
        var progressPercent = (_downloadState.currentProgress * 100).toFixed(1);
        progressBar.style.width = progressPercent + '%';
    }
    
    if (progressText && _downloadState.currentMessage) {
        progressText.textContent = _downloadState.currentMessage;
    }
}

function showDownloadResultsModal(successCount, total, results) {
    var statusEl = document.getElementById('modal-web-status');
    var progressFill = document.getElementById('modal-web-progress-fill');
    
    if (progressFill) {
        progressFill.style.width = '100%';
    }
    
    if (statusEl) {
        var statusText = window.t('download.done', { success: successCount, total: total });
        if (_downloadState.failedUrls.length > 0) {
            statusText += ' (' + _downloadState.failedUrls.length + ' failed)';
        }
        statusEl.textContent = statusText;
    }
    
    var urlInput = document.getElementById('modal-urls');
    if (urlInput) {
        var summaryLines = [];
        summaryLines.push('=== Download results ===');
        summaryLines.push('OK: ' + successCount + '/' + total);
        
        if (_downloadState.completedUrls.length > 0) {
            summaryLines.push('');
            summaryLines.push('-- Saved --');
            _downloadState.completedUrls.forEach(function(result, index) {
                summaryLines.push((index + 1) + '. ' + (result.title || window.t('download.unnamed')));
                if (result.file_path) {
                    summaryLines.push('   → ' + result.file_path);
                }
            });
        }
        
        if (_downloadState.failedUrls.length > 0) {
            summaryLines.push('');
            summaryLines.push('-- Failed --');
            _downloadState.failedUrls.forEach(function(result, index) {
                summaryLines.push((index + 1) + '. ' + (result.url || ''));
                summaryLines.push(window.t('download.reasonPrefix') + (result.error || window.t('common.unknownError')));
            });
        }
        
        urlInput.value = summaryLines.join('\n');
    }
}

function resetDownloadButtonState() {
    var downloadBtn = document.getElementById('modal-download-btn');
    var switchContainer = document.querySelector('.switch-container');
    var switchLabel = document.querySelector('.switch-label');
    
    if (downloadBtn) {
        downloadBtn.disabled = false;
        downloadBtn.style.opacity = '1';
    }
    if (switchContainer) switchContainer.style.opacity = '1';
    if (switchLabel) switchLabel.style.opacity = '1';
}

function initModalDrag() {
    const header = document.getElementById('download-modal-header');
    const modal = document.getElementById('download-modal-content');
    
    if (!header || !modal) return;
    
    header.style.cursor = 'move';
    header.style.userSelect = 'none';
    header.style.webkitUserSelect = 'none';
    
    function onMouseDown(e) {
        if (e.target.closest('.download-modal-close')) return;
        
        _modalDragState.isDragging = true;
        _modalDragState.startX = e.clientX;
        _modalDragState.startY = e.clientY;
        _modalDragState.initialLeft = modal.offsetLeft;
        _modalDragState.initialTop = modal.offsetTop;
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('selectstart', onSelectStart);
    }
    
    function onMouseMove(e) {
        if (!_modalDragState.isDragging) return;
        
        e.preventDefault();
        const deltaX = e.clientX - _modalDragState.startX;
        const deltaY = e.clientY - _modalDragState.startY;
        
        modal.style.position = 'absolute';
        modal.style.transform = 'none';
        modal.style.margin = '0';
        modal.style.left = (_modalDragState.initialLeft + deltaX) + 'px';
        modal.style.top = (_modalDragState.initialTop + deltaY) + 'px';
    }
    
    function onMouseUp() {
        _modalDragState.isDragging = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.removeEventListener('selectstart', onSelectStart);
    }
    
    function onSelectStart(e) {
        e.preventDefault();
        return false;
    }
    
    header.addEventListener('mousedown', onMouseDown);
}

function openDownloadModal() {
    const modal = document.getElementById('download-modal');
    const modalContent = document.getElementById('download-modal-content');
    
    modalContent.style.position = '';
    modalContent.style.transform = '';
    modalContent.style.margin = '';
    modalContent.style.left = '';
    modalContent.style.top = '';
    
    const mainWidth = window.innerWidth;
    const mainHeight = window.innerHeight;
    
    const currentWidth = Math.max(500, mainWidth / 2);
    const currentHeight = Math.max(400, mainHeight * 2 / 3);
    
    modalContent.style.width = (currentWidth * 0.72) + 'px';
    modalContent.style.height = (currentHeight * 0.75 * 1.1) + 'px';
    
    const savedConfig = window.Storage.getItem(window.Storage.KEYS.DOWNLOADER_CONFIG, null, { silent: true });
    if (savedConfig) {
        const modalIncludeImages = document.getElementById('modal-web-include-images');
        
        if (modalIncludeImages && savedConfig.webIncludeImages !== undefined) {
            modalIncludeImages.checked = savedConfig.webIncludeImages;
        }
    }
    
    modal.classList.add('active');
    
    initModalDrag();
    initRssTab();
    
    setTimeout(() => {
        const urlInput = document.getElementById('modal-urls');
        if (urlInput) urlInput.focus();
    }, 100);
}

function closeDownloadModal() {
    const modal = document.getElementById('download-modal');
    modal.classList.remove('active');
}

function autoSaveModalConfig() {
    const includeImages = document.getElementById('modal-web-include-images');
    
    const config = {
        webAiAssist: false,
        webIncludeImages: includeImages ? includeImages.checked : true
    };
    
    window.Storage.setItem(window.Storage.KEYS.DOWNLOADER_CONFIG, config);
}

async function startDownloadFromModal() {
    const urlsEl = document.getElementById('modal-urls');
    const urls = urlsEl ? urlsEl.value.split('\n').map(u => u.trim()).filter(u => u) : [];
    
    if (urls.length === 0) {
        alert(window.t('download.enterUrl'));
        return;
    }
    
    const includeImages = document.getElementById('modal-web-include-images');
    const includeImagesVal = includeImages ? includeImages.checked : false;
    
    const downloadBtn = document.getElementById('modal-download-btn');
    const switchContainer = document.querySelector('.switch-container');
    const switchLabel = document.querySelector('.switch-label');
    
    if (_downloadState.isDownloading) {
        alert(window.t('download.taskRunning'));
        return;
    }
    
    _downloadState.isDownloading = true;
    _downloadState.totalUrls = urls.length;
    _downloadState.currentIndex = 0;
    _downloadState.completedUrls = [];
    _downloadState.failedUrls = [];
    _downloadState.currentProgress = 0;
    _downloadState.currentMessage = '';
    
    if (downloadBtn) {
        downloadBtn.disabled = true;
        downloadBtn.style.opacity = '0.5';
    }
    if (switchContainer) switchContainer.style.opacity = '0.5';
    if (switchLabel) switchLabel.style.opacity = '0.5';
    
    autoSaveModalConfig();
    
    try {
        console.log('[Downloader] Starting download with', urls.length, 'URLs');
        
        updateProgress('web-progress', 0, window.t('download.preparing'));
        
        try {
            console.log('[Downloader] Calling start_web_download with urls:', urls);
            const result = await window.api.startWebDownload(urls, false, includeImagesVal);
            console.log('[Downloader] API result:', result);
            
            if (result && result.success) {
                updateProgress('web-progress', 0, window.t('download.progress', { current: 1, total: _downloadState.totalUrls }));
            } else {
                const errMsg = result?.message || window.t('common.unknownError');
                updateProgress('web-progress', 0, window.t('download.failed', { message: errMsg }));
                resetDownloadButtonState();
                _downloadState.isDownloading = false;
                alert(window.t('download.failed', { message: '' }).replace(': ', '') + errMsg);
            }
        } catch (apiError) {
            throw apiError;
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateProgress('web-progress', 0, window.t('download.failed', { message: e.message }));
        resetDownloadButtonState();
        _downloadState.isDownloading = false;
        alert(window.t('download.error', { message: e.message }));
    }
}

async function startWebDownload() {
    const btn = document.querySelector('#tab-0 .btn-primary');
    const originalText = btn ? btn.textContent : window.t('download.start');
    
    if (_downloadState.isDownloading) {
        alert(window.t('download.taskRunning'));
        return;
    }
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('download.downloading');
    }

    try {
        const urlsEl = document.getElementById('web-urls');
        const aiToggleEl = document.getElementById('web-ai-toggle');
        const includeImagesEl = document.getElementById('web-include-images');

        const urls = urlsEl ? urlsEl.value.split('\n').map(u => u.trim()).filter(u => u) : [];
        const aiAssist = aiToggleEl ? aiToggleEl.checked : false;
        const includeImages = includeImagesEl ? includeImagesEl.checked : false;

        if (urls.length === 0) {
            alert(window.t('download.enterUrlSingle'));
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
            return;
        }
        
        _downloadState.isDownloading = true;
        _downloadState.totalUrls = urls.length;
        _downloadState.currentIndex = 0;
        _downloadState.completedUrls = [];
        _downloadState.failedUrls = [];

        updateStatus(window.t('download.downloading'));
        updateProgress('web-progress', 0, window.t('download.preparing'));

        const result = await window.api.startWebDownload(urls, aiAssist, includeImages);
        
        if (result && result.success) {
            updateStatus(window.t('download.waiting'));
        } else {
            updateStatus(window.t('download.failed', { message: '' }).replace(': ', '') + (result?.message || window.t('common.unknownError')));
            updateProgress('web-progress', 0, window.t('download.failed', { message: result?.message || window.t('common.unknownError') }));
            _downloadState.isDownloading = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateStatus(window.t('download.failed', { message: '' }).replace(': ', '') + e.message);
        updateProgress('web-progress', 0, window.t('download.failed', { message: e.message }));
        _downloadState.isDownloading = false;
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

function updateWebImageStatus() {
    autoSaveConfig();
}

function autoSaveConfig() {
    const aiToggle = document.getElementById('web-ai-toggle');
    const includeImages = document.getElementById('web-include-images');
    
    const config = {
        webAiAssist: aiToggle ? aiToggle.checked : false,
        webIncludeImages: includeImages ? includeImages.checked : true
    };
    
    window.Storage.setItem(window.Storage.KEYS.DOWNLOADER_CONFIG, config);
}

function loadSavedConfig() {
    const config = window.Storage.getItem(window.Storage.KEYS.DOWNLOADER_CONFIG, null);
    if (config) {
        const aiToggle = document.getElementById('web-ai-toggle');
        const includeImages = document.getElementById('web-include-images');
        
        if (aiToggle && config.webAiAssist !== undefined) {
            aiToggle.checked = config.webAiAssist;
        }
        if (includeImages && config.webIncludeImages !== undefined) {
            includeImages.checked = config.webIncludeImages;
        }
        
        if (window.TreeModule) {
            if (window.TreeModule.updateWebAIStatus) {
                window.TreeModule.updateWebAIStatus();
            }
        }
    }
}

function clearUrls() {
    const urlsEl = document.getElementById('web-urls');
    if (urlsEl) {
        urlsEl.value = '';
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDownloadEventListener);
} else {
    initDownloadEventListener();
}

window.DownloaderModule = {
    startWebDownload,
    updateWebImageStatus,
    autoSaveConfig,
    loadSavedConfig,
    clearUrls,
    openDownloadModal,
    closeDownloadModal,
    autoSaveModalConfig,
    startDownloadFromModal,
    loadRssSubscriptions,
    getDownloadState: function() { return _downloadState; }
};

window.closeDownloadModal = closeDownloadModal;
window.startDownloadFromModal = startDownloadFromModal;

// ── RSS Tab ──
var _RSS_LEGACY_KEY = 'noteai_rss_subscriptions';

function _rssT(key, params) {
    return window.t ? window.t(key, params) : key;
}

function _escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function initRssTab() {
  var rssImportBtn = document.getElementById('ms-rss-import-btn');
  if (rssImportBtn && !rssImportBtn._rssBound) {
    rssImportBtn.addEventListener('click', startRssImport);
    rssImportBtn._rssBound = true;
  }
  var fetchAllBtn = document.getElementById('ms-rss-fetch-all-btn');
  if (fetchAllBtn && !fetchAllBtn._rssBound) {
    fetchAllBtn.addEventListener('click', fetchAllRssSubscriptions);
    fetchAllBtn._rssBound = true;
  }
  var transcriptBtn = document.getElementById('ms-transcript-import-btn');
  if (transcriptBtn && !transcriptBtn._trBound) {
    transcriptBtn.addEventListener('click', startTranscriptImport);
    transcriptBtn._trBound = true;
  }
  loadRssSubscriptions();
}

async function startRssImport() {
  var urlEl = document.getElementById('ms-rss-url');
  var maxEl = document.getElementById('ms-rss-max');
  var fetchEl = document.getElementById('ms-rss-fetch');
  var url = urlEl ? urlEl.value.trim() : '';
  if (!url) { alert(_rssT('download.rssPlaceholder')); return; }
  var maxItems = maxEl ? parseInt(maxEl.value, 10) || 10 : 10;
  var fetchArticles = fetchEl ? fetchEl.checked : true;
  var btn = document.getElementById('ms-rss-import-btn');
  if (btn) { btn.disabled = true; btn.textContent = _rssT('download.rssImporting'); }
  try {
    var result = await window.api.importRssFeed(url, maxItems, fetchArticles);
    if (result && result.success) {
      alert(result.message || _rssT('download.importRss'));
      if (urlEl) urlEl.value = '';
      await saveRssSubscription(url);
      if (window.TreeModule && window.TreeModule.loadFileTree) window.TreeModule.loadFileTree(true);
    } else {
      alert('RSS: ' + (result && result.message || _rssT('download.failed', { message: '' })));
    }
  } catch(e) { alert('RSS: ' + e.message); }
  finally { if (btn) { btn.disabled = false; btn.textContent = _rssT('download.importRss'); } }
}

async function fetchAllRssSubscriptions() {
  if (!window.api || !window.api.fetchAllRss) return;
  var btn = document.getElementById('ms-rss-fetch-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = _rssT('download.rssUpdating'); }
  try {
    var result = await window.api.fetchAllRss();
    if (!result || !result.success) {
      alert('RSS: ' + (result && result.message || _rssT('common.unknownError')));
      return;
    }
    var imported = 0;
    (result.results || []).forEach(function(r) { imported += r.imported || 0; });
    alert(imported > 0
      ? _rssT('download.rssFetchAllDone', { count: imported })
      : _rssT('download.rssFetchAllNone'));
    if (imported > 0 && window.TreeModule && window.TreeModule.loadFileTree) {
      window.TreeModule.loadFileTree(true);
    }
    await loadRssSubscriptions();
  } catch (e) {
    alert('RSS: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = _rssT('download.rssFetchAll'); }
  }
}

async function startTranscriptImport() {
  var titleEl = document.getElementById('ms-transcript-title');
  var sourceEl = document.getElementById('ms-transcript-source');
  var contentEl = document.getElementById('ms-transcript-content');
  var title = titleEl ? titleEl.value.trim() : '';
  var content = contentEl ? contentEl.value.trim() : '';
  if (!content) { alert('请输入转录内容'); return; }
  try {
    var result = await window.api.importTranscript(title, content, sourceEl ? sourceEl.value.trim() : '');
    if (result && result.success) {
      alert(result.message || '转录保存成功');
      if (titleEl) titleEl.value = '';
      if (sourceEl) sourceEl.value = '';
      if (contentEl) contentEl.value = '';
    } else { alert('保存失败: ' + (result && result.message || '未知错误')); }
  } catch(e) { alert('保存失败: ' + e.message); }
}

function getRssStorageKey() { return _RSS_LEGACY_KEY; }

async function _migrateLegacyRssSubscriptions() {
  if (!window.Storage || !window.api || !window.api.saveRssSubscription) return;
  var legacy = window.Storage.getItem(_RSS_LEGACY_KEY, [], { silent: true });
  if (!legacy || !legacy.length) return;
  for (var i = 0; i < legacy.length; i++) {
    var url = legacy[i];
    if (url) {
      try { await window.api.saveRssSubscription(url, ''); } catch (_e) {}
    }
  }
  window.Storage.setItem(_RSS_LEGACY_KEY, [], { silent: true });
}

async function loadRssSubscriptions() {
  if (!window.api || !window.api.listRssSubscriptions) {
    updateRssSubList([]);
    return;
  }
  await _migrateLegacyRssSubscriptions();
  try {
    var result = await window.api.listRssSubscriptions();
    var subs = (result && result.success && result.subscriptions) ? result.subscriptions : [];
    updateRssSubList(subs);
  } catch (_e) {
    updateRssSubList([]);
  }
}

async function saveRssSubscription(url) {
  if (!url || !window.api || !window.api.saveRssSubscription) return;
  try {
    await window.api.saveRssSubscription(url, '');
    await loadRssSubscriptions();
  } catch (_e) {}
}

async function removeRssSubscription(url) {
  if (!url || !window.api || !window.api.removeRssSubscription) return;
  try {
    await window.api.removeRssSubscription(url);
    await loadRssSubscriptions();
  } catch (e) {
    alert('RSS: ' + e.message);
  }
}

function updateRssSubList(subs) {
  var container = document.getElementById('ms-rss-sub-list');
  if (!container) return;
  if (!subs || subs.length === 0) {
    container.innerHTML = '<div class="rss-sub-empty">' + _escapeHtml(_rssT('download.rssNoSubscriptions')) + '</div>';
    return;
  }
  var html = '';
  subs.forEach(function(sub) {
    var url = (sub && sub.url) ? sub.url : String(sub || '');
    if (!url) return;
    var short = url.length > 50 ? url.substring(0, 50) + '...' : url;
    html += '<div class="rss-sub-item" data-url="' + encodeURIComponent(url) + '">';
    html += '<span class="rss-sub-url" title="' + _escapeHtml(url) + '">' + _escapeHtml(short) + '</span>';
    html += '<button type="button" class="rss-sub-remove" title="' + _escapeHtml(_rssT('download.rssRemove')) + '">✕</button>';
    html += '</div>';
  });
  container.innerHTML = html;
  container.querySelectorAll('.rss-sub-remove').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var row = btn.closest('.rss-sub-item');
      if (row && row.dataset.url) removeRssSubscription(decodeURIComponent(row.dataset.url));
    });
  });
}

window.removeRssSubscription = removeRssSubscription;

})();

