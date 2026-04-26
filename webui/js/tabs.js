(function() {
    function switchTab(tabIndex) {
        document.querySelectorAll('.tab-btn').forEach(function(item, i) {
            item.classList.toggle('active', i === tabIndex);
        });
        document.querySelectorAll('.tab-content').forEach(function(content, i) {
            content.classList.toggle('active', i === tabIndex);
        });

        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');

        if (contentPanel && previewPanel) {
            contentPanel.style.display = 'flex';
            previewPanel.style.display = 'none';
        }
    }

    function showContentView() {
        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');

        if (contentPanel) contentPanel.style.display = 'flex';
        if (previewPanel) previewPanel.style.display = 'none';
    }

    function showPreviewView() {
        var contentPanel = document.getElementById('content-panel');
        var previewPanel = document.getElementById('preview-panel');

        if (contentPanel) contentPanel.style.display = 'none';
        if (previewPanel) previewPanel.style.display = 'flex';
    }

    function initTabs() {
        document.querySelectorAll('.tab-btn').forEach(function(btn, index) {
            btn.addEventListener('click', function() {
                switchTab(index);
            });
        });
    }

    window.tabs = {
        switchTab: switchTab,
        showContentView: showContentView,
        showPreviewView: showPreviewView,
        initTabs: initTabs
    };

    window.TabsModule = window.tabs;

    window.switchTab = switchTab;
    window.showContentView = showContentView;
    window.showPreviewView = showPreviewView;
})();
