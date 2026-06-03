(function() { 'use strict';

var PROVIDERS = {
    onedrive: { name: 'OneDrive', icon: '☁️', color: '#0078d4' },
    baidu: { name: '百度网盘', icon: '💾', color: '#06a7ff' },
    aliyun: { name: '阿里云盘', icon: '📀', color: '#ff6a00' },
    pan123: { name: '123云盘', icon: '📁', color: '#2b7dff' },
    jianguoyun: { name: '坚果云', icon: '🌰', color: '#3cb034' },
    tencent_cos: { name: '腾讯云COS', icon: '☁️', color: '#006eff' },
    icloud: { name: 'iCloud', icon: '🍎', color: '#333' }
};

var PROVIDER_KEYS = ['onedrive', 'baidu', 'aliyun', 'pan123', 'jianguoyun', 'tencent_cos', 'icloud'];

var _providerStatus = {};

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function initCloudSync() {
    var container = document.getElementById('cloud-sync-providers');
    if (!container) return;

    PROVIDER_KEYS.forEach(function(key) {
        var card = renderProviderCard(key);
        container.appendChild(card);
    });

    loadProviderStatus();
}

function renderProviderCard(providerName) {
    var info = PROVIDERS[providerName];
    var card = document.createElement('div');
    card.className = 'cloud-sync-card';
    card.setAttribute('data-provider', providerName);

    var status = _providerStatus[providerName];
    var connected = status && status.authenticated;
    var authFields = (status && status.auth_fields) || [];

    var headerHtml = '<div class="cloud-sync-card-header">' +
        '<div class="cloud-sync-provider-info">' +
        '<span class="cloud-sync-provider-icon" style="background:' + info.color + '20;color:' + info.color + '">' + info.icon + '</span>' +
        '<span class="cloud-sync-provider-name">' + escapeHtml(info.name) + '</span>' +
        '</div>' +
        '<span class="cloud-sync-status-badge ' + (connected ? 'connected' : 'disconnected') + '">' +
        (connected ? window.t('cloudSync.connected') : window.t('cloudSync.disconnected')) + '</span>' +
        '</div>';

    var authHtml = '<div class="cloud-sync-auth-fields" data-provider="' + providerName + '">';
    if (authFields.length > 0) {
        authFields.forEach(function(field) {
            var inputType = (field.type === 'password') ? 'password' : 'text';
            authHtml += '<div class="form-group">' +
                '<div class="form-field"><div class="form-label">' + escapeHtml(field.label || field.key) + '</div>' +
                '<input type="' + inputType + '" class="form-input cloud-sync-auth-input" ' +
                'data-provider="' + providerName + '" data-field="' + escapeHtml(field.key) + '" ' +
                'placeholder="' + escapeHtml(field.placeholder || '') + '" ' +
                'value="' + escapeHtml(field.value || '') + '">' +
                '</div></div>';
        });
    }
    authHtml += '</div>';

    var actionsHtml = '<div class="cloud-sync-actions">' +
        '<button class="btn btn-primary cloud-sync-btn-auth" data-provider="' + providerName + '">' +
        (connected ? window.t('settings.saveConfig') : window.t('cloudSync.authLogin')) + '</button>' +
        '<button class="btn btn-secondary cloud-sync-btn-push" data-provider="' + providerName + '"' +
        (connected ? '' : ' disabled') + '>' + window.t('cloudSync.push') + '</button>' +
        '<button class="btn btn-secondary cloud-sync-btn-pull" data-provider="' + providerName + '"' +
        (connected ? '' : ' disabled') + '>' + window.t('cloudSync.pull') + '</button>' +
        '<button class="btn btn-secondary cloud-sync-btn-disconnect" data-provider="' + providerName + '"' +
        (connected ? '' : ' disabled') + '>' + window.t('cloudSync.disconnect') + '</button>' +
        '</div>';

    var syncInfoHtml = '<div class="cloud-sync-meta">' +
        '<span class="cloud-sync-last-time" data-provider="' + providerName + '">尚未同步</span>' +
        '<div class="cloud-sync-progress" data-provider="' + providerName + '"></div>' +
        '</div>';

    card.innerHTML = headerHtml + authHtml + actionsHtml + syncInfoHtml;

    card.querySelector('.cloud-sync-btn-auth').addEventListener('click', function() {
        handleAuth(providerName);
    });
    card.querySelector('.cloud-sync-btn-push').addEventListener('click', function() {
        handlePush(providerName);
    });
    card.querySelector('.cloud-sync-btn-pull').addEventListener('click', function() {
        handlePull(providerName);
    });
    card.querySelector('.cloud-sync-btn-disconnect').addEventListener('click', function() {
        handleDisconnect(providerName);
    });

    return card;
}

async function loadProviderStatus() {
    try {
        var result = await window.api.cloudSyncListProviders();
        if (result && result.success && result.providers) {
            result.providers.forEach(function(p) {
                _providerStatus[p.name] = p;
                updateProviderCard(p.name, p);
            });
        }
    } catch (e) {
        console.error('[CloudSync] loadProviderStatus error:', e);
    }
}

function updateProviderCard(providerName, status) {
    var card = document.querySelector('.cloud-sync-card[data-provider="' + providerName + '"]');
    if (!card) return;

    var connected = status && status.authenticated;
    var authFields = (status && status.auth_fields) || [];

    var badge = card.querySelector('.cloud-sync-status-badge');
    if (badge) {
        badge.className = 'cloud-sync-status-badge ' + (connected ? 'connected' : 'disconnected');
        badge.textContent = connected ? window.t('cloudSync.connected') : window.t('cloudSync.disconnected');
    }

    var authBtn = card.querySelector('.cloud-sync-btn-auth');
    if (authBtn) {
        authBtn.textContent = connected ? window.t('settings.saveConfig') : window.t('cloudSync.authLogin');
    }

    var pushBtn = card.querySelector('.cloud-sync-btn-push');
    if (pushBtn) pushBtn.disabled = !connected;

    var pullBtn = card.querySelector('.cloud-sync-btn-pull');
    if (pullBtn) pullBtn.disabled = !connected;

    var disconnectBtn = card.querySelector('.cloud-sync-btn-disconnect');
    if (disconnectBtn) disconnectBtn.disabled = !connected;

    var lastTimeEl = card.querySelector('.cloud-sync-last-time');
    if (lastTimeEl) {
        var lastSync = status.last_push || status.last_pull || '';
        lastTimeEl.textContent = lastSync ? window.t('cloudSync.lastSync', { time: new Date(lastSync * 1000).toLocaleString() }) : window.t('cloudSync.neverSynced');
    }

    var authContainer = card.querySelector('.cloud-sync-auth-fields');
    if (authContainer && authFields.length > 0) {
        var existingInputs = authContainer.querySelectorAll('.cloud-sync-auth-input');
        var existingMap = {};
        existingInputs.forEach(function(input) {
            existingMap[input.dataset.field] = input.value;
        });

        authContainer.innerHTML = '';
        authFields.forEach(function(field) {
            var inputType = (field.type === 'password') ? 'password' : 'text';
            var preservedValue = existingMap[field.key] || field.value || '';
            var fieldHtml = '<div class="form-group">' +
                '<div class="form-field"><div class="form-label">' + escapeHtml(field.label || field.key) + '</div>' +
                '<input type="' + inputType + '" class="form-input cloud-sync-auth-input" ' +
                'data-provider="' + providerName + '" data-field="' + escapeHtml(field.key) + '" ' +
                'placeholder="' + escapeHtml(field.placeholder || '') + '" ' +
                'value="' + escapeHtml(preservedValue) + '">' +
                '</div></div>';
            authContainer.insertAdjacentHTML('beforeend', fieldHtml);
        });
    }
}

async function handleAuth(providerName) {
    var card = document.querySelector('.cloud-sync-card[data-provider="' + providerName + '"]');
    if (!card) return;

    var inputs = card.querySelectorAll('.cloud-sync-auth-input');
    var credentials = {};
    inputs.forEach(function(input) {
        credentials[input.dataset.field] = input.value;
    });

    var btn = card.querySelector('.cloud-sync-btn-auth');
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('cloudSync.authing');
    }

    try {
        var result = await window.api.cloudSyncAuth(providerName, credentials);
        if (result && result.success) {
            showProviderProgress(providerName, window.t('cloudSync.authSuccess'), 'success');
            await loadProviderStatus();
        } else {
            showProviderProgress(providerName, (result && result.message) || window.t('cloudSync.authFailed'), 'error');
        }
    } catch (e) {
        showProviderProgress(providerName, window.t('cloudSync.authFailedMsg', { message: e.message }), 'error');
    } finally {
        if (btn) {
            var status = _providerStatus[providerName];
            btn.disabled = false;
            btn.textContent = (status && status.connected) ? window.t('settings.saveConfig') : window.t('cloudSync.authLogin');
        }
    }
}

async function handlePush(providerName) {
    var btn = document.querySelector('.cloud-sync-btn-push[data-provider="' + providerName + '"]');
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('cloudSync.pushing');
    }
    showProviderProgress(providerName, window.t('cloudSync.pushingStatus'), 'info');

    try {
        var result = await window.api.cloudSyncPush(providerName);
        if (result && result.success) {
            showProviderProgress(providerName, window.t('cloudSync.pushDone'), 'success');
            await loadProviderStatus();
        } else {
            showProviderProgress(providerName, (result && result.message) || window.t('cloudSync.pushFailed'), 'error');
        }
    } catch (e) {
        showProviderProgress(providerName, window.t('cloudSync.pushFailedMsg', { message: e.message }), 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = window.t('cloudSync.push');
        }
    }
}

async function handlePull(providerName) {
    var btn = document.querySelector('.cloud-sync-btn-pull[data-provider="' + providerName + '"]');
    if (btn) {
        btn.disabled = true;
        btn.textContent = window.t('cloudSync.pulling');
    }
    showProviderProgress(providerName, window.t('cloudSync.pullingStatus'), 'info');

    try {
        var result = await window.api.cloudSyncPull(providerName);
        if (result && result.success) {
            showProviderProgress(providerName, window.t('cloudSync.pullDone'), 'success');
            await loadProviderStatus();
        } else {
            showProviderProgress(providerName, (result && result.message) || window.t('cloudSync.pullFailed'), 'error');
        }
    } catch (e) {
        showProviderProgress(providerName, window.t('cloudSync.pullFailedMsg', { message: e.message }), 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = window.t('cloudSync.pull');
        }
    }
}

async function handleDisconnect(providerName) {
    var btn = document.querySelector('.cloud-sync-btn-disconnect[data-provider="' + providerName + '"]');
    if (btn) {
        btn.disabled = true;
    }

    try {
        var result = await window.api.cloudSyncDisconnect(providerName);
        if (result && result.success) {
            showProviderProgress(providerName, window.t('cloudSync.disconnectDone'), 'success');
            await loadProviderStatus();
        } else {
            showProviderProgress(providerName, (result && result.message) || window.t('cloudSync.disconnectFailed'), 'error');
        }
    } catch (e) {
        showProviderProgress(providerName, window.t('cloudSync.disconnectFailedMsg', { message: e.message }), 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = window.t('cloudSync.disconnect');
        }
    }
}

function showProviderProgress(providerName, message, type) {
    var progressEl = document.querySelector('.cloud-sync-progress[data-provider="' + providerName + '"]');
    if (!progressEl) return;

    var className = 'cloud-sync-progress-msg';
    if (type === 'success') className += ' progress-success';
    else if (type === 'error') className += ' progress-error';
    else className += ' progress-info';

    progressEl.innerHTML = '<span class="' + className + '">' + escapeHtml(message) + '</span>';

    if (type === 'success' || type === 'error') {
        setTimeout(function() {
            progressEl.innerHTML = '';
        }, 5000);
    }
}

window.CloudSyncModule = { init: initCloudSync };

})();
