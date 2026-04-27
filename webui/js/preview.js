let currentPreviewData = null;
let isPreviewActive = false;

function showContentView() {
    const contentPanel = document.getElementById('content-panel');
    const previewPanel = document.getElementById('preview-panel');

    if (contentPanel) contentPanel.style.display = 'flex';
    if (previewPanel) previewPanel.style.display = 'none';
}

function showPreviewView() {
    const contentPanel = document.getElementById('content-panel');
    const previewPanel = document.getElementById('preview-panel');

    if (contentPanel) contentPanel.style.display = 'none';
    if (previewPanel) previewPanel.style.display = 'flex';
}

async function loadFilePreview(path, fileName) {
    const previewPanel = document.getElementById('preview-panel');
    const previewContent = document.getElementById('preview-content');
    const previewTitle = document.getElementById('preview-file-name');

    if (!previewPanel || !previewContent) return;

    isPreviewActive = true;

    if (previewTitle) {
        previewTitle.textContent = fileName;
    }

    previewContent.innerHTML = `
        <div class="preview-loading">
            <div class="preview-spinner"></div>
            <div>加载中...</div>
        </div>
    `;

    previewPanel.classList.add('active');
    showPreviewView();

    try {
        const result = await window.api.read_note_file(path);
        
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
    const previewPanel = document.getElementById('preview-panel');
    const previewContent = document.getElementById('preview-content');

    if (window.EditorModule && window.EditorModule.isActive) {
        window.EditorModule.exitEditMode();
    }

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
    backToContent
};
