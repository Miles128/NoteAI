(function() { 'use strict';

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatFileSize(bytes) {
    if (bytes == null) return '';
    if (bytes < 1024) return bytes + ' Byte';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' K';
    return (bytes / (1024 * 1024)).toFixed(1) + ' M';
}

function formatModifiedTime(timestamp) {
    if (timestamp == null) return '';
    var d = new Date(timestamp * 1000);
    var pad = function(n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function Path_stem(p) {
    if (!p) return p;
    var parts = p.split('/');
    var name = parts[parts.length - 1];
    var dotIdx = name.lastIndexOf('.');
    return dotIdx > 0 ? name.substring(0, dotIdx) : name;
}

window.escapeHtml = escapeHtml;
window.escapeAttr = escapeAttr;
window.formatFileSize = formatFileSize;
window.formatModifiedTime = formatModifiedTime;
window.Path_stem = Path_stem;

/** 侧边栏等在模块加载完毕前可被点击；占位避免 ReferenceError（各模块会覆盖） */
function _noop() {}

var _earlyGlobals = [
    'toggleSidebar',
    'toggleFileListSidebar',
    'toggleNoteList',
    'openWorkspace',
    'showSettings',
    'importFiles',
    'switchTab',
    'closePreviewPanel',
    'togglePendingView',
    'toggleEditMode',
    'toggleGraphPanel',
    'toggleSearchModal',
    'toggleAIPanel',
    'closeSettingsPanel',
    'saveApiConfig',
];
_earlyGlobals.forEach(function(name) {
    if (typeof window[name] !== 'function') {
        window[name] = _noop;
    }
});

})();
