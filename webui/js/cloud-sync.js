(function() { 'use strict';

function renderPlaceholder() {
    var container = document.getElementById('cloud-sync-providers');
    if (!container) return;
    container.innerHTML =
        '<div class="cloud-sync-placeholder">' +
            '<div class="cloud-sync-placeholder-title">' + window.t('cloudSync.disabledTitle') + '</div>' +
            '<p>' + window.t('cloudSync.disabledBody') + '</p>' +
            '<span>' + window.t('cloudSync.disabledBadge') + '</span>' +
        '</div>';
}

async function refresh() {
    renderPlaceholder();
    if (!window.api || !window.api.cloudSyncListProviders) return;
    try {
        await window.api.cloudSyncListProviders();
    } catch (_e) {
        // The page is intentionally a non-actionable placeholder.
    }
}

window.CloudSyncModule = {
    init: renderPlaceholder,
    refresh: refresh
};

})();
