(function() {
    'use strict';
    var el = document.getElementById('js-error-panel');
    var log = document.getElementById('js-error-log');
    var errors = [];
    function showErrors() {
        if (errors.length === 0) return;
        el.style.display = 'block';
        log.textContent = errors.join('\n\n---\n\n');
    }
    window.onerror = function(msg, url, line, col, err) {
        var info = (err && err.stack) ? err.stack : (msg + ' at ' + url + ':' + line + ':' + col);
        errors.push(info);
        showErrors();
    };
    window.addEventListener('unhandledrejection', function(e) {
        var info = 'Promise rejection: ' + (e.reason && e.reason.stack ? e.reason.stack : String(e.reason));
        errors.push(info);
        showErrors();
    });

    window._customConfirm = function(message) {
        return new Promise(function(resolve) {
            var overlay = document.getElementById('custom-confirm-overlay');
            var msgEl = document.getElementById('custom-confirm-message');
            var okBtn = document.getElementById('custom-confirm-ok');
            var cancelBtn = document.getElementById('custom-confirm-cancel');
            if (!overlay) { resolve(window.confirm(message)); return; }
            msgEl.textContent = message;
            overlay.style.display = 'flex';
            okBtn.focus();
            function cleanup(result) {
                overlay.style.display = 'none';
                okBtn.removeEventListener('click', onOk);
                cancelBtn.removeEventListener('click', onCancel);
                resolve(result);
            }
            function onOk() { cleanup(true); }
            function onCancel() { cleanup(false); }
            okBtn.addEventListener('click', onOk);
            cancelBtn.addEventListener('click', onCancel);
        });
    };
})();
