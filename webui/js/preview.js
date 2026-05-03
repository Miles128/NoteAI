let currentPreviewData = null;
let isPreviewActive = false;
let currentLoadRequestId = 0;
var pdfViewerState = null;

function generateLoadRequestId() {
    currentLoadRequestId += 1;
    return currentLoadRequestId;
}

function showContentView() {
    const contentPanel = document.getElementById('content-panel');
    const previewPanel = document.getElementById('preview-panel');
    const titlebarFileName = document.getElementById('titlebar-file-name');
    const titlebarSplitBtn = document.getElementById('titlebar-split-btn');
    const titlebarCloseBtn = document.getElementById('titlebar-close-preview-btn');
    const titlebarSeparator = document.getElementById('titlebar-preview-separator');

    if (contentPanel) contentPanel.style.display = 'flex';
    if (previewPanel) previewPanel.style.display = 'none';
    if (titlebarFileName) {
        titlebarFileName.style.display = 'none';
        titlebarFileName.textContent = '';
    }
    if (titlebarSplitBtn) titlebarSplitBtn.style.display = 'none';
    if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'none';
    if (titlebarSeparator) titlebarSeparator.style.display = 'none';
}

function showPreviewView() {
    const contentPanel = document.getElementById('content-panel');
    const previewPanel = document.getElementById('preview-panel');

    if (contentPanel) contentPanel.style.display = 'none';
    if (previewPanel) previewPanel.style.display = 'flex';
}

function updateTitlebarFileName(fileName, isMarkdown) {
    const titlebarFileName = document.getElementById('titlebar-file-name');
    const titlebarCloseBtn = document.getElementById('titlebar-close-preview-btn');
    const titlebarSeparator = document.getElementById('titlebar-preview-separator');
    
    if (fileName) {
        if (titlebarFileName) {
            titlebarFileName.textContent = fileName;
            titlebarFileName.style.display = 'block';
        }
        if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'flex';
        if (titlebarSeparator) titlebarSeparator.style.display = 'block';
    } else {
        if (titlebarFileName) {
            titlebarFileName.style.display = 'none';
            titlebarFileName.textContent = '';
        }
        if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'none';
        if (titlebarSeparator) titlebarSeparator.style.display = 'none';
    }
}

function showEditButton(show) {
    const splitBtn = document.getElementById('titlebar-split-btn');
    if (splitBtn) {
        splitBtn.style.display = show ? 'flex' : 'none';
    }
}

async function loadFilePreview(path, fileName) {
    const requestId = generateLoadRequestId();
    
    const previewPanel = document.getElementById('preview-panel');
    const previewContent = document.getElementById('preview-content');
    const previewTitle = document.getElementById('preview-file-name');

    if (!previewPanel || !previewContent) {
        console.error('[Preview] Missing DOM elements');
        return;
    }

    if (window.TiptapEditor && window.TiptapEditor.isActive) {
        if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
            window.TiptapEditorModule.hideEditorUI();
        }
    }

    if (window.mdEditor && window.mdEditor.isActive) {
        if (window.EditorModule && window.EditorModule.destroyCodeMirrorEditor) {
            window.EditorModule.destroyCodeMirrorEditor();
        }
    }

    isPreviewActive = true;

    if (previewTitle) {
        previewTitle.textContent = fileName;
    }

    previewContent.style.display = 'block';
    previewContent.innerHTML = `
        <div class="preview-loading">
            <div class="preview-spinner"></div>
            <div>加载中...</div>
        </div>
    `;

    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';

    previewPanel.classList.add('active');
    showPreviewView();

    try {
        const result = await window.api.read_note_file(path);
        
        if (requestId !== currentLoadRequestId) {
            return;
        }
        
        if (result && result.success) {
            const fileType = result.type || 'markdown';
            const isMarkdown = fileType === 'markdown' || fileName.toLowerCase().endsWith('.md');
            const isPdf = fileType === 'pdf' || fileName.toLowerCase().endsWith('.pdf');
            
            currentPreviewData = {
                path: path,
                name: fileName,
                type: fileType,
                content: result.content,
                metadata: result.metadata,
                pdfData: result
            };

            updateTitlebarFileName(fileName, isMarkdown);
            
            if (isPdf) {
                showEditButton(false);
                await loadPdfViewer(path, fileName, requestId);
            } else if (isMarkdown) {
                if (window.TiptapEditorModule && window.TiptapEditorModule.openMarkdownInEditor) {
                    try {
                        const editorReady = await window.TiptapEditorModule.openMarkdownInEditor(
                            result.content,
                            path
                        );
                        
                        if (requestId !== currentLoadRequestId) {
                            if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                                window.TiptapEditorModule.hideEditorUI();
                            }
                            return;
                        }
                        
                        if (!editorReady) {
                            showEditButton(false);
                            renderPreviewContent(currentPreviewData);
                        } else {
                            showEditButton(false);
                        }
                    } catch (tiptapErr) {
                        console.error('[Preview] Tiptap error:', tiptapErr);
                        showEditButton(false);
                        renderPreviewContent(currentPreviewData);
                    }
                } else {
                    showEditButton(false);
                    renderPreviewContent(currentPreviewData);
                }
            } else {
                showEditButton(false);
                renderPreviewContent(currentPreviewData);
            }
        } else {
            showPreviewError('加载失败', result?.message || '无法读取文件');
        }
    } catch (e) {
        console.error('[Preview] Load error:', e);
        if (requestId === currentLoadRequestId) {
            showPreviewError('加载失败', e.message);
        }
    }
}

async function loadPdfViewer(path, fileName, requestId) {
    var previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    previewContent.innerHTML = `
        <div class="pdf-viewer-container">
            <div class="pdf-toolbar">
                <div class="pdf-toolbar-left">
                    <span class="pdf-file-name">${escapeHtml(fileName)}</span>
                </div>
                <div class="pdf-toolbar-center">
                    <button class="pdf-nav-btn" id="pdf-prev-btn" title="上一页">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                    </button>
                    <span class="pdf-page-info"><span id="pdf-page-num">1</span> / <span id="pdf-page-count">0</span></span>
                    <button class="pdf-nav-btn" id="pdf-next-btn" title="下一页">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                    </button>
                </div>
                <div class="pdf-toolbar-right">
                    <button class="pdf-zoom-btn" id="pdf-zoom-out-btn" title="缩小">−</button>
                    <span class="pdf-zoom-level" id="pdf-zoom-level">100%</span>
                    <button class="pdf-zoom-btn" id="pdf-zoom-in-btn" title="放大">+</button>
                </div>
            </div>
            <div class="pdf-canvas-wrapper" id="pdf-canvas-wrapper">
                <canvas id="pdf-render-canvas"></canvas>
            </div>
        </div>
    `;

    previewContent.style.display = 'flex';
    previewContent.style.flexDirection = 'column';
    previewContent.style.padding = '0';
    previewContent.style.overflow = 'hidden';

    try {
        var rawResult = await window.api.read_file_raw(path);
        if (requestId !== currentLoadRequestId) return;

        if (!rawResult || !rawResult.success) {
            showPdfError('加载失败', rawResult ? rawResult.message : '无法读取文件');
            return;
        }

        var binaryStr = atob(rawResult.content);
        var len = binaryStr.length;
        var bytes = new Uint8Array(len);
        for (var i = 0; i < len; i++) {
            bytes[i] = binaryStr.charCodeAt(i);
        }

        if (typeof pdfjsLib === 'undefined') {
            showPdfError('PDF 查看器未加载', 'pdf.js 库不可用，请检查网络连接');
            return;
        }

        pdfjsLib.GlobalWorkerOptions.workerSrc = 'pdfjs-legacy.worker.min.js';

        var loadingTask = pdfjsLib.getDocument({ data: bytes });
        var pdfDoc = await loadingTask.promise;

        if (requestId !== currentLoadRequestId) {
            pdfDoc.destroy();
            return;
        }

        pdfViewerState = {
            pdfDoc: pdfDoc,
            pageNum: 1,
            pageCount: pdfDoc.numPages,
            scale: 1.0
        };

        document.getElementById('pdf-page-count').textContent = pdfDoc.numPages;
        document.getElementById('pdf-page-num').textContent = '1';
        document.getElementById('pdf-zoom-level').textContent = '100%';

        renderPdfPage(pdfViewerState.pageNum);

        document.getElementById('pdf-prev-btn').addEventListener('click', function() {
            if (pdfViewerState.pageNum <= 1) return;
            pdfViewerState.pageNum--;
            renderPdfPage(pdfViewerState.pageNum);
        });

        document.getElementById('pdf-next-btn').addEventListener('click', function() {
            if (pdfViewerState.pageNum >= pdfViewerState.pageCount) return;
            pdfViewerState.pageNum++;
            renderPdfPage(pdfViewerState.pageNum);
        });

        document.getElementById('pdf-zoom-in-btn').addEventListener('click', function() {
            pdfViewerState.scale = Math.min(pdfViewerState.scale + 0.25, 3.0);
            document.getElementById('pdf-zoom-level').textContent = Math.round(pdfViewerState.scale * 100) + '%';
            renderPdfPage(pdfViewerState.pageNum);
        });

        document.getElementById('pdf-zoom-out-btn').addEventListener('click', function() {
            pdfViewerState.scale = Math.max(pdfViewerState.scale - 0.25, 0.5);
            document.getElementById('pdf-zoom-level').textContent = Math.round(pdfViewerState.scale * 100) + '%';
            renderPdfPage(pdfViewerState.pageNum);
        });

        var canvasWrapper = document.getElementById('pdf-canvas-wrapper');
        canvasWrapper.addEventListener('wheel', function(e) {
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                if (e.deltaY < 0) {
                    pdfViewerState.scale = Math.min(pdfViewerState.scale + 0.1, 3.0);
                } else {
                    pdfViewerState.scale = Math.max(pdfViewerState.scale - 0.1, 0.5);
                }
                document.getElementById('pdf-zoom-level').textContent = Math.round(pdfViewerState.scale * 100) + '%';
                renderPdfPage(pdfViewerState.pageNum);
            }
        }, { passive: false });

        document.addEventListener('keydown', function pdfKeyHandler(e) {
            if (!pdfViewerState) {
                document.removeEventListener('keydown', pdfKeyHandler);
                return;
            }
            if (e.key === 'ArrowRight' || e.key === 'PageDown') {
                if (pdfViewerState.pageNum < pdfViewerState.pageCount) {
                    pdfViewerState.pageNum++;
                    renderPdfPage(pdfViewerState.pageNum);
                }
            } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
                if (pdfViewerState.pageNum > 1) {
                    pdfViewerState.pageNum--;
                    renderPdfPage(pdfViewerState.pageNum);
                }
            }
        });

    } catch (e) {
        console.error('[Preview] PDF load error:', e);
        if (requestId === currentLoadRequestId) {
            showPdfError('PDF 加载失败', e.message || '未知错误');
        }
    }
}

async function renderPdfPage(pageNum) {
    if (!pdfViewerState || !pdfViewerState.pdfDoc) return;

    var canvas = document.getElementById('pdf-render-canvas');
    if (!canvas) return;

    document.getElementById('pdf-page-num').textContent = pageNum;

    try {
        var page = await pdfViewerState.pdfDoc.getPage(pageNum);
        var viewport = page.getViewport({ scale: pdfViewerState.scale });

        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = viewport.width + 'px';
        canvas.style.height = viewport.height + 'px';

        var ctx = canvas.getContext('2d');
        var renderContext = {
            canvasContext: ctx,
            viewport: viewport
        };

        await page.render(renderContext).promise;
        page.cleanup();
    } catch (e) {
        console.error('[Preview] PDF render error:', e);
    }
}

function showPdfError(title, message) {
    var previewContent = document.getElementById('preview-content');
    if (!previewContent) return;
    previewContent.style.display = '';
    previewContent.style.padding = '16px';
    showPreviewError(title, message);
}

function renderPreviewContent(previewData) {
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    const { type, content, metadata } = previewData;

    let previewHtml = '';

    if (metadata) {
        previewHtml += `
            <div class="preview-file-info">
                <div class="preview-file-info-row">
                    <span class="preview-file-info-label">类型:</span>
                    <span class="preview-file-info-value">${metadata.type || '未知'}</span>
                </div>
                ${metadata.size ? `
                    <div class="preview-file-info-row">
                        <span class="preview-file-info-label">大小:</span>
                        <span class="preview-file-info-value">${formatFileSize(metadata.size)}</span>
                    </div>
                ` : ''}
                ${metadata.modified ? `
                    <div class="preview-file-info-row">
                        <span class="preview-file-info-label">修改时间:</span>
                        <span class="preview-file-info-value">${formatModifiedTime(metadata.modified)}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    if (type === 'markdown' || type === 'text') {
        if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
            previewHtml += `<div class="preview-content">${window.EditorModule.renderMarkdownPreview(content)}</div>`;
        } else {
            previewHtml += `<div class="preview-content"><pre>${escapeHtml(content)}</pre></div>`;
        }
    } else if (type === 'image') {
        previewHtml += `
            <div class="preview-content" style="display: flex; justify-content: center; align-items: center; padding: 20px;">
                <img src="data:${metadata?.mime || 'image/png'};base64,${content}" 
                     style="max-width: 100%; max-height: 80vh; border-radius: 8px;" 
                     alt="Image">
            </div>
        `;
    } else if (type === 'code' || type === 'json' || type === 'xml' || type === 'html') {
        previewHtml += `<div class="preview-content"><pre><code class="language-${type}">${escapeHtml(content)}</code></pre></div>`;
    } else {
        previewHtml += `<div class="preview-content"><pre>${escapeHtml(content)}</pre></div>`;
    }

    previewContent.innerHTML = previewHtml;

    if (typeof hljs !== 'undefined') {
        previewContent.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }
}

function showPreviewError(title, message) {
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    previewContent.innerHTML = `
        <div class="preview-error">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="15" y1="9" x2="9" y2="15"></line>
                <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            <div class="preview-error-title">${escapeHtml(title)}</div>
            <div class="preview-error-message">${escapeHtml(message)}</div>
        </div>
    `;
}

function closePreview() {
    currentLoadRequestId += 1;
    
    if (pdfViewerState && pdfViewerState.pdfDoc) {
        try {
            pdfViewerState.pdfDoc.destroy();
        } catch(e) {}
        pdfViewerState = null;
    }
    
    const previewPanel = document.getElementById('preview-panel');
    const previewContent = document.getElementById('preview-content');

    if (window.TiptapEditor && window.TiptapEditor.isActive) {
        if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
            window.TiptapEditorModule.hideEditorUI();
        }
    }

    if (window.mdEditor && window.mdEditor.isActive) {
        if (window.EditorModule && window.EditorModule.destroyCodeMirrorEditor) {
            window.EditorModule.destroyCodeMirrorEditor();
        }
    }

    showEditButton(false);

    if (previewPanel) {
        previewPanel.classList.remove('active');
        previewPanel.classList.remove('editor-active');
    }

    if (previewContent) {
        previewContent.innerHTML = `
            <div class="preview-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <div>选择一个文件查看预览</div>
            </div>
        `;
    }

    currentPreviewData = null;
    isPreviewActive = false;

    showContentView();
}

function closePreviewPanel() {
    closePreview();
}

function backToContent() {
    if (window.EditorModule && window.EditorModule.isActive) {
        window.EditorModule.exitEditMode();
    }
    showContentView();
}

window.PreviewModule = {
    currentPreviewData,
    isPreviewActive,
    showContentView,
    showPreviewView,
    loadFilePreview,
    renderPreviewContent,
    showPreviewError,
    closePreview,
    backToContent,
    updateTitlebarFileName,
    showEditButton
};

window.showTagsView = function() { window.switchSidebarView('tags'); };
