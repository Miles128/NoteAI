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

/**
 * URL 协议白名单校验：仅允许 http/https/锚点/相对路径，
 * 拒绝 javascript:、data:、vbscript: 等危险协议。不合法时返回 '#'。
 */
function safeUrl(url) {
    // 先剔除控制字符再判断协议，堵住 "java\tscript:" 类绕过
    var str = String(url == null ? '' : url).replace(/[\t\n\r]/g, '').trim();
    if (!str) return '#';
    // 锚点或相对路径（不含协议分隔）
    if (str.charAt(0) === '#' || str.charAt(0) === '/' || str.charAt(0) === '.' || str.charAt(0) === '?') return str;
    if (/^https?:\/\//i.test(str)) return str;
    // 含协议但不在白名单（javascript:/data:/vbscript:/file: 等）→ 拒绝
    if (/^[a-z][a-z0-9+.-]*:/i.test(str)) return '#';
    // 无协议的相对路径（如 notes/xx.md）
    return str;
}

function Path_stem(p) {
    if (!p) return p;
    var parts = p.split('/');
    var name = parts[parts.length - 1];
    var dotIdx = name.lastIndexOf('.');
    return dotIdx > 0 ? name.substring(0, dotIdx) : name;
}

/** Base64 → Uint8Array；非 Tauri/畸形输入返回空数组。 */
function b64ToUint8(b64) {
    if (!b64) return new Uint8Array(0);
    var bin = typeof atob === 'function' ? atob(b64) : '';
    var out = new Uint8Array(bin.length);
    var i = 0;
    for (; i < bin.length; i++) {
        out[i] = bin.charCodeAt(i) & 0xff;
    }
    return out;
}

/** Base64 → UTF-8 字符串（用于后端 base64 编码的文本流）。 */
function b64DecodeUtf8(b64) {
    if (!b64) return '';
    return new TextDecoder('utf-8').decode(b64ToUint8(b64));
}

/** 幂等懒加载经典脚本（不重复注入同一 src）。用于 pdfjs/tiptap 等按需库。 */
var _lazyScripts = {};
function loadLazyScript(src) {
    if (_lazyScripts[src] === true) return Promise.resolve(true);
    if (_lazyScripts[src]) return _lazyScripts[src];
    _lazyScripts[src] = new Promise(function(resolve, reject) {
        var existing = document.querySelector('script[data-lazy-src="' + src + '"]');
        if (existing) {
            if (existing.dataset.loaded === '1') { resolve(true); return; }
            existing.addEventListener('load', function() { resolve(true); });
            existing.addEventListener('error', function() { reject(new Error('加载失败: ' + src)); });
            return;
        }
        var s = document.createElement('script');
        s.src = src;
        s.dataset.lazySrc = src;
        s.onload = function() {
            s.dataset.loaded = '1';
            _lazyScripts[src] = true;
            resolve(true);
        };
        s.onerror = function() {
            _lazyScripts[src] = null;
            reject(new Error('加载失败: ' + src));
        };
        document.head.appendChild(s);
    });
    return _lazyScripts[src];
}

window.escapeHtml = escapeHtml;
window.escapeAttr = escapeAttr;
window.safeUrl = safeUrl;
window.formatFileSize = formatFileSize;
window.formatModifiedTime = formatModifiedTime;
window.Path_stem = Path_stem;
window.b64ToUint8 = b64ToUint8;
window.b64DecodeUtf8 = b64DecodeUtf8;
window.loadLazyScript = loadLazyScript;

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
