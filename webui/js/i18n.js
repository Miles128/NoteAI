(function() { 'use strict';

var _messages = {};
var _locale = 'zh-CN';
var _ready = false;
var _readyPromise = null;

function _getNested(obj, path) {
    if (!obj || !path) return undefined;
    var parts = path.split('.');
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
        if (cur == null || typeof cur !== 'object') return undefined;
        cur = cur[parts[i]];
    }
    return cur;
}

function t(key, params) {
    var msg = _getNested(_messages, key);
    if (msg == null || msg === '') return key;
    if (params && typeof params === 'object') {
        Object.keys(params).forEach(function(k) {
            msg = String(msg).replace(new RegExp('\\{' + k + '\\}', 'g'), String(params[k]));
        });
    }
    return msg;
}

function _localeFile(locale) {
    return locale === 'en' ? 'en.json' : 'zh-CN.json';
}

async function loadLocale(locale) {
    var lang = locale === 'en' ? 'en' : 'zh-CN';
    var resp = await fetch('locales/' + _localeFile(lang));
    if (!resp.ok) {
        throw new Error('Failed to load locale: ' + lang);
    }
    _messages = await resp.json();
    _locale = lang;
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
    applyDomI18n();
    document.dispatchEvent(new CustomEvent('localechange', { detail: { locale: _locale } }));
    _ready = true;
}

function applyDomI18n(root) {
    root = root || document;
    root.querySelectorAll('[data-i18n]').forEach(function(el) {
        var key = el.getAttribute('data-i18n');
        if (!key) return;
        var params = {};
        var countAttr = el.getAttribute('data-i18n-count');
        if (countAttr != null && countAttr !== '') {
            params.count = countAttr;
        }
        el.textContent = t(key, Object.keys(params).length ? params : undefined);
    });
    root.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-placeholder');
        if (key) el.placeholder = t(key);
    });
    root.querySelectorAll('[data-i18n-title]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-title');
        if (key) el.title = t(key);
    });
    root.querySelectorAll('[data-i18n-aria]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-aria');
        if (key) el.setAttribute('aria-label', t(key));
    });
    root.querySelectorAll('[data-i18n-html]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-html');
        if (key) el.innerHTML = t(key);
    });
}

async function initI18n() {
    if (_readyPromise) return _readyPromise;
    _readyPromise = (async function() {
        var locale = 'zh-CN';
        try {
            if (window.api && window.api.getUiConfig) {
                var cfg = await window.api.getUiConfig();
                if (cfg && cfg.locale) locale = cfg.locale;
            }
        } catch (_e) { /* use default */ }
        await loadLocale(locale);
    })();
    return _readyPromise;
}

async function setLocale(locale) {
    await loadLocale(locale === 'en' ? 'en' : 'zh-CN');
    if (window.api && window.api.saveUiConfig) {
        await window.api.saveUiConfig({ locale: _locale });
    }
}

function whenReady(fn) {
    if (_ready) {
        fn();
        return;
    }
    initI18n().then(fn).catch(function() { fn(); });
}

window.t = t;
window.I18nModule = {
    t: t,
    loadLocale: loadLocale,
    setLocale: setLocale,
    applyDomI18n: applyDomI18n,
    initI18n: initI18n,
    whenReady: whenReady,
    getLocale: function() { return _locale; },
    isReady: function() { return _ready; },
};

})();
