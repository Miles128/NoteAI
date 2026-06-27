(function() {
    'use strict';

    function updateStatus(text) {
        if (window.StatusbarModule && window.StatusbarModule.updateMessage) {
            window.StatusbarModule.updateMessage(text || '');
            return;
        }
        const el = document.getElementById('status-bar') || document.getElementById('statusbar-message');
        if (el) {
            el.textContent = text;
        }
    }

    function updateProgress(elementId, progress, text) {
        const fill = document.getElementById(elementId + '-fill');
        const statusEl = document.getElementById(elementId.replace('progress', 'status'));

        if (fill) {
            fill.style.width = (progress * 100) + '%';
        }
        if (statusEl) {
            statusEl.textContent = text;
        }
    }

    window.toast = {
        updateStatus,
        updateProgress
    };

    window.updateStatus = updateStatus;
    window.updateProgress = updateProgress;
})();

