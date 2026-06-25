(function() { 'use strict';

var THEME_STORAGE_KEY = 'noteai_theme';
var SIDEBAR_FONT_KEY = 'noteai_sidebar_font_family';
var PREVIEW_FONT_KEY = 'noteai_preview_font_family';
var FONT_FAMILY_MAP = {
    system: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
    sans: '"PingFang SC", "Microsoft YaHei", "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
    serif: '"Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", Georgia, serif',
    mono: '"SF Mono", "JetBrains Mono", "Iosevka Web", Consolas, monospace'
};

function persistThemeLocal(theme) {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch (_e) { /* noop */ }
}

function syncThemeRadioInputs(theme) {
    document.querySelectorAll('input[name="theme"], input[name="theme-popup"]').forEach(function(radio) {
        radio.checked = radio.value === theme;
    });
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const lightIcon = document.getElementById('theme-icon-light');
    const darkIcon = document.getElementById('theme-icon-dark');

    if (currentTheme === 'light') {
        html.setAttribute('data-theme', 'dark');
        lightIcon.style.display = 'none';
        darkIcon.style.display = 'block';
    } else {
        html.setAttribute('data-theme', 'light');
        lightIcon.style.display = 'block';
        darkIcon.style.display = 'none';
    }

    var next = html.getAttribute('data-theme') || 'dark';
    persistThemeLocal(next);
    if (window.api) {
        window.api.saveThemePreference(next).catch(function(err) {
            console.warn('[Theme] saveThemePreference failed:', err);
        });
    }
}

function setTheme(theme) {
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

function applySystemTheme() {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const html = document.documentElement;

    if (prefersDark) {
        html.setAttribute('data-theme', 'dark');
    } else {
        html.setAttribute('data-theme', 'light');
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function initSystemThemeListener() {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        var currentTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'system';
        if (currentTheme === 'system') {
            applySystemTheme();
        }
    });
}

async function applyThemeBootstrap() {
    var pref = null;
    try {
        if (window.api && typeof window.api.getThemePreference === 'function') {
            pref = await window.api.getThemePreference();
        }
    } catch (e) {
        console.warn('[Theme] getThemePreference failed:', e);
    }
    if (pref === null || pref === undefined || String(pref).trim() === '') {
        pref = localStorage.getItem(THEME_STORAGE_KEY);
    }
    pref = pref || 'system';

    persistThemeLocal(pref);
    syncThemeRadioInputs(pref);

    if (pref === 'system') {
        applySystemTheme();
    } else {
        applyTheme(pref);
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function applyTheme(theme) {
    const html = document.documentElement;
    const lightIcon = document.getElementById('theme-icon-light');
    const darkIcon = document.getElementById('theme-icon-dark');

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

function restoreSidebarWidth() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const savedWidth = localStorage.getItem('sidebar-width');
    if (savedWidth) {
        const w = parseInt(savedWidth, 10);
        if (w >= 180 && w <= 600) {
            sidebar.style.width = w + 'px';
        }
    }
}

function initResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    const sidebar = document.querySelector('.sidebar');
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
        if (typeof Graph3Tier !== 'undefined') Graph3Tier.pauseResize();
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
        localStorage.setItem('sidebar-width', sidebar.offsetWidth);
        if (typeof Graph3Tier !== 'undefined') Graph3Tier.resumeResize();
    });
}

function initPreviewResizer() {
    const resizer = document.getElementById('preview-resizer');
    const previewPanel = document.getElementById('preview-panel');
    if (!resizer || !previewPanel) {
        console.log('[DEBUG] initPreviewResizer: resizer or previewPanel not found', { resizer, previewPanel });
        return;
    }
    console.log('[DEBUG] initPreviewResizer: initialized successfully');
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

function showAboutPanel() {
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
        <p class="about-email" style="margin-top: 4px; font-size: 13px; color: var(--text-muted);">myx28@qq.com</p>
        <p class="about-tech" style="margin-top: 4px;">${window.t('about.opensource')}</p>
    `;

    document.getElementById('about-panel-content').innerHTML = aboutContent;
    document.getElementById('about-panel').classList.add('active');
}

function hideAboutPanel() {
    document.getElementById('about-panel').classList.remove('active');
}

window.setTheme = setTheme;
window.setFontSize = applyFontSize;

var FONT_SCALE_MAP = { small: 1, medium: 1.15, large: 1.3 };

function setFontSize(size) {
    var scale = FONT_SCALE_MAP[size] || 1;
    document.documentElement.style.setProperty('--font-scale', scale);
    document.querySelectorAll('input[name="font-size"]').forEach(function(radio) {
        radio.checked = radio.value === size;
    });
}

function applyFontSize(size) {
    setFontSize(size);
    localStorage.setItem('noteai_font_size', size);
    if (window.SettingsModule && window.SettingsModule.saveFontSize) {
        window.SettingsModule.saveFontSize(size);
    }
}

function restoreFontSize() {
    var saved = localStorage.getItem('noteai_font_size') || 'small';
    setFontSize(saved);
}

function normalizeFontFamily(value) {
    return FONT_FAMILY_MAP[value] ? value : 'system';
}

function applyContentFonts(sidebarFont, previewFont) {
    var sidebar = normalizeFontFamily(sidebarFont);
    var preview = normalizeFontFamily(previewFont);
    document.documentElement.style.setProperty('--sidebar-font-family', FONT_FAMILY_MAP[sidebar]);
    document.documentElement.style.setProperty('--preview-font-family', FONT_FAMILY_MAP[preview]);
    document.querySelectorAll('select[name="sidebar-font-family"]').forEach(function(select) {
        select.value = sidebar;
    });
    document.querySelectorAll('select[name="preview-font-family"]').forEach(function(select) {
        select.value = preview;
    });
}

function setSidebarFontFamily(value) {
    var font = normalizeFontFamily(value);
    var preview = localStorage.getItem(PREVIEW_FONT_KEY) || 'system';
    localStorage.setItem(SIDEBAR_FONT_KEY, font);
    applyContentFonts(font, preview);
    if (window.SettingsModule && window.SettingsModule.saveFontFamily) {
        window.SettingsModule.saveFontFamily('sidebar_font_family', font);
    }
}

function setPreviewFontFamily(value) {
    var font = normalizeFontFamily(value);
    var sidebar = localStorage.getItem(SIDEBAR_FONT_KEY) || 'system';
    localStorage.setItem(PREVIEW_FONT_KEY, font);
    applyContentFonts(sidebar, font);
    if (window.SettingsModule && window.SettingsModule.saveFontFamily) {
        window.SettingsModule.saveFontFamily('preview_font_family', font);
    }
}

function restoreContentFonts() {
    applyContentFonts(
        localStorage.getItem(SIDEBAR_FONT_KEY) || 'system',
        localStorage.getItem(PREVIEW_FONT_KEY) || 'system'
    );
}

window.setSidebarFontFamily = setSidebarFontFamily;
window.setPreviewFontFamily = setPreviewFontFamily;

window.ThemeModule = {
    toggleTheme,
    setTheme,
    applySystemTheme,
    initSystemThemeListener,
    applyTheme,
    syncThemeRadioInputs,
    persistThemeLocal,
    applyThemeBootstrap,
    setFontSize: applyFontSize,
    restoreFontSize,
    applyContentFonts,
    restoreContentFonts,
    setSidebarFontFamily,
    setPreviewFontFamily,
    restoreSidebarWidth,
    initResizer,
    initPreviewResizer,
    showAboutPanel,
    hideAboutPanel
};

})();
