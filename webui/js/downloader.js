var _webDownloadUnlisten = null;
var _urlList = [];

function openDownloadModal() {
    const modal = document.getElementById('download-modal');
    const modalContent = document.getElementById('download-modal-content');
    
    const mainWidth = window.innerWidth;
    const mainHeight = window.innerHeight;
    
    modalContent.style.width = Math.max(500, mainWidth / 2) + 'px';
    modalContent.style.height = Math.max(400, mainHeight * 2 / 3) + 'px';
    
    const savedConfig = localStorage.getItem('downloader-config');
    if (savedConfig) {
        try {
            const config = JSON.parse(savedConfig);
            const modalAiToggle = document.getElementById('modal-web-ai-toggle');
            const modalIncludeImages = document.getElementById('modal-web-include-images');
            
            if (modalAiToggle && config.webAiAssist !== undefined) {
                modalAiToggle.checked = config.webAiAssist;
            }
            if (modalIncludeImages && config.webIncludeImages !== undefined) {
                modalIncludeImages.checked = config.webIncludeImages;
            }
        } catch (e) {
            console.warn('[Downloader] Failed to load config:', e);
        }
    }
    
    renderUrlList();
    modal.classList.add('active');
    
    setTimeout(() => {
        const urlInput = document.getElementById('url-input');
        if (urlInput) urlInput.focus();
    }, 100);
}

function closeDownloadModal() {
    const modal = document.getElementById('download-modal');
    modal.classList.remove('active');
}

function handleUrlInputKeydown(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        addUrlFromInput();
    }
}

function addUrlFromInput() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput ? urlInput.value.trim() : '';
    
    if (!url) {
        return;
    }
    
    const urls = url.split(/[\n,;\s]+/).filter(u => u.trim());
    
    urls.forEach(u => {
        const trimmedUrl = u.trim();
        if (trimmedUrl && isValidUrl(trimmedUrl)) {
            if (!_urlList.includes(trimmedUrl)) {
                _urlList.push(trimmedUrl);
            }
        }
    });
    
    if (urlInput) {
        urlInput.value = '';
    }
    
    renderUrlList();
}

function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

function getHostFromUrl(url) {
    try {
        const urlObj = new URL(url);
        return urlObj.hostname;
    } catch (_) {
        return url;
    }
}

function renderUrlList() {
    const listContainer = document.getElementById('url-list');
    const emptyState = document.getElementById('url-list-empty');
    
    if (!listContainer || !emptyState) return;
    
    if (_urlList.length === 0) {
        emptyState.style.display = 'flex';
        listContainer.classList.remove('has-items');
        listContainer.innerHTML = '';
        return;
    }
    
    emptyState.style.display = 'none';
    listContainer.classList.add('has-items');
    
    listContainer.innerHTML = _urlList.map((url, index) => `
        <div class="url-item" data-index="${index}">
            <div class="url-item-number">${index + 1}</div>
            <div class="url-item-content">
                <div class="url-item-url">${escapeHtml(url)}</div>
                <div class="url-item-host">${getHostFromUrl(url)}</div>
            </div>
            <button class="url-item-remove" onclick="removeUrl(${index})" title="移除">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 6 6 18"></path>
                    <path d="m6 6 12 12"></path>
                </svg>
            </button>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function removeUrl(index) {
    _urlList.splice(index, 1);
    renderUrlList();
}

function clearAllUrls() {
    _urlList = [];
    renderUrlList();
}

function updateModalWebAIStatus() {
    autoSaveModalConfig();
}

function autoSaveModalConfig() {
    const aiToggle = document.getElementById('modal-web-ai-toggle');
    const includeImages = document.getElementById('modal-web-include-images');
    
    const config = {
        webAiAssist: aiToggle ? aiToggle.checked : false,
        webIncludeImages: includeImages ? includeImages.checked : true
    };
    
    localStorage.setItem('downloader-config', JSON.stringify(config));
}

async function startDownloadFromModal() {
    if (_urlList.length === 0) {
        alert('请添加至少一个 URL');
        return;
    }
    
    const aiToggle = document.getElementById('modal-web-ai-toggle');
    const includeImages = document.getElementById('modal-web-include-images');
    
    const aiAssist = aiToggle ? aiToggle.checked : false;
    const includeImagesVal = includeImages ? includeImages.checked : false;
    
    const oldTextarea = document.getElementById('web-urls');
    if (oldTextarea) {
        oldTextarea.value = _urlList.join('\n');
    }
    
    const oldAiToggle = document.getElementById('web-ai-toggle');
    const oldIncludeImages = document.getElementById('web-include-images');
    if (oldAiToggle) oldAiToggle.checked = aiAssist;
    if (oldIncludeImages) oldIncludeImages.checked = includeImagesVal;
    
    closeDownloadModal();
    await startWebDownload();
}

async function startWebDownload() {
    const btn = document.querySelector('#tab-0 .btn-primary');
    const originalText = btn ? btn.textContent : '开始下载';
    
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
            return;
        }

        updateStatus('正在下载...');
        updateProgress('web-progress', 0, '正在准备下载...');

        if (window.__TAURI_INTERNALS__) {
            var listen = window.__TAURI_INTERNALS__.event?.listen;
            if (listen) {
                if (_webDownloadUnlisten) {
                    _webDownloadUnlisten();
                }
                _webDownloadUnlisten = await listen('python-event', function(event) {
                    var data = event.payload;
                    if (!data) return;

                    if (data.type === 'progress' && data.element_id === 'web-progress') {
                        updateProgress('web-progress', data.progress || 0, data.message || '');
                        updateStatus(data.message || '下载中...');
                    } else if (data.type === 'web_download_complete') {
                        var successCount = data.success_count || 0;
                        var total = data.total || 0;
                        updateProgress('web-progress', 1, '下载完成：' + successCount + '/' + total + ' 篇成功');
                        updateStatus('下载完成：' + successCount + '/' + total + ' 篇成功');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = originalText;
                        }
                        if (window.TreeModule && window.TreeModule.loadFileTree) {
                            window.TreeModule.loadFileTree();
                        }
                        if (_webDownloadUnlisten) {
                            _webDownloadUnlisten();
                            _webDownloadUnlisten = null;
                        }
                    } else if (data.type === 'web_download_error') {
                        updateProgress('web-progress', 0, '下载失败：' + (data.error || '未知错误'));
                        updateStatus('下载失败：' + (data.error || '未知错误'));
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = originalText;
                        }
                        if (_webDownloadUnlisten) {
                            _webDownloadUnlisten();
                            _webDownloadUnlisten = null;
                        }
                    }
                });
            }
        }

        const result = await window.api.start_web_download(urls, aiAssist, includeImages);
        
        if (result && result.success) {
            updateStatus('正在下载，请稍候...');
        } else {
            updateStatus('下载失败: ' + (result?.message || '未知错误'));
            updateProgress('web-progress', 0, '下载失败: ' + (result?.message || '未知错误'));
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateStatus('下载失败: ' + e.message);
        updateProgress('web-progress', 0, '下载失败: ' + e.message);
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

window.DownloaderModule = {
    startWebDownload,
    updateWebImageStatus,
    autoSaveConfig,
    loadSavedConfig,
    clearUrls,
    openDownloadModal,
    closeDownloadModal,
    handleUrlInputKeydown,
    addUrlFromInput,
    removeUrl,
    clearAllUrls,
    updateModalWebAIStatus,
    autoSaveModalConfig,
    startDownloadFromModal
};
