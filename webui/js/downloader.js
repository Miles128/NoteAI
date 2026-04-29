var _webDownloadUnlisten = null;
var _modalDragState = {
    isDragging: false,
    startX: 0,
    startY: 0,
    initialLeft: 0,
    initialTop: 0
};

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
    
    if (downloadBtn) {
        downloadBtn.disabled = true;
        downloadBtn.style.opacity = '0.5';
    }
    if (switchContainer) switchContainer.style.opacity = '0.5';
    if (switchLabel) switchLabel.style.opacity = '0.5';
    
    autoSaveModalConfig();
    
    try {
        updateStatus('正在下载...');
        updateProgress('web-progress', 0, '正在准备下载...');
        
        function handleDownloadEvent(event) {
            var data = event.payload;
            if (!data) return;
            
            console.log('[Downloader] Received event:', data.type);
            
            if (data.type === 'progress' && data.element_id === 'web-progress') {
                updateProgress('web-progress', data.progress || 0, data.message || '');
                updateStatus(data.message || '下载中...');
            } else if (data.type === 'web_download_complete') {
                var successCount = data.success_count || 0;
                var total = data.total || 0;
                updateProgress('web-progress', 1, '下载完成：' + successCount + '/' + total + ' 篇成功');
                updateStatus('下载完成：' + successCount + '/' + total + ' 篇成功');
                if (window.TreeModule && window.TreeModule.loadFileTree) {
                    window.TreeModule.loadFileTree();
                }
                
                if (downloadBtn) {
                    downloadBtn.disabled = false;
                    downloadBtn.style.opacity = '1';
                }
                if (switchContainer) switchContainer.style.opacity = '1';
                if (switchLabel) switchLabel.style.opacity = '1';
                
                alert('下载完成：' + successCount + '/' + total + ' 篇成功');
            } else if (data.type === 'web_download_error') {
                const errorMsg = data.error || '未知错误';
                updateProgress('web-progress', 0, '下载失败：' + errorMsg);
                updateStatus('下载失败：' + errorMsg);
                
                if (downloadBtn) {
                    downloadBtn.disabled = false;
                    downloadBtn.style.opacity = '1';
                }
                if (switchContainer) switchContainer.style.opacity = '1';
                if (switchLabel) switchLabel.style.opacity = '1';
                
                alert('下载失败：' + errorMsg);
            }
        }
        
        if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event) {
            const eventModule = window.__TAURI_INTERNALS__.event;
            if (eventModule && eventModule.listen) {
                if (_webDownloadUnlisten) {
                    try {
                        _webDownloadUnlisten();
                    } catch (e) {
                        console.warn('[Downloader] Failed to unlisten:', e);
                    }
                    _webDownloadUnlisten = null;
                }
                
                try {
                    console.log('[Downloader] Setting up event listener...');
                    const unlisten = await Promise.race([
                        eventModule.listen('python-event', handleDownloadEvent),
                        new Promise(function(_, reject) {
                            setTimeout(function() {
                                reject(new Error('Event listen timeout (1s)'));
                            }, 1000);
                        })
                    ]);
                    _webDownloadUnlisten = unlisten;
                    console.log('[Downloader] Event listener setup completed successfully');
                } catch (listenError) {
                    console.warn('[Downloader] Event listen failed or timed out:', listenError.message);
                    console.warn('[Downloader] Continuing without event listener - download will still work but progress may not update');
                }
            }
        }
        
        const apiTimeout = setTimeout(function() {
            console.warn('[Downloader] API call timed out after 15 seconds');
            updateStatus('下载调用超时，请检查网络连接');
            updateProgress('web-progress', 0, '下载调用超时');
            
            if (downloadBtn) {
                downloadBtn.disabled = false;
                downloadBtn.style.opacity = '1';
            }
            if (switchContainer) switchContainer.style.opacity = '1';
            if (switchLabel) switchLabel.style.opacity = '1';
            
            alert('下载调用超时，请检查网络连接后重试');
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
                alert('下载失败: ' + errMsg);
                
                if (downloadBtn) {
                    downloadBtn.disabled = false;
                    downloadBtn.style.opacity = '1';
                }
                if (switchContainer) switchContainer.style.opacity = '1';
                if (switchLabel) switchLabel.style.opacity = '1';
            }
        } catch (apiError) {
            clearTimeout(apiTimeout);
            throw apiError;
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        updateStatus('下载失败: ' + e.message);
        updateProgress('web-progress', 0, '下载失败: ' + e.message);
        alert('下载出错: ' + e.message);
        
        if (downloadBtn) {
            downloadBtn.disabled = false;
            downloadBtn.style.opacity = '1';
        }
        if (switchContainer) switchContainer.style.opacity = '1';
        if (switchLabel) switchLabel.style.opacity = '1';
    }
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
    autoSaveModalConfig,
    startDownloadFromModal
};
