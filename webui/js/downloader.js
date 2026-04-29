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

function initDownloadEventListener() {
    console.log('[Downloader] Initializing event listener at page load...');
    
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event) {
        const eventModule = window.__TAURI_INTERNALS__.event;
        if (eventModule && eventModule.listen) {
            eventModule.listen('python-event', handleGlobalDownloadEvent).then(function(unlisten) {
                _webDownloadUnlisten = unlisten;
                console.log('[Downloader] Global event listener initialized successfully');
            }).catch(function(err) {
                console.error('[Downloader] Failed to initialize global event listener:', err);
            });
        }
    }
}

function handleGlobalDownloadEvent(event) {
    var data = event.payload;
    if (!data) return;
    
    console.log('[Downloader] Received global event:', data.type);
    
    if (data.type === 'progress' && data.element_id === 'web-progress') {
        handleProgressEvent(data);
    } else if (data.type === 'web_download_complete') {
        handleDownloadCompleteEvent(data);
    } else if (data.type === 'web_download_error') {
        handleDownloadErrorEvent(data);
    }
}

function handleProgressEvent(data) {
    var progress = data.progress || 0;
    var message = data.message || '';
    
    _downloadState.currentProgress = progress;
    _downloadState.currentMessage = message;
    
    updateProgress('web-progress', progress, message);
    updateStatus(message);
    
    if (progress > 0 && progress < 1) {
        if (_downloadState.totalUrls > 0) {
            var estimatedCurrent = Math.ceil(progress * _downloadState.totalUrls);
            if (estimatedCurrent > _downloadState.currentIndex) {
                _downloadState.currentIndex = estimatedCurrent;
            }
        }
    }
    
    updateModalProgressDisplay();
}

function handleDownloadCompleteEvent(data) {
    var successCount = data.success_count || 0;
    var total = data.total || 0;
    var results = data.data || [];
    
    _downloadState.isDownloading = false;
    _downloadState.completedUrls = results.filter(function(r) { return r.success; });
    _downloadState.failedUrls = results.filter(function(r) { return !r.success; });
    
    updateProgress('web-progress', 1, '下载完成：' + successCount + '/' + total + ' 篇成功');
    updateStatus('下载完成：' + successCount + '/' + total + ' 篇成功');
    
    if (window.TreeModule && window.TreeModule.loadFileTree) {
        window.TreeModule.loadFileTree();
    }
    
    resetDownloadButtonState();
    showDownloadResultsModal(successCount, total, results);
}

function handleDownloadErrorEvent(data) {
    var errorMsg = data.error || '未知错误';
    
    _downloadState.isDownloading = false;
    
    updateProgress('web-progress', 0, '下载失败：' + errorMsg);
    updateStatus('下载失败：' + errorMsg);
    
    resetDownloadButtonState();
    alert('下载失败：' + errorMsg);
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
    var message = '下载完成！\n\n';
    message += '成功: ' + successCount + '/' + total + ' 篇\n';
    
    if (_downloadState.completedUrls.length > 0) {
        message += '\n已保存的文件：\n';
        _downloadState.completedUrls.forEach(function(result, index) {
            if (result.file_path) {
                message += (index + 1) + '. ' + result.title + '\n';
                message += '   路径: ' + result.file_path + '\n';
            }
        });
    }
    
    if (_downloadState.failedUrls.length > 0) {
        message += '\n失败的文章：\n';
        _downloadState.failedUrls.forEach(function(result, index) {
            message += (index + 1) + '. ' + result.url + '\n';
            message += '   原因: ' + (result.error || '未知错误') + '\n';
        });
    }
    
    alert(message);
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
    
    modalContent.style.width = (currentWidth * 0.75 * 0.8) + 'px';
    modalContent.style.height = (currentHeight * 0.75 * 1.1) + 'px';
    
    const savedConfig = localStorage.getItem('downloader-config');
    if (savedConfig) {
        try {
            const config = JSON.parse(savedConfig);
            const modalIncludeImages = document.getElementById('modal-web-include-images');
            
            if (modalIncludeImages && config.webIncludeImages !== undefined) {
                modalIncludeImages.checked = config.webIncludeImages;
            }
        } catch (e) {
            console.warn('[Downloader] Failed to load config:', e);
        }
    }
    
    modal.classList.add('active');
    
    initModalDrag();
    
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
    
    localStorage.setItem('downloader-config', JSON.stringify(config));
}

async function startDownloadFromModal() {
    const urlsEl = document.getElementById('modal-urls');
    const urls = urlsEl ? urlsEl.value.split('\n').map(u => u.trim()).filter(u => u) : [];
    
    if (urls.length === 0) {
        alert('请输入至少一个 URL');
        return;
    }
    
    const includeImages = document.getElementById('modal-web-include-images');
    const includeImagesVal = includeImages ? includeImages.checked : false;
    
    const downloadBtn = document.getElementById('modal-download-btn');
    const switchContainer = document.querySelector('.switch-container');
    const switchLabel = document.querySelector('.switch-label');
    
    if (_downloadState.isDownloading) {
        alert('下载任务正在进行中，请稍后');
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
        
        updateStatus('正在准备下载...');
        updateProgress('web-progress', 0, '正在准备下载...');
        
        const apiTimeout = setTimeout(function() {
            console.warn('[Downloader] API call timed out after 15 seconds');
            if (_downloadState.isDownloading) {
                updateStatus('下载调用超时，请检查网络连接');
                updateProgress('web-progress', 0, '下载调用超时');
                resetDownloadButtonState();
                _downloadState.isDownloading = false;
                alert('下载调用超时，请检查网络连接后重试');
            }
        }, 15000);
        
        try {
            console.log('[Downloader] Calling start_web_download with urls:', urls);
            const result = await window.api.start_web_download(urls, false, includeImagesVal);
            console.log('[Downloader] API result:', result);
            
            clearTimeout(apiTimeout);
            
            if (result && result.success) {
                updateStatus('正在下载，请稍候...');
                updateProgress('web-progress', 0, '正在下载第 1 篇...');
            } else {
                const errMsg = result?.message || '未知错误';
                updateStatus('下载失败: ' + errMsg);
                updateProgress('web-progress', 0, '下载失败: ' + errMsg);
                resetDownloadButtonState();
                _downloadState.isDownloading = false;
                alert('下载失败: ' + errMsg);
            }
        } catch (apiError) {
            clearTimeout(apiTimeout);
            throw apiError;
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateStatus('下载失败: ' + e.message);
        updateProgress('web-progress', 0, '下载失败: ' + e.message);
        resetDownloadButtonState();
        _downloadState.isDownloading = false;
        alert('下载出错: ' + e.message);
    }
}

async function startWebDownload() {
    const btn = document.querySelector('#tab-0 .btn-primary');
    const originalText = btn ? btn.textContent : '开始下载';
    
    if (_downloadState.isDownloading) {
        alert('下载任务正在进行中，请稍后');
        return;
    }
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = '下载中...';
    }

    try {
        const urlsEl = document.getElementById('web-urls');
        const aiToggleEl = document.getElementById('web-ai-toggle');
        const includeImagesEl = document.getElementById('web-include-images');

        const urls = urlsEl ? urlsEl.value.split('\n').map(u => u.trim()).filter(u => u) : [];
        const aiAssist = aiToggleEl ? aiToggleEl.checked : false;
        const includeImages = includeImagesEl ? includeImagesEl.checked : false;

        if (urls.length === 0) {
            alert('请输入要下载的URL');
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

        updateStatus('正在下载...');
        updateProgress('web-progress', 0, '正在准备下载...');

        const result = await window.api.start_web_download(urls, aiAssist, includeImages);
        
        if (result && result.success) {
            updateStatus('正在下载，请稍候...');
        } else {
            updateStatus('下载失败: ' + (result?.message || '未知错误'));
            updateProgress('web-progress', 0, '下载失败: ' + (result?.message || '未知错误'));
            _downloadState.isDownloading = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateStatus('下载失败: ' + e.message);
        updateProgress('web-progress', 0, '下载失败: ' + e.message);
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
    
    localStorage.setItem('downloader-config', JSON.stringify(config));
}

function loadSavedConfig() {
    try {
        const saved = localStorage.getItem('downloader-config');
        if (saved) {
            const config = JSON.parse(saved);
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
    } catch (e) {
        console.warn('[Downloader] Failed to load config:', e);
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
    getDownloadState: function() { return _downloadState; }
};
