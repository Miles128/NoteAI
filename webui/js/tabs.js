(function() {
    'use strict';

    function switchTab(tabIndex) {
        document.querySelectorAll('.tab-content').forEach((content, i) => {
            content.classList.toggle('active', i === tabIndex);
        });

        if (tabIndex === 0) {
            setTimeout(() => {
                if (window.DownloaderModule && window.DownloaderModule.openDownloadModal) {
                    window.DownloaderModule.openDownloadModal();
                }
            }, 50);
        }
    }

    window.switchTab = switchTab;
    window.TabsModule = { switchTab };
})();

