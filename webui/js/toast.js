(function() {
    function updateStatus(text) {
        var el = document.getElementById('status-bar');
        if (el) {
            el.textContent = text;
        }
    }

    function updateProgress(elementId, progress, text) {
        var fill = document.getElementById(elementId + '-fill');
        var statusEl = document.getElementById(elementId.replace('progress', 'status'));

        if (fill) {
            fill.style.width = (progress * 100) + '%';
        }
        if (statusEl) {
            statusEl.textContent = text;
        }
    }

    window.toast = {
        updateStatus: updateStatus,
        updateProgress: updateProgress
    };
})();
