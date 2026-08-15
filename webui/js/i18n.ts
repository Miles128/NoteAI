/**
 * i18n.ts —— 国际化（从 i18n.js 渐进迁移到 TS）。
 * window.t 提供文案查找，I18nModule 提供加载/切换/应用。
 */
(function() { 'use strict';

var _messages: Record<string, any> = {};
var _locale = 'zh-CN';
var _ready = false;
var _readyPromise: Promise<any> | null = null;

function _getNested(obj: any, path: string): any {
    if (!obj || !path) return undefined;
    var parts = path.split('.');
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
        if (cur == null || typeof cur !== 'object') return undefined;
        cur = cur[parts[i]];
    }
    return cur;
}

function t(key: string, params?: Record<string, string | number>): string {
    var msg = _getNested(_messages, key);
    if (msg == null || msg === '') return key;
    if (params && typeof params === 'object') {
        Object.keys(params).forEach(function(k) {
            msg = String(msg).replace(new RegExp('\\{' + k + '\\}', 'g'), String(params[k]));
        });
    }
    return msg;
}

function _localeFile(locale: string): string {
    return locale === 'en' ? 'en.json' : 'zh-CN.json';
}

async function loadLocale(locale: string): Promise<void> {
    var lang = locale === 'en' ? 'en' : 'zh-CN';
    try {
        var resp = await fetch('locales/' + _localeFile(lang));
        if (!resp.ok) {
            throw new Error('Failed to load locale: ' + lang);
        }
        _messages = await resp.json();
    } catch (e) {
        console.warn('[i18n] ' + (e as Error).message + ', falling back to raw keys');
        _messages = {};
    }
    _locale = lang;
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
    applyDomI18n();
    document.dispatchEvent(new CustomEvent('localechange', { detail: { locale: _locale } }));
    _ready = true;
}

function applyDomI18n(root?: ParentNode): void {
    root = root || document;
    root.querySelectorAll('[data-i18n]').forEach(function(el) {
        var key = el.getAttribute('data-i18n');
        if (!key) return;
        var params: Record<string, string> = {};
        var countAttr = el.getAttribute('data-i18n-count');
        if (countAttr != null && countAttr !== '') {
            params.count = countAttr;
        }
        el.textContent = t(key, Object.keys(params).length ? params : undefined);
    });
    root.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-placeholder');
        if (key) (el as HTMLInputElement).placeholder = t(key);
    });
    root.querySelectorAll('[data-i18n-title]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-title');
        if (key) (el as HTMLElement).title = t(key);
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

async function initI18n(): Promise<any> {
    if (_readyPromise) return _readyPromise;
    _readyPromise = (async function() {
        var locale = 'zh-CN';
        try {
            // 优先复用 state 门面的 uiConfig（启动期已预热，避免重复 RPC）
            if (window.state && window.state.loadUiConfig) {
                var cfg = await window.state.loadUiConfig();
                if (cfg && cfg.locale) locale = cfg.locale;
            } else if (window.api && window.api.getUiConfig) {
                var cfg2 = await window.api.getUiConfig();
                if (cfg2 && cfg2.locale) locale = cfg2.locale;
            }
        } catch (_e) { /* use default */ }
        await loadLocale(locale);
    })();
    return _readyPromise;
}

async function setLocale(locale: string): Promise<void> {
    await loadLocale(locale === 'en' ? 'en' : 'zh-CN');
    if (window.api && window.api.saveUiConfig) {
        await window.api.saveUiConfig({ locale: _locale });
    }
}

function whenReady(fn: () => void): void {
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