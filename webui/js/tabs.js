(function() {
    'use strict';

    function switchTab(tabIndex) {
        document.querySelectorAll('.tab-btn').forEach((item, i) => {
            item.classList.toggle('active', i === tabIndex);
        });
        document.querySelectorAll('.tab-content').forEach((content, i) => {
            content.classList.toggle('active', i === tabIndex);
        });

        const contentPanel = document.getElementById('content-panel');
        const previewPanel = document.getElementById('preview-panel');

        if (contentPanel && previewPanel) {
            contentPanel.style.display = 'flex';
            previewPanel.style.display = 'none';
        }
    }

    function showContentView() {
        const contentPanel = document.getElementById('content-panel');
        const previewPanel = document.getElementById('preview-panel');

        if (contentPanel) contentPanel.style.display = 'flex';
        if (previewPanel) previewPanel.style.display = 'none';
    }

    function showPreviewView() {
        const contentPanel = document.getElementById('content-panel');
        const previewPanel = document.getElementById('preview-panel');

        if (contentPanel) contentPanel.style.display = 'none';
        if (previewPanel) previewPanel.style.display = 'flex';
    }

    window.tabs = {
        switchTab,
        showContentView,
        showPreviewView
    };

    window.TabsModule = window.tabs;

    window.switchTab = switchTab;
    window.showContentView = showContentView;
    window.showPreviewView = showPreviewView;
})();
