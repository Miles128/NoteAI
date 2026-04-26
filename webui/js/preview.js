var currentPreviewData = null;
var isPreviewActive = false;
var _pdfCleanupFn = null;

function _cleanupPdf() {
    if (_pdfCleanupFn) {
        _pdfCleanupFn();
        _pdfCleanupFn = null;
    }
}

async function loadFilePreview(path, fileName) {
    var previewPanel = document.getElementById('preview-panel');
    var previewContent = document.getElementById('preview-content');
    var previewTitle = document.getElementById('preview-title');

    if (!previewPanel || !previewContent) return;

    _cleanupPdf();

    if (window.mdEditor && window.mdEditor.isActive) {
        exitEditMode();
    }

    isPreviewActive = true;

    if (previewTitle) {
        previewTitle.textContent = fileName;
    }

    previewContent.innerHTML =
        '<div class="preview-loading">' +
            '<div class="preview-spinner"></div>' +
            '<div>加载中...</div>' +
        '</div>';

    previewPanel.classList.add('active');
    showPreviewView();

    try {
        var result = await window.api.get_file_preview(path);

        if (result && result.success) {
            currentPreviewData = {
                path: path,
                name: fileName,
                type: result.type || 'markdown',
                content: result.content,
                metadata: result.metadata
            };

            renderPreviewContent(currentPreviewData);
        } else {
            showPreviewError('加载失败', result?.message || '无法读取文件');
        }
    } catch (e) {
        console.error('[Preview] Load error:', e);
        showPreviewError('加载失败', e.message);
    }
}

async function renderPdfPreview(filePath) {
    var previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    var port = window.api ? window.api.getApiPort() : window.location.port;
    var token = window.api ? window.api.getApiToken() : '';
    var baseUrl = window.location.origin || ('http://localhost:' + port);

    var pdfUrl = baseUrl + '/files/' + encodeURIComponent(filePath) + '?token=' + encodeURIComponent(token);

    previewContent.innerHTML = '<div class="pdf-viewer-container"><canvas id="pdf-canvas"></canvas></div>' +
        '<div class="pdf-controls">' +
            '<button class="pdf-btn" id="pdf-prev" title="上一页">‹</button>' +
            '<span class="pdf-page-info"><span id="pdf-page-num">1</span> / <span id="pdf-page-count">0</span></span>' +
            '<button class="pdf-btn" id="pdf-next" title="下一页">›</button>' +
            '<button class="pdf-btn" id="pdf-zoom-out" title="缩小">−</button>' +
            '<span class="pdf-zoom-info" id="pdf-zoom-info">100%</span>' +
            '<button class="pdf-btn" id="pdf-zoom-in" title="放大">+</button>' +
        '</div>';

    try {
        var pdfjsLib = window.pdfjsLib;
        if (!pdfjsLib) {
            var mod = await import(baseUrl + '/lib/pdfjs/build/pdf.min.mjs');
            pdfjsLib = mod;
            window.pdfjsLib = mod;
        }

        pdfjsLib.GlobalWorkerOptions.workerSrc = baseUrl + '/lib/pdfjs/build/pdf.worker.min.mjs';

        var loadingTask = pdfjsLib.getDocument({
            url: pdfUrl,
            withCredentials: false
        });
        var pdfDoc = await loadingTask.promise;
        var totalPages = pdfDoc.numPages;
        var currentPage = 1;
        var scale = 1.5;
        var rendering = false;

        document.getElementById('pdf-page-count').textContent = totalPages;

        var canvas = document.getElementById('pdf-canvas');
        var ctx = canvas.getContext('2d');

        function renderPage(num) {
            if (rendering) return;
            rendering = true;

            pdfDoc.getPage(num).then(function(page) {
                var viewport = page.getViewport({ scale: scale });
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                var renderContext = {
                    canvasContext: ctx,
                    viewport: viewport
                };

                page.render(renderContext).promise.then(function() {
                    rendering = false;
                    document.getElementById('pdf-page-num').textContent = num;
                    document.getElementById('pdf-zoom-info').textContent = Math.round(scale / 1.5 * 100) + '%';
                });
            });
        }

        renderPage(currentPage);

        document.getElementById('pdf-prev').addEventListener('click', function() {
            if (currentPage <= 1) return;
            currentPage--;
            renderPage(currentPage);
        });

        document.getElementById('pdf-next').addEventListener('click', function() {
            if (currentPage >= totalPages) return;
            currentPage++;
            renderPage(currentPage);
        });

        document.getElementById('pdf-zoom-in').addEventListener('click', function() {
            scale = Math.min(scale + 0.3, 5);
            renderPage(currentPage);
        });

        document.getElementById('pdf-zoom-out').addEventListener('click', function() {
            scale = Math.max(scale - 0.3, 0.5);
            renderPage(currentPage);
        });

        _pdfCleanupFn = function() {
            rendering = false;
            if (loadingTask) {
                try { loadingTask.destroy(); } catch(e) {}
            }
        };

    } catch (e) {
        console.error('[PDF.js] Render error:', e);
        var errMsg = e.message || String(e);
        if (e instanceof Error) errMsg = e.message;
        previewContent.innerHTML =
            '<div class="preview-error">' +
                '<div class="preview-error-title">PDF 渲染失败</div>' +
                '<div class="preview-error-message">' + escapeHtml(errMsg) + '</div>' +
            '</div>';
    }
}

function renderPreviewContent(previewData) {
    var previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    _cleanupPdf();

    var type = previewData.type;
    var content = previewData.content;
    var metadata = previewData.metadata;

    var previewHtml = '';

    if (metadata && type !== 'pdf') {
        previewHtml += '<div class="preview-file-info">';
        previewHtml += '<div class="preview-file-info-row"><span class="preview-file-info-label">类型:</span><span class="preview-file-info-value">' + escapeHtml(metadata.type || '未知') + '</span></div>';
        if (metadata.size) {
            previewHtml += '<div class="preview-file-info-row"><span class="preview-file-info-label">大小:</span><span class="preview-file-info-value">' + formatFileSize(metadata.size) + '</span></div>';
        }
        if (metadata.modified) {
            previewHtml += '<div class="preview-file-info-row"><span class="preview-file-info-label">修改时间:</span><span class="preview-file-info-value">' + formatModifiedTime(metadata.modified) + '</span></div>';
        }
        previewHtml += '</div>';
    }

    if (type === 'pdf') {
        previewContent.innerHTML = '';
        renderPdfPreview(previewData.path);
        var splitBtn = document.getElementById('preview-split-btn');
        if (splitBtn) splitBtn.style.display = 'none';
        return;
    }

    if (type === 'markdown' || type === 'text') {
        if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
            previewHtml += '<div class="preview-content">' + window.EditorModule.renderMarkdownPreview(content) + '</div>';
        } else {
            previewHtml += '<div class="preview-content"><pre>' + escapeHtml(content) + '</pre></div>';
        }
    } else if (type === 'image') {
        previewHtml +=
            '<div class="preview-content" style="display: flex; justify-content: center; align-items: center; padding: 20px;">' +
                '<img src="data:' + (metadata?.mime || 'image/png') + ';base64,' + content + '" style="max-width: 100%; max-height: 80vh; border-radius: 8px;" alt="Image">' +
            '</div>';
    } else if (type === 'code' || type === 'json' || type === 'xml' || type === 'html') {
        previewHtml += '<div class="preview-content"><pre><code class="language-' + type + '">' + escapeHtml(content) + '</code></pre></div>';
    } else {
        previewHtml += '<div class="preview-content"><pre>' + escapeHtml(content) + '</pre></div>';
    }

    previewContent.innerHTML = previewHtml;

    var splitBtn = document.getElementById('preview-split-btn');
    if (splitBtn) {
        splitBtn.style.display = (type === 'markdown' || type === 'text') ? '' : 'none';
    }

    if (typeof hljs !== 'undefined') {
        previewContent.querySelectorAll('pre code').forEach(function(block) {
            hljs.highlightElement(block);
        });
    }
}

function showPreviewError(title, message) {
    var previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    previewContent.innerHTML =
        '<div class="preview-error">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
                '<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>' +
            '</svg>' +
            '<div class="preview-error-title">' + escapeHtml(title) + '</div>' +
            '<div class="preview-error-message">' + escapeHtml(message) + '</div>' +
        '</div>';
}

function closePreview() {
    var previewPanel = document.getElementById('preview-panel');
    var previewContent = document.getElementById('preview-content');

    _cleanupPdf();

    if (window.mdEditor && window.mdEditor.isActive) {
        exitEditMode();
    }

    if (previewPanel) {
        previewPanel.classList.remove('active');
        previewPanel.classList.remove('editor-active');
    }

    if (previewContent) {
        previewContent.innerHTML =
            '<div class="preview-empty">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>' +
                    '<polyline points="14 2 14 8 20 8"></polyline>' +
                '</svg><div>选择一个文件查看预览</div>' +
            '</div>';
    }

    currentPreviewData = null;
    isPreviewActive = false;

    showContentView();
}

function backToContent() {
    _cleanupPdf();

    if (window.mdEditor && window.mdEditor.isActive) {
        exitEditMode();
    }
    showContentView();
}

window.PreviewModule = {
    get currentPreviewData() { return currentPreviewData; },
    set currentPreviewData(v) { currentPreviewData = v; },
    get isPreviewActive() { return isPreviewActive; },
    set isPreviewActive(v) { isPreviewActive = v; },
    loadFilePreview: loadFilePreview,
    renderPreviewContent: renderPreviewContent,
    showPreviewError: showPreviewError,
    closePreview: closePreview,
    backToContent: backToContent
};
