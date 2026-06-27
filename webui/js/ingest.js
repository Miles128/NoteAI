(function() { 'use strict';

var STAGE_LABELS = {
    rules: window.t('ingest.stage.rules'),
    schema: window.t('ingest.stage.rules'),
    convert: window.t('ingest.stage.convert'),
    classify: window.t('ingest.stage.classify'),
    index: window.t('ingest.stage.index'),
    cascade: window.t('ingest.stage.cascade'),
    lint: window.t('ingest.stage.lint'),
    sync: window.t('ingest.stage.sync')
};

function showBar() {
    var bar = document.getElementById('ingest-pipeline-bar');
    var appBar = document.getElementById('app-statusbar');
    if (bar) bar.classList.add('visible');
    if (appBar) appBar.classList.add('ingest-active');
}

function hideBar() {
    var bar = document.getElementById('ingest-pipeline-bar');
    var appBar = document.getElementById('app-statusbar');
    if (bar) bar.classList.remove('visible');
    if (appBar) appBar.classList.remove('ingest-active');
}

function updateBar(stage, progress, message) {
    showBar();
    var fill = document.getElementById('ingest-pipeline-fill');
    var label = document.getElementById('ingest-pipeline-stage');
    var msg = document.getElementById('ingest-pipeline-message');
    if (fill) fill.style.width = Math.round((progress || 0) * 100) + '%';
    if (label) label.textContent = STAGE_LABELS[stage] || stage || window.t('ingest.label');
    if (msg) msg.textContent = message || '';
    if (typeof window.updateStatus === 'function') {
        window.updateStatus(message || window.t('ingest.pipelineRunning'));
    }
}

function onIngestComplete(data) {
    hideBar();
    if (data.cancelled) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('ingest.cancelled'));
        }
        return;
    }
    if (data.success) {
        var stats = data.stats || {};
        var parts = [];
        if (stats.converted) parts.push(window.t('ingest.statConverted', { count: stats.converted }));
        if (stats.classified) parts.push(window.t('ingest.statClassified', { count: stats.classified }));
        if (stats.indexed_files) parts.push(window.t('ingest.statIndexed', { count: stats.indexed_files }));
        if (stats.cascade_updated) parts.push(window.t('ingest.statCascade', { count: stats.cascade_updated }));
        if (stats.lint && stats.lint.total) parts.push('Lint ' + stats.lint.total);
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('ingest.done') + (parts.length ? ' — ' + parts.join('，') : ''));
        }
    } else {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('ingest.failed') + (data.error || window.t('common.unknownError')));
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
    updateBar('schema', 0, window.t('ingest.starting'));
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
