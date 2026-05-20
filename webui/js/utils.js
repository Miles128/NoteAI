(function() { 'use strict';

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

function formatFileSizeForTree(size) {
    if (size < 1024) {
        return size + ' B';
    } else if (size < 1024 * 1024) {
        return (size / 1024).toFixed(1) + ' KB';
    } else if (size < 1024 * 1024 * 1024) {
        return (size / (1024 * 1024)).toFixed(1) + ' MB';
    } else {
        return (size / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
    }
}

function Path_stem(p) {
    if (!p) return p;
    var parts = p.split('/');
    var name = parts[parts.length - 1];
    var dotIdx = name.lastIndexOf('.');
    return dotIdx > 0 ? name.substring(0, dotIdx) : name;
}

function getTauriEventAPI() {
    if (window.__TAURI__ && window.__TAURI__.event && typeof window.__TAURI__.event.listen === 'function') {
        return window.__TAURI__.event;
    }
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && typeof window.__TAURI_INTERNALS__.event.listen === 'function') {
        return window.__TAURI_INTERNALS__.event;
    }
    return null;
}

window.escapeHtml = escapeHtml;
window.escapeAttr = escapeAttr;
window.formatFileSize = formatFileSize;
window.formatModifiedTime = formatModifiedTime;
window.formatFileSizeForTree = formatFileSizeForTree;
window.Path_stem = Path_stem;
window.getTauriEventAPI = getTauriEventAPI;

window.utils = {
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    formatFileSize: formatFileSize,
    formatFileSizeForTree: formatFileSizeForTree,
    formatModifiedTime: formatModifiedTime,
    Path_stem: Path_stem,
    getTauriEventAPI: getTauriEventAPI
};

})();
