document.addEventListener('DOMContentLoaded', async function() {
    console.log('[App] DOM Content Loaded');
    
    initMarked();
    
    initSystemThemeListener();
    
    const savedTheme = localStorage.getItem('noteai_theme') || 'system';
    applyTheme(savedTheme);
    
    initResizer();
    initPreviewResizer();
    initWindowDrag();
    
    initTabSwitching();
    
    updateStatus('正在加载...');
    
    try {
        await checkWorkspaceStatus();
        
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
        
        if (window.DownloaderModule && window.DownloaderModule.loadSavedConfig) {
            window.DownloaderModule.loadSavedConfig();
        }
        
        if (window.ConverterModule && window.ConverterModule.loadSavedConvConfig) {
            window.ConverterModule.loadSavedConvConfig();
        }
        
        updateStatus('就绪');
    } catch (e) {
        console.error('[App] Initialization error:', e);
        updateStatus('初始化完成');
    }
    
    const tabInputs = document.querySelectorAll('input[name="theme"], input[name="theme-popup"]');
    tabInputs.forEach(radio => {
        radio.addEventListener('change', (e) => {
            setTheme(e.target.value);
        });
    });
    
    const webAiToggle = document.getElementById('web-ai-toggle');
    if (webAiToggle) {
        webAiToggle.addEventListener('change', () => {
            if (window.TreeModule && window.TreeModule.updateWebAIStatus) {
                window.TreeModule.updateWebAIStatus();
            }
        });
    }
    
    const convAiToggle = document.getElementById('conv-ai-toggle');
    if (convAiToggle) {
        convAiToggle.addEventListener('change', () => {
            if (window.TreeModule && window.TreeModule.updateConvAIStatus) {
                window.TreeModule.updateConvAIStatus();
            }
        });
    }
    
    const topicList = document.getElementById('topic-list');
    if (topicList) {
        topicList.addEventListener('input', () => {
            if (window.IntegratorModule) {
                window.IntegratorModule.topicsReady = true;
                window.IntegratorModule.updateIntegrateBtnState();
            }
        });
    }
    
    console.log('[App] Initialization complete');
});

function initMarked() {
    if (window.EditorModule && window.EditorModule.initMarked) {
        window.EditorModule.initMarked();
    }
}

function initSystemThemeListener() {
    if (window.ThemeModule && window.ThemeModule.initSystemThemeListener) {
        window.ThemeModule.initSystemThemeListener();
    }
}

function applyTheme(theme) {
    if (window.ThemeModule && window.ThemeModule.applyTheme) {
        window.ThemeModule.applyTheme(theme);
    }
}

function setTheme(theme) {
    if (window.ThemeModule && window.ThemeModule.setTheme) {
        window.ThemeModule.setTheme(theme);
    }
}

function initResizer() {
    if (window.ThemeModule && window.ThemeModule.initResizer) {
        window.ThemeModule.initResizer();
    }
}

function initPreviewResizer() {
    if (window.ThemeModule && window.ThemeModule.initPreviewResizer) {
        window.ThemeModule.initPreviewResizer();
    }
}

function initWindowDrag() {
    if (window.EditorModule && window.EditorModule.initWindowDrag) {
        window.EditorModule.initWindowDrag();
    }
}

function initTabSwitching() {
    if (window.TabsModule && window.TabsModule.initTabs) {
        window.TabsModule.initTabs();
    }
}

async function checkWorkspaceStatus() {
    if (window.WorkspaceModule && window.WorkspaceModule.checkWorkspaceStatus) {
        await window.WorkspaceModule.checkWorkspaceStatus();
    }
}

function updateStatus(text) {
    if (window.WorkspaceModule && window.WorkspaceModule.updateStatus) {
        window.WorkspaceModule.updateStatus(text);
    }
}

window.App = {
    initMarked,
    initSystemThemeListener,
    applyTheme,
    setTheme,
    initResizer,
    initPreviewResizer,
    initWindowDrag,
    initTabSwitching,
    checkWorkspaceStatus,
    updateStatus
};
