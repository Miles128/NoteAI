async function startWebDownload() {
    var btn = document.querySelector('#tab-0 .btn-primary');
    var originalText = btn ? btn.textContent : '开始下载';

    if (btn) {
        btn.disabled = true;
        btn.textContent = '下载中...';
    }

    try {
        var urlsEl = document.getElementById('web-urls');
        var aiToggleEl = document.getElementById('web-ai-toggle');
        var includeImagesEl = document.getElementById('web-include-images');

        var urls = urlsEl ? urlsEl.value.split('\n').map(function(u) { return u.trim(); }).filter(function(u) { return u; }) : [];
        var aiAssist = aiToggleEl ? aiToggleEl.checked : false;
        var includeImages = includeImagesEl ? includeImagesEl.checked : false;

        if (urls.length === 0) {
            alert('请输入要下载的URL');
            return;
        }

        var result = await window.api.start_web_download(urls, aiAssist, includeImages);

        if (result && result.success) {
            updateStatus('下载完成');
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree();
            }
        } else {
            updateStatus('下载失败: ' + (result?.message || '未知错误'));
        }
    } catch (e) {
        console.error('[Downloader] Download error:', e);
        alert('下载失败: ' + e.message);
        updateStatus('下载失败: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

function updateWebImageStatus() {
    saveDownloaderConfig();
}

function saveDownloaderConfig() {
    var aiToggle = document.getElementById('web-ai-toggle');
    var includeImages = document.getElementById('web-include-images');

    var config = {
        webAiAssist: aiToggle ? aiToggle.checked : false,
        webIncludeImages: includeImages ? includeImages.checked : true
    };

    localStorage.setItem('downloader-config', JSON.stringify(config));
}

function loadSavedConfig() {
    try {
        var saved = localStorage.getItem('downloader-config');
        if (saved) {
            var config = JSON.parse(saved);
            var aiToggle = document.getElementById('web-ai-toggle');
            var includeImages = document.getElementById('web-include-images');

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
    var urlsEl = document.getElementById('web-urls');
    if (urlsEl) {
        urlsEl.value = '';
    }
}

window.DownloaderModule = {
    startWebDownload: startWebDownload,
    updateWebImageStatus: updateWebImageStatus,
    saveDownloaderConfig: saveDownloaderConfig,
    loadSavedConfig: loadSavedConfig,
    clearUrls: clearUrls
};
