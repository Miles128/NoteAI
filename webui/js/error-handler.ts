/**
 * error-handler.ts —— 全局错误捕获 + 自定义确认框。
 * 经典脚本（esbuild IIFE bundle：webui/js/error-handler.bundle.js），
 * 在模块脚本之前同步加载，确保尽早安装 onerror / unhandledrejection。
 */
(function() { 'use strict';

var el = document.getElementById('js-error-panel') as HTMLElement | null;
var log = document.getElementById('js-error-log') as HTMLElement | null;
var errors: string[] = [];

function showErrors() {
    if (!el || !log || errors.length === 0) return;
    el.style.display = 'block';
    log.textContent = errors.join('\n\n---\n\n');
}

window.onerror = function(msg: unknown, url: unknown, line: unknown, col: unknown, err: unknown) {
    var info = (err && (err as Error).stack)
        ? String((err as Error).stack)
        : (String(msg) + ' at ' + String(url) + ':' + String(line) + ':' + String(col));
    errors.push(info);
    showErrors();
    return false;
};

window.addEventListener('unhandledrejection', function(e) {
    var reason = (e as PromiseRejectionEvent).reason;
    var info = 'Promise rejection: ' + (reason && (reason as Error).stack ? String((reason as Error).stack) : String(reason));
    errors.push(info);
    showErrors();
});

window._customConfirm = function(message: string): Promise<boolean> {
    return new Promise(function(resolve) {
        var overlay = document.getElementById('custom-confirm-overlay') as HTMLElement | null;
        var msgEl = document.getElementById('custom-confirm-message') as HTMLElement | null;
        var okBtn = document.getElementById('custom-confirm-ok') as HTMLButtonElement | null;
        var cancelBtn = document.getElementById('custom-confirm-cancel') as HTMLButtonElement | null;
        if (!overlay || !msgEl || !okBtn || !cancelBtn) { resolve(window.confirm(message)); return; }
        msgEl.textContent = message;
        overlay.style.display = 'flex';
        okBtn.focus();
        function cleanup(result: boolean) {
            overlay!.style.display = 'none';
            okBtn!.removeEventListener('click', onOk);
            cancelBtn!.removeEventListener('click', onCancel);
            resolve(result);
        }
        function onOk() { cleanup(true); }
        function onCancel() { cleanup(false); }
        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
    });
};

})();
