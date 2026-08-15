(function() {
    'use strict';

    function switchTab(tabIndex: any) {
        document.querySelectorAll('.tab-content').forEach((content, i) => {
            content.classList.toggle('active', i === tabIndex);
        });

        if (tabIndex === 0) {
            setTimeout(() => {
                if (typeof window.openDownloadModal === 'function') {
                    window.openDownloadModal();
                }
            }, 50);
        }
    }

    window.switchTab = switchTab;
    window.TabsModule = { switchTab };
})();

