(function() { 'use strict';

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
    const graphPanel = document.getElementById('graph-panel');
    const pendingView = document.getElementById('pending-view');
    const home = document.getElementById('home-dashboard');

    if (contentPanel) contentPanel.style.display = 'flex';
    if (previewPanel) previewPanel.style.display = 'none';
    if (graphPanel) graphPanel.style.display = 'none';
    if (pendingView) pendingView.style.display = 'none';
    if (home) home.style.display = 'none';
    if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();
    if (titlebarFileName) {
        titlebarFileName.style.display = 'none';
        titlebarFileName.textContent = '';
    }
    if (titlebarSplitBtn) titlebarSplitBtn.style.display = 'none';
    if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'none';

    var graphHome = document.getElementById('home-dashboard') || document.getElementById('graph-home-view');
    var contentArea = document.getElementById('content-area');
    if (window.AppState.selectedFilePath) {
        if (graphHome) graphHome.style.display = 'none';
        if (contentArea) contentArea.style.display = '';
    } else {
        if (graphHome) graphHome.style.display = '';
        if (contentArea) contentArea.style.display = 'none';
        if (typeof window.updateHomeStats === 'function') window.updateHomeStats();
    }
}

function showPreviewView() {
    if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.deactivate) window.SemanticWorkbenchModule.deactivate();
    const contentPanel = document.getElementById('content-panel');
    const previewPanel = document.getElementById('preview-panel');
    const pendingView = document.getElementById('pending-view');

    if (contentPanel) contentPanel.style.display = 'none';
    if (previewPanel) previewPanel.style.display = 'flex';
    if (pendingView) pendingView.style.display = 'none';
    if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();
}

function updateTitlebarFileName(fileName, isMarkdown) {
    const titlebarFileName = document.getElementById('titlebar-file-name');
    const titlebarCloseBtn = document.getElementById('titlebar-close-preview-btn');
    
    if (fileName) {
        if (titlebarFileName) {
            titlebarFileName.textContent = fileName;
            titlebarFileName.style.display = 'block';
        }
        if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'flex';
    } else {
        if (titlebarFileName) {
            titlebarFileName.style.display = 'none';
            titlebarFileName.textContent = '';
        }
        if (titlebarCloseBtn) titlebarCloseBtn.style.display = 'none';
    }
}

function showEditButton(show) {
    const splitBtn = document.getElementById('titlebar-split-btn');
    if (splitBtn) {
        splitBtn.style.display = show ? 'flex' : 'none';
    }
}

// ============================================================================
// P5：语义页可信度元信息条
// 识别 wiki 语义页（frontmatter semantic_page: true 或 wiki/semantic/*_语义.md），
// 异步拉取 topic_meta 后在正文上方注入元信息条；不阻塞正文渲染。
// 所有动态文本一律经 window.escapeHtml 转义（XSS 加固要求）。
// ============================================================================

function parseMarkdownFrontmatter(content) {
    if (typeof content !== 'string') return null;
    var m = content.slice(0, 2000).match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---/);
    if (!m) return null;
    var fm = {};
    m[1].split(/\r?\n/).forEach(function(line) {
        var kv = line.match(/^([A-Za-z0-9_-]+)\s*:\s*(.*)$/);
        if (kv) fm[kv[1]] = kv[2].trim();
    });
    return fm;
}

function isSemanticWikiPath(path) {
    if (!path) return false;
    return /(^|[/\\])wiki[/\\]semantic[/\\][^/\\]*_语义\.md$/i.test(String(path));
}

function removeSemanticMetaBar() {
    document.querySelectorAll('.semantic-page-meta').forEach(function(el) {
        el.remove();
    });
}

function formatRelativeTime(value) {
    var d = new Date(typeof value === 'number' ? value * 1000 : value);
    if (isNaN(d.getTime())) return '';
    var diff = Date.now() - d.getTime();
    if (diff < 0) diff = 0;
    if (diff < 60000) return window.t('preview.justNow');
    if (diff < 3600000) return window.t('preview.minutesAgo', { count: Math.floor(diff / 60000) });
    if (diff < 86400000) return window.t('preview.hoursAgo', { count: Math.floor(diff / 3600000) });
    if (diff < 604800000) return window.t('preview.daysAgo', { count: Math.floor(diff / 86400000) });
    return window.formatModifiedTime(d.getTime() / 1000);
}

function buildSemanticMetaBarHtml(meta) {
    var sourceCount = Number(meta.source_count) || 0;
    var parts = [escapeHtml(window.t('preview.semanticSources', { count: sourceCount }))];
    var compiledLabel = meta.compiled_at ? formatRelativeTime(meta.compiled_at) : '';
    if (compiledLabel) {
        parts.push(escapeHtml(window.t('preview.semanticCompiled', { time: compiledLabel })));
    }
    var html = '<div class="semantic-page-meta-text">' + parts.join(' · ') + '</div>';
    html += '<div class="semantic-page-meta-badges">';
    if (meta.is_stale) {
        html += '<span class="semantic-page-meta-badge semantic-page-meta-badge-stale" title="'
            + escapeAttr(window.t('preview.semanticStaleTitle')) + '">'
            + escapeHtml(window.t('preview.semanticStale')) + '</span>';
    }
    var conflictCount = Number(meta.conflict_pending_count) || 0;
    if (conflictCount > 0) {
        html += '<button type="button" class="semantic-page-meta-badge semantic-page-meta-badge-conflict" data-meta-action="conflicts" title="'
            + escapeAttr(window.t('preview.semanticConflictsTitle')) + '">'
            + escapeHtml(window.t('preview.semanticConflicts', { count: conflictCount })) + '</button>';
    }
    html += '</div>';
    return html;
}

function insertSemanticMetaBar(html) {
    var wrapper = document.querySelector('#preview-panel .preview-content-wrapper');
    if (!wrapper) return;
    var bar = document.createElement('div');
    bar.className = 'semantic-page-meta';
    bar.innerHTML = html;
    var conflictBtn = bar.querySelector('[data-meta-action="conflicts"]');
    if (conflictBtn) {
        conflictBtn.addEventListener('click', function() {
            if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.show) {
                window.SemanticWorkbenchModule.show('conflicts');
            }
        });
    }
    removeSemanticMetaBar();
    wrapper.insertBefore(bar, wrapper.firstChild);
}

function maybeLoadSemanticPageMeta(path, content, requestId) {
    removeSemanticMetaBar();
    if (!isPreviewActive || requestId !== currentLoadRequestId) return;
    var fm = parseMarkdownFrontmatter(content);
    var semantic = !!(fm && /^(true|yes)$/i.test(String(fm.semantic_page || '')));
    if (!semantic && !isSemanticWikiPath(path)) return;
    var topic = fm && fm.topic ? String(fm.topic).replace(/^["']|["']$/g, '').trim() : '';
    if (!topic) return;
    if (!window.api || typeof window.api.topicMeta !== 'function') return;
    // 异步获取，不阻塞正文渲染；到达后再插入元信息条
    window.api.topicMeta(topic).then(function(meta) {
        if (requestId !== currentLoadRequestId || !isPreviewActive) return;
        if (!meta || meta.exists === false) return;
        insertSemanticMetaBar(buildSemanticMetaBarHtml(meta));
    }).catch(function(err) {
        console.warn('[Preview] topicMeta load failed:', err);
    });
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
            <div>${window.t('preview.loading')}</div>
        </div>
    `;

    const tiptapContainer = document.getElementById('tiptap-editor-container');
    const toolbar = document.getElementById('tiptap-toolbar');
    if (tiptapContainer) tiptapContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';

    previewPanel.classList.add('active');
    showPreviewView();
    removeSemanticMetaBar();

    try {
        const result = await window.api.getFilePreview(path);
        
        if (requestId !== currentLoadRequestId) {
            return;
        }
        
        if (result && result.success) {
            const fileType = result.type || 'markdown';
            const isMarkdown = fileType === 'markdown' || fileName.toLowerCase().endsWith('.md');
            const isPdf = fileType === 'pdf' || fileName.toLowerCase().endsWith('.pdf');
            const isDocx = fileType === 'docx' || fileType === 'word'
                || /\.docx?$/i.test(fileName);
            
            currentPreviewData = {
                path: path,
                name: fileName,
                type: isDocx ? 'docx' : fileType,
                content: result.content || result.full_text || '',
                contentKind: result.content_kind || 'text',
                metadata: result.metadata || {
                    type: isDocx ? window.t('preview.typeWord') : undefined,
                    size: result.file_size,
                },
                pdfData: result
            };

            updateTitlebarFileName(fileName, isMarkdown);

            if (isMarkdown) {
                maybeLoadSemanticPageMeta(path, currentPreviewData.content, requestId);
            }

            if (isPdf) {
                if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                    await window.TiptapEditorModule.hideEditorUI();
                }
                showEditButton(false);
                await loadPdfViewer(path, fileName, requestId);
            } else if (isDocx) {
                if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                    await window.TiptapEditorModule.hideEditorUI();
                }
                showEditButton(false);
                renderPreviewContent(currentPreviewData);
            } else if (isMarkdown) {
                if (window.TiptapEditorModule && window.TiptapEditorModule.openMarkdownInEditor) {
                    try {
                        let editorReady = await window.TiptapEditorModule.openMarkdownInEditor(
                            result.content,
                            path
                        );

                        if (!editorReady && window.TiptapEditor && window.TiptapEditor.whenModulesReady) {
                            const modulesOk = await window.TiptapEditor.whenModulesReady(8000);
                            if (modulesOk && requestId === currentLoadRequestId) {
                                if (window.TiptapEditorModule.hideEditorUI) {
                                    await window.TiptapEditorModule.hideEditorUI();
                                }
                                editorReady = await window.TiptapEditorModule.openMarkdownInEditor(
                                    result.content,
                                    path
                                );
                            }
                        }
                        
                        if (requestId !== currentLoadRequestId) {
                            if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                                await window.TiptapEditorModule.hideEditorUI();
                            }
                            return;
                        }
                        
                        if (!editorReady) {
                            showEditButton(false);
                            console.warn('[Preview] WYSIWYG editor unavailable, showing read-only preview');
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
                    if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                        await window.TiptapEditorModule.hideEditorUI();
                    }
                    showEditButton(false);
                    renderPreviewContent(currentPreviewData);
                }
            } else {
                if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
                    await window.TiptapEditorModule.hideEditorUI();
                }
                showEditButton(false);
                renderPreviewContent(currentPreviewData);
            }
        } else {
            showPreviewError(window.t('preview.loadFailed'), result?.error || result?.message || window.t('preview.cannotRead'));
        }
    } catch (e) {
        console.error('[Preview] Load error:', e);
        if (requestId === currentLoadRequestId) {
            showPreviewError(window.t('preview.loadFailed'), e.message);
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
                    <button class="pdf-nav-btn" id="pdf-prev-btn" title="${window.t('preview.prevPage')}">
                        ${window.Icons.get('chevronLeft', 16)}
                    </button>
                    <span class="pdf-page-info"><span id="pdf-page-num">1</span> / <span id="pdf-page-count">0</span></span>
                    <button class="pdf-nav-btn" id="pdf-next-btn" title="${window.t('preview.nextPage')}">
                        ${window.Icons.get('chevronRight', 16)}
                    </button>
                </div>
                <div class="pdf-toolbar-right">
                    <button class="pdf-zoom-btn" id="pdf-zoom-out-btn" title="${window.t('preview.zoomOut')}">−</button>
                    <span class="pdf-zoom-level" id="pdf-zoom-level">100%</span>
                    <button class="pdf-zoom-btn" id="pdf-zoom-in-btn" title="${window.t('preview.zoomIn')}">+</button>
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
        var rawResult = await window.api.readFileRaw(path);
        if (requestId !== currentLoadRequestId) return;

        if (!rawResult || !rawResult.success) {
            showPdfError(window.t('preview.loadFailed'), rawResult ? rawResult.message : window.t('preview.cannotRead'));
            return;
        }

        var bytes = window.b64ToUint8(rawResult.content);

        if (typeof pdfjsLib === 'undefined') {
            // pdfjs 不再随首屏加载：打开 PDF 时按需注入（幂等）
            try {
                await window.loadLazyScript('pdfjs-legacy.min.js');
            } catch (e) {
                showPdfError(window.t('preview.pdfViewerMissing'), window.t('preview.pdfJsUnavailable'));
                return;
            }
            if (typeof pdfjsLib === 'undefined') {
                showPdfError(window.t('preview.pdfViewerMissing'), window.t('preview.pdfJsUnavailable'));
                return;
            }
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

        if (window._pdfKeyHandler) {
            document.removeEventListener('keydown', window._pdfKeyHandler);
            window._pdfKeyHandler = null;
        }
        window._pdfKeyHandler = function pdfKeyHandler(e) {
            if (!pdfViewerState) {
                document.removeEventListener('keydown', window._pdfKeyHandler);
                window._pdfKeyHandler = null;
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
        };
        document.addEventListener('keydown', window._pdfKeyHandler);

    } catch (e) {
        console.error('[Preview] PDF load error:', e);
        if (requestId === currentLoadRequestId) {
            showPdfError(window.t('preview.pdfLoadFailed'), e.message || window.t('common.unknownError'));
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
                    <span class="preview-file-info-label">${window.t('preview.typeLabel')}</span>
                    <span class="preview-file-info-value">${escapeHtml(metadata.type || window.t('preview.unknownType'))}</span>
                </div>
                ${metadata.size ? `
                    <div class="preview-file-info-row">
                        <span class="preview-file-info-label">${window.t('preview.sizeLabel')}</span>
                        <span class="preview-file-info-value">${formatFileSize(metadata.size)}</span>
                    </div>
                ` : ''}
                ${metadata.modified ? `
                    <div class="preview-file-info-row">
                        <span class="preview-file-info-label">${window.t('preview.modifiedLabel')}</span>
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
    } else if (type === 'docx' || type === 'word') {
        previewHtml += renderDocxPreviewHtml(content, previewData.contentKind);
    } else if (type === 'image') {
        var rawMime = (metadata && metadata.mime) || 'image/png';
        var safeMime = /^[a-z0-9]+\/[a-z0-9.+-]+$/i.test(rawMime) ? rawMime : 'image/png';
        previewHtml += `
            <div class="preview-content" style="display: flex; justify-content: center; align-items: center; padding: 20px;">
                <img src="data:${safeMime};base64,${content}" 
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

function renderDocxPreviewHtml(content, contentKind) {
    const body = content || '';
    if (!body.trim()) {
        return '<div class="preview-content docx-preview"><p class="docx-preview-empty">' + window.t('preview.docxEmpty') + '</p></div>';
    }
    if (contentKind === 'html') {
        const safe = typeof DOMPurify !== 'undefined'
            ? DOMPurify.sanitize(body, { USE_PROFILES: { html: true } })
            : escapeHtml(body);
        return `<article class="preview-content docx-preview">${safe}</article>`;
    }
    if (window.EditorModule && window.EditorModule.renderMarkdownPreview) {
        return `<div class="preview-content docx-preview">${window.EditorModule.renderMarkdownPreview(body)}</div>`;
    }
    return `<div class="preview-content docx-preview"><pre>${escapeHtml(body)}</pre></div>`;
}

function showPreviewError(title, message) {
    const previewContent = document.getElementById('preview-content');
    if (!previewContent) return;

    previewContent.innerHTML = `
        <div class="preview-error">
            ${window.Icons.get('close', 48)}
            <div class="preview-error-title">${escapeHtml(title)}</div>
            <div class="preview-error-message">${escapeHtml(message)}</div>
        </div>
    `;
}

function closePreview() {
    currentLoadRequestId += 1;

    removeSemanticMetaBar();

    if (pdfViewerState && pdfViewerState.pdfDoc) {
        try {
            pdfViewerState.pdfDoc.destroy();
        } catch(e) {}
        pdfViewerState = null;
    }

    if (window._pdfKeyHandler) {
        document.removeEventListener('keydown', window._pdfKeyHandler);
        window._pdfKeyHandler = null;
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
                ${window.Icons.get('fileDoc', 48)}
                <div>${window.t('preview.selectFile')}</div>
            </div>
        `;
    }

    currentPreviewData = null;
    isPreviewActive = false;

    window.AppState.selectedFilePath = null;
    window.AppState.selectedFileName = null;

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
    get currentPreviewData() { return currentPreviewData; },
    get isPreviewActive() { return isPreviewActive; },
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

window.showTagsView = function() { window.switchSidebarView('tree'); };

window.closePreview = closePreview;
window.closePreviewPanel = closePreviewPanel;
window.backToContent = backToContent;

window.showPreview = function(options) {
    if (!options || !options.path) {
        console.error('[showPreview] Missing path parameter');
        return;
    }
    const path = options.path;
    const name = options.name || path.split('/').pop() || window.t('preview.defaultName');
    window.PreviewModule.loadFilePreview(path, name);
};

})();
