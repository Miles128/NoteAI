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

    if (window.api) {
        window.api.save_theme_preference(html.getAttribute('data-theme') || 'system');
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

    document.querySelectorAll('input[name="theme"], input[name="theme-popup"]').forEach(radio => {
        radio.checked = radio.value === theme;
    });

    if (window.api) {
        window.api.save_theme_preference(theme);
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
        html.removeAttribute('data-theme');
    }

    if (window.EditorModule && window.EditorModule.updateEditorTheme) {
        window.EditorModule.updateEditorTheme();
    }
}

function initSystemThemeListener() {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        const currentTheme = localStorage.getItem('noteai_theme') || 'system';
        if (currentTheme === 'system') {
            applySystemTheme();
        }
    });
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
    if (!resizer || !sidebar) {
        console.log('[DEBUG] initResizer: resizer or sidebar not found', { resizer, sidebar });
        return;
    }
    console.log('[DEBUG] initResizer: initialized successfully');
    let isResizing = false;

    restoreSidebarWidth();

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const newWidth = e.clientX;
        if (newWidth >= 180 && newWidth <= 600) {
            sidebar.style.width = newWidth + 'px';
        }
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        resizer.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        localStorage.setItem('sidebar-width', sidebar.offsetWidth);
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
        <p class="about-version">版本 1.0.0</p>
        <p class="about-desc">AI 驱动的 Markdown 笔记知识库管理工具</p>
        <div class="about-features">
            <h3>核心功能</h3>
            <ul>
                <li>Markdown 笔记管理与编辑</li>
                <li>AI 智能主题分析与归类</li>
                <li>AI 主题综述自动撰写</li>
                <li>标签管理与自动匹配</li>
                <li>双向链接发现与可视化</li>
                <li>网络文章批量下载与转换</li>
                <li>多格式文件导入与整合</li>
                <li>AI 改写与格式化</li>
            </ul>
        </div>
        <div class="about-features">
            <h3>技术架构</h3>
            <ul>
                <li>前端：Tauri v2 + HTML / CSS / JS</li>
                <li>后端：Python sidecar</li>
                <li>编辑器：Tiptap</li>
                <li>大模型：LangChain + ChatOpenAI</li>
            </ul>
        </div>
        <p class="about-author" style="margin-top: 20px; font-size: 15px; color: var(--text);">作者：四海</p>
        <p class="about-tech" style="margin-top: 4px;">开源项目 · GitHub: Miles128/NoteAI</p>
    `;

    document.getElementById('about-panel-content').innerHTML = aboutContent;
    document.getElementById('about-panel').classList.add('active');
}

function hideAboutPanel() {
    document.getElementById('about-panel').classList.remove('active');
}

window.ThemeModule = {
    toggleTheme,
    setTheme,
    applySystemTheme,
    initSystemThemeListener,
    applyTheme,
    restoreSidebarWidth,
    initResizer,
    initPreviewResizer,
    showAboutPanel,
    hideAboutPanel
};
