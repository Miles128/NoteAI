/**
 * theme.ts —— 主题/排版（从 theme.js 渐进迁移到 TS）。
 * 运行时语义与迁移前一致。
 */
(function() { 'use strict';

var THEME_STORAGE_KEY = window.Storage.KEYS.THEME;
var ACCENT_STORAGE_KEY = window.Storage.KEYS.ACCENT_COLOR;
var TYPOGRAPHY_STORAGE_KEY = 'noteai_typography_settings';
var ACCENT_VALUES = new Set(['theme', 'blue', 'rust', 'teal', 'plum']);
var currentAccentColor = 'theme';
var FONT_FAMILIES: Record<string, string> = {
    system: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", sans-serif',
    sans: '"Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    serif: '"Songti SC", "Noto Serif SC", "Source Han Serif SC", Georgia, serif',
    mono: '"Iosevka Web", "iA Writer Mono S", "JetBrains Mono", "SF Mono", Consolas, monospace'
};
var FONT_STYLE_VALUES = new Set(['normal', 'bold', 'italic', 'bold-italic']);
var TYPOGRAPHY_ROLES = ['h1', 'h2', 'h3', 'body', 'quote'];
var DEFAULT_TYPOGRAPHY: Record<string, TypographyRow> = {
    h1: { family: 'serif', style: 'bold' },
    h2: { family: 'sans', style: 'bold' },
    h3: { family: 'sans', style: 'bold' },
    body: { family: 'system', style: 'normal' },
    quote: { family: 'serif', style: 'italic' }
};

function persistThemeLocal(theme: string): void {
    window.Storage.setRaw(THEME_STORAGE_KEY, theme, { silent: true });
}

function syncThemeRadioInputs(theme: string): void {
    document.querySelectorAll<HTMLInputElement>('input[name="theme"], input[name="theme-popup"]').forEach(function(radio) {
        radio.checked = radio.value === theme;
        var option = radio.closest('.theme-option');
        if (option) option.classList.toggle('active', radio.checked);
    });
}

function normalizeAccentColor(accent: string): string {
    return ACCENT_VALUES.has(accent) ? accent : 'theme';
}

function syncAccentInputs(accent: string): void {
    document.querySelectorAll<HTMLInputElement>('input[name="accent-color"]').forEach(function(radio) {
        radio.checked = radio.value === accent;
        var option = radio.closest('.accent-option');
        if (option) option.classList.toggle('active', radio.checked);
    });
}

function applyAccentColor(accent: string): void {
    accent = normalizeAccentColor(accent);
    currentAccentColor = accent;
    const html = document.documentElement;
    if (accent === 'theme') {
        html.removeAttribute('data-accent');
    } else {
        html.setAttribute('data-accent', accent);
    }
    syncAccentInputs(accent);
}

function setAccentColor(accent: string): void {
    accent = normalizeAccentColor(accent);
    applyAccentColor(accent);
    window.Storage.setRaw(ACCENT_STORAGE_KEY, accent, { silent: true });
}

function applyAccentBootstrap(): void {
    var accent = window.Storage.getRaw(ACCENT_STORAGE_KEY, 'theme', { silent: true }) as string;
    applyAccentColor(accent);
}

function normalizeFontFamily(value: string): string {
    return Object.prototype.hasOwnProperty.call(FONT_FAMILIES, value) ? value : 'system';
}

function normalizeFontStyle(value: string): string {
    return FONT_STYLE_VALUES.has(value) ? value : 'normal';
}

function fontWeightForStyle(style: string): string {
    return style === 'bold' || style === 'bold-italic' ? '700' : '400';
}

function fontStyleForStyle(style: string): string {
    return style === 'italic' || style === 'bold-italic' ? 'italic' : 'normal';
}

function normalizeTypography(input: any): Record<string, TypographyRow> {
    var source = input && typeof input === 'object' ? input : {};
    var out: Record<string, TypographyRow> = {};
    TYPOGRAPHY_ROLES.forEach(function(role) {
        var defaults = DEFAULT_TYPOGRAPHY[role];
        var row = source[role] && typeof source[role] === 'object' ? source[role] : {};
        out[role] = {
            family: normalizeFontFamily(row.family || defaults.family),
            style: normalizeFontStyle(row.style || defaults.style)
        };
    });
    return out;
}

function applyContentFonts(sidebarFont: string, previewFont: string): void {
    var root = document.documentElement;
    var sidebar = normalizeFontFamily(sidebarFont);
    var preview = normalizeFontFamily(previewFont);
    root.style.setProperty('--sidebar-font-family', FONT_FAMILIES[sidebar]);
    root.style.setProperty('--preview-font-family', FONT_FAMILIES[preview]);
}

function applyTypography(settings: any): Record<string, TypographyRow> {
    var typography = normalizeTypography(settings);
    var root = document.documentElement;
    TYPOGRAPHY_ROLES.forEach(function(role) {
        var row = typography[role];
        root.style.setProperty('--typo-' + role + '-font-family', FONT_FAMILIES[row.family]);
        root.style.setProperty('--typo-' + role + '-font-weight', fontWeightForStyle(row.style));
        root.style.setProperty('--typo-' + role + '-font-style', fontStyleForStyle(row.style));
    });
    window.Storage.setItem(TYPOGRAPHY_STORAGE_KEY, typography, { silent: true });
    return typography;
}

function restoreTypography(): Record<string, TypographyRow> {
    var saved = window.Storage.getItem(TYPOGRAPHY_STORAGE_KEY, DEFAULT_TYPOGRAPHY, { silent: true });
    return applyTypography(saved);
}

function toggleTheme(): void {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const lightIcon = document.getElementById('theme-icon-light') as HTMLElement | null;
    const darkIcon = document.getElementById('theme-icon-dark') as HTMLElement | null;

    if (currentTheme === 'light') {
        html.setAttribute('data-theme', 'dark');
        if (lightIcon) lightIcon.style.display = 'none';
        if (darkIcon) darkIcon.style.display = 'block';
    } else {
        html.setAttribute('data-theme', 'light');
        if (lightIcon) lightIcon.style.display = 'block';
        if (darkIcon) darkIcon.style.display = 'none';
    }

    var next = html.getAttribute('data-theme') || 'dark';
    syncThemeRadioInputs(next);
    persistThemeLocal(next);
    if (window.api) {
        window.api.saveThemePreference(next).catch(function(err) {
            console.warn('[Theme] saveThemePreference failed:', err);
        });
    }
}

function setTheme(theme: string): void {
    const html = document.documentElement;

    if (theme === 'system') {
        html.removeAttribute('data-theme');
        applySystemTheme();
    } else {
        html.setAttribute('data-theme', theme);
    }

    syncThemeRadioInputs(theme);
    persistThemeLocal(theme);

    if (window.api) {
        window.api.saveThemePreference(theme).catch(function(err) {
            console.warn('[Theme] saveThemePreference failed:', err);
        });
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function applySystemTheme(): void {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const html = document.documentElement;

    if (prefersDark) {
        html.setAttribute('data-theme', 'dark');
    } else {
        html.removeAttribute('data-theme');
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function initSystemThemeListener(): void {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        var currentTheme = window.Storage.getRaw(THEME_STORAGE_KEY, 'system', { silent: true }) as string;
        if (currentTheme === 'system') {
            applySystemTheme();
        }
    });
}

async function applyThemeBootstrap(): Promise<void> {
    var pref: string | null = null;
    try {
        // 优先复用 state 门面（与启动期 loadThemePreference 共享同一 RPC）
        if (window.state && typeof window.state.loadThemePreference === 'function') {
            pref = await window.state.loadThemePreference();
        } else if (window.api && typeof window.api.getThemePreference === 'function') {
            pref = await window.api.getThemePreference();
        }
    } catch (e) {
        console.warn('[Theme] getThemePreference failed:', e);
    }
    if (pref === null || pref === undefined || String(pref).trim() === '') {
        pref = window.Storage.getRaw(THEME_STORAGE_KEY, null, { silent: true }) as string | null;
    }
    pref = pref || 'system';

    persistThemeLocal(pref);
    syncThemeRadioInputs(pref);

    if (pref === 'system') {
        applySystemTheme();
    } else {
        applyTheme(pref);
    }
    applyAccentBootstrap();
    restoreTypography();

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function applyTheme(theme: string): void {
    const html = document.documentElement;
    const lightIcon = document.getElementById('theme-icon-light') as HTMLElement | null;
    const darkIcon = document.getElementById('theme-icon-dark') as HTMLElement | null;

    if (theme === 'system') {
        html.removeAttribute('data-theme');
    } else {
        html.setAttribute('data-theme', theme);
    }

    if (lightIcon && darkIcon) {
        if (theme === 'light') {
            lightIcon.style.display = 'block';
            darkIcon.style.display = 'none';
        } else if (theme === 'dark') {
            lightIcon.style.display = 'none';
            darkIcon.style.display = 'block';
        } else {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (prefersDark) {
                lightIcon.style.display = 'none';
                darkIcon.style.display = 'block';
            } else {
                lightIcon.style.display = 'block';
                darkIcon.style.display = 'none';
            }
        }
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function restoreSidebarWidth(): void {
    const sidebar = document.querySelector('.sidebar') as HTMLElement | null;
    if (!sidebar) return;
    const savedWidth = window.Storage.getRaw(window.Storage.KEYS.SIDEBAR_WIDTH, null, { silent: true }) as string | null;
    if (savedWidth) {
        const w = parseInt(savedWidth, 10);
        if (w >= 180 && w <= 600) {
            sidebar.style.width = w + 'px';
        }
    }
}

function initResizer(): void {
    const resizer = document.getElementById('sidebar-resizer') as HTMLElement | null;
    const sidebar = document.querySelector('.sidebar') as HTMLElement | null;
    if (!resizer || !sidebar) return;
    let isResizing = false;
    let startX = 0;
    let startWidth = 0;

    restoreSidebarWidth();

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        sidebar.classList.add('resizing-active');
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        if (window.Graph3Tier && window.Graph3Tier.pauseResize) window.Graph3Tier.pauseResize();
        e.preventDefault();
        e.stopPropagation();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const delta = e.clientX - startX;
        const newWidth = startWidth + delta;
        if (newWidth >= 180 && newWidth <= 600) {
            sidebar.style.width = newWidth + 'px';
            sidebar.style.minWidth = newWidth + 'px';
        }
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        sidebar.classList.remove('resizing-active');
        sidebar.style.minWidth = '';
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        window.Storage.setRaw(window.Storage.KEYS.SIDEBAR_WIDTH, String(sidebar.offsetWidth));
        if (window.Graph3Tier && window.Graph3Tier.resumeResize) window.Graph3Tier.resumeResize();
    });
}

function initPreviewResizer(): void {
    const resizer = document.getElementById('preview-resizer') as HTMLElement | null;
    const previewPanel = document.getElementById('preview-panel') as HTMLElement | null;
    if (!resizer || !previewPanel) {
        return;
    }
    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
        e.stopPropagation();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const panelRect = previewPanel.getBoundingClientRect();
        const newWidth = panelRect.right - e.clientX;
        if (newWidth >= 300 && newWidth <= 1200) {
            previewPanel.style.width = newWidth + 'px';
        }
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });
}

function showAboutPanel(): void {
    const aboutContent = `
        <h2>NoteAI</h2>
        <p class="about-version">${window.t('about.version')}</p>
        <p class="about-desc">${window.t('about.desc')}</p>
        <div class="about-features">
            <h3>${window.t('about.coreFeatures')}</h3>
            <ul>
                <li>${window.t('about.feature1')}</li>
                <li>${window.t('about.feature2')}</li>
                <li>${window.t('about.feature3')}</li>
                <li>${window.t('about.feature4')}</li>
                <li>${window.t('about.feature5')}</li>
                <li>${window.t('about.feature6')}</li>
                <li>${window.t('about.feature7')}</li>
                <li>${window.t('about.feature8')}</li>
            </ul>
        </div>
        <div class="about-features">
            <h3>${window.t('about.techArchitecture')}</h3>
            <ul>
                <li>${window.t('about.techFrontend')}</li>
                <li>${window.t('about.techBackend')}</li>
                <li>${window.t('about.techEditor')}</li>
                <li>${window.t('about.techLlm')}</li>
            </ul>
        </div>
        <p class="about-author" style="margin-top: 20px; font-size: 15px; color: var(--text);">${window.t('about.author')}</p>
        <p class="about-email" style="margin-top: 4px; font-size: 13px; color: var(--text-muted);">mai.yuxiang@foxmail.com</p>
        <p class="about-tech" style="margin-top: 4px;">${window.t('about.opensource')}</p>
    `;

    document.getElementById('about-panel-content')!.innerHTML = aboutContent;
    document.getElementById('about-panel')!.classList.add('active');
}

function hideAboutPanel(): void {
    document.getElementById('about-panel')!.classList.remove('active');
}

window.setTheme = setTheme;
window.setAccentColor = setAccentColor;
window.setFontSize = applyFontSize;

// 本模块由 main.mjs 动态 import，执行时 DOM 已解析完成，直接同步（不再依赖 DOMContentLoaded 重放）
(function() {
    var savedTheme = window.Storage.getRaw(THEME_STORAGE_KEY, 'system', { silent: true }) as string;
    syncThemeRadioInputs(savedTheme);
    syncAccentInputs(currentAccentColor);
})();

var FONT_SCALE_MAP: Record<string, number> = { small: 1, medium: 1.15, large: 1.3 };

function setFontSize(size: string): void {
    var scale = FONT_SCALE_MAP[size] || 1;
    document.documentElement.style.setProperty('--font-scale', String(scale));
    document.querySelectorAll<HTMLInputElement>('input[name="font-size"]').forEach(function(radio) {
        radio.checked = radio.value === size;
    });
}

function applyFontSize(size: string): void {
    setFontSize(size);
    window.Storage.setRaw(window.Storage.KEYS.FONT_SIZE, size);
    if (window.SettingsModule && window.SettingsModule.saveFontSize) {
        window.SettingsModule.saveFontSize(size);
    }
}

function restoreFontSize(): void {
    var saved = window.Storage.getRaw(window.Storage.KEYS.FONT_SIZE, 'small', { silent: true }) as string;
    setFontSize(saved);
}

window.ThemeModule = {
    toggleTheme,
    setTheme,
    applySystemTheme,
    initSystemThemeListener,
    applyTheme,
    syncThemeRadioInputs,
    applyAccentColor,
    setAccentColor,
    applyAccentBootstrap,
    persistThemeLocal,
    applyThemeBootstrap,
    setFontSize: applyFontSize,
    restoreFontSize,
    applyContentFonts,
    applyTypography,
    restoreTypography,
    normalizeTypography,
    restoreSidebarWidth,
    initResizer,
    initPreviewResizer,
    showAboutPanel,
    hideAboutPanel
};

})();