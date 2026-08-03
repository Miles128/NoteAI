window.WindowManager = (function() { 'use strict';

// 桥接探测统一由 api.js 提供（window.checkIsTauri / window.getTauriInvoke）
function checkIsTauri() {
    return window.checkIsTauri
        ? window.checkIsTauri()
        : !!(window.__TAURI_INTERNALS__ || window.__TAURI__);
}

function getTauriInvoke() {
    return window.getTauriInvoke ? window.getTauriInvoke() : null;
}

function getTauriWindow() {
    if (window.__TAURI__ && window.__TAURI__.window) {
        if (typeof window.__TAURI__.window.getCurrentWindow === 'function') {
            return window.__TAURI__.window.getCurrentWindow();
        }
        if (typeof window.__TAURI__.window.getCurrent === 'function') {
            return window.__TAURI__.window.getCurrent();
        }
    }
    if (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.window) {
        if (typeof window.__TAURI_INTERNALS__.window.getCurrentWindow === 'function') {
            return window.__TAURI_INTERNALS__.window.getCurrentWindow();
        }
        if (typeof window.__TAURI_INTERNALS__.window.getCurrent === 'function') {
            return window.__TAURI_INTERNALS__.window.getCurrent();
        }
    }
    return null;
}

function moveWindow(dx, dy) {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win && typeof win.startDragging === 'function') {
            win.startDragging();
        }
    }
}

function minimizeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.minimize();
    }
}

function maximizeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.toggleMaximize();
    }
}

function closeWindow() {
    if (checkIsTauri()) {
        var win = getTauriWindow();
        if (win) win.close();
    }
}

async function openFileInNewWindow(path, name) {
    if (checkIsTauri()) {
        var invoke = getTauriInvoke();
        if (invoke) {
            return invoke('open_file_in_new_window', { path: path, name: name || null });
        }
    }
    console.error('[WindowManager] Not running in Tauri');
    throw new Error('Not running in Tauri');
}

return {
    checkIsTauri: checkIsTauri,
    getTauriInvoke: getTauriInvoke,
    getTauriWindow: getTauriWindow,
    moveWindow: moveWindow,
    minimizeWindow: minimizeWindow,
    maximizeWindow: maximizeWindow,
    closeWindow: closeWindow,
    openFileInNewWindow: openFileInNewWindow
};

})();
