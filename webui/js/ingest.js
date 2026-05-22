(function() { 'use strict';

var STAGE_LABELS = {
    schema: '规范',
    convert: '转换',
    classify: '分类',
    index: '向量索引',
    cascade: '综述',
    lint: '健康检查',
    sync: '同步'
};

function showBar() {
    var bar = document.getElementById('ingest-pipeline-bar');
    if (bar) bar.classList.add('visible');
}

function hideBar() {
    var bar = document.getElementById('ingest-pipeline-bar');
    if (bar) bar.classList.remove('visible');
}

function updateBar(stage, progress, message) {
    showBar();
    var fill = document.getElementById('ingest-pipeline-fill');
    var label = document.getElementById('ingest-pipeline-stage');
    var msg = document.getElementById('ingest-pipeline-message');
    if (fill) fill.style.width = Math.round((progress || 0) * 100) + '%';
    if (label) label.textContent = STAGE_LABELS[stage] || stage || '入库';
    if (msg) msg.textContent = message || '';
    if (typeof window.updateStatus === 'function') {
        window.updateStatus(message || '入库流水线…');
    }
}

function onIngestComplete(data) {
    hideBar();
    if (data.cancelled) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus('入库已取消');
        }
        return;
    }
    if (data.success) {
        var stats = data.stats || {};
        var parts = [];
        if (stats.converted) parts.push('转换 ' + stats.converted);
        if (stats.classified) parts.push('分类 ' + stats.classified);
        if (stats.indexed_files) parts.push('索引 ' + stats.indexed_files);
        if (stats.cascade_updated) parts.push('综述 ' + stats.cascade_updated);
        if (stats.lint && stats.lint.total) parts.push('Lint ' + stats.lint.total);
        if (typeof window.updateStatus === 'function') {
            window.updateStatus('入库完成' + (parts.length ? ' — ' + parts.join('，') : ''));
        }
    } else {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus('入库失败: ' + (data.error || '未知错误'));
        }
    }
    if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
        window.refreshWorkspaceViewsAfterChange();
    }
    if (typeof window.refreshPendingBtnState === 'function') {
        window.refreshPendingBtnState();
    }
}

function handleEvent(data) {
    if (!data) return;
    if (data.type === 'ingest_progress') {
        updateBar(data.stage, data.progress, data.message);
    } else if (data.type === 'ingest_complete') {
        onIngestComplete(data);
    }
}

async function startIngest(mode, filePaths) {
    if (!window.api || !window.api.startIngest) return { success: false };
    showBar();
    updateBar('schema', 0, '启动入库流水线…');
    return window.api.startIngest({
        mode: mode || 'full',
        file_paths: filePaths || []
    });
}

async function cancelIngest() {
    if (window.api && window.api.cancelIngest) {
        await window.api.cancelIngest();
    }
}

async function retryIngest(mode) {
    if (!window.api || !window.api.retryIngest) return { success: false };
    showBar();
    return window.api.retryIngest({ mode: mode || 'full' });
}

function initIngestUi() {
    var cancelBtn = document.getElementById('ingest-pipeline-cancel');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            cancelIngest();
        });
    }
}

window.IngestModule = {
    startIngest: startIngest,
    cancelIngest: cancelIngest,
    retryIngest: retryIngest,
    handleEvent: handleEvent,
    initIngestUi: initIngestUi
};

})();
