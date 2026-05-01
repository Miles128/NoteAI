function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

window.utils = {
    escapeHtml: escapeHtml,
    formatFileSize: formatFileSize,
    formatFileSizeForTree: formatFileSizeForTree,
    formatModifiedTime: formatModifiedTime
};
