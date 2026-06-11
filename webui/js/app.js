(function() { 'use strict';

document.addEventListener('DOMContentLoaded', async function() {
    initMarked();

    // 主题已由 main.mjs 中 applyThemeBootstrap（服务端偏好 + localStorage）应用，此处不再覆盖

    if (window.ThemeModule && window.ThemeModule.restoreFontSize) {
        window.ThemeModule.restoreFontSize();
    }

    initResizer();
    initPreviewResizer();
    initWindowDrag();

    initTabSwitching();

    initCustomTooltip();

    if (window.TiptapEditorModule && window.TiptapEditorModule.preloadModules) {
        await window.TiptapEditorModule.preloadModules();
    }

    updateStatus(window.t('app.loading'));

    try {
        await checkWorkspaceStatus();

        if (window.TreeModule && window.TreeModule.loadFileTree) {
            await window.TreeModule.loadFileTree();
        }

        // Default: show knowledge graph (full right panel, no splits)
        var ca = document.getElementById('content-area');
        var gp = document.getElementById('graph-panel');
        var cp = document.getElementById('content-panel');
        if (ca) ca.style.display = 'none';
        if (cp) cp.style.display = 'flex';
        if (gp) gp.style.display = 'flex';
        window.updateHomeStats();
        if (window.Graph3Tier && window.Graph3Tier.load) {
            window.Graph3Tier.load();
        }

        if (window.DownloaderModule && window.DownloaderModule.loadSavedConfig) {
            window.DownloaderModule.loadSavedConfig();
        }

        if (window.ConverterModule && window.ConverterModule.loadSavedConvConfig) {
            window.ConverterModule.loadSavedConvConfig();
        }

        if (typeof window.runPostWorkspaceSetup === 'function') {
            /* ingest deferred until schema wizard completes, if needed */
        }

            setTimeout(function() {
                if (window.api && window.api.mergeDuplicateTopics) {
                    window.api.mergeDuplicateTopics().then(function(result) {
                        if (result && result.success && result.merged_topics > 0) {
                            console.log('[App] 合并重复主题: ' + result.merged_topics + ' 个, 去重文件: ' + result.deduplicated_files + ' 个');
                        }
                    }).catch(function(e) { console.warn('[App] merge_duplicate_topics failed:', e); });
                }
            }, 8000);

        updateStatus(window.t('app.ready'));
    } catch (e) {
        console.error('[App] Initialization error:', e);
        updateStatus(window.t('app.initDone'));
    }

    if (window.EventListeners) {
        window.EventListeners.initWorkspaceFileWatcher();
        window.EventListeners.initSidecarErrorListener();
        window.EventListeners.initRagEventListener();
    }

    if (window.AssistantModule && window.AssistantModule.init) {
        window.AssistantModule.init();
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

var _fileImportUnlisten = null;

async function importFiles() {
    try {
        var result = await window.api.importFilesToWorkspace();
        if (!result || result.cancelled) return;

        if (result && result.success) {
            updateStatus(window.t('app.importing', { count: result.file_count || 0 }));

            if (typeof window.getTauriEventAPI === 'function') {
                var eventAPI = getTauriEventAPI();
                if (eventAPI) {
                    if (_fileImportUnlisten) {
                        _fileImportUnlisten();
                    }
                    _fileImportUnlisten = await eventAPI.listen('python-event', function(event) {
                        var data = event.payload;
                        if (!data) return;

                        if (data.type === 'progress' && data.element_id === 'import-progress') {
                            updateStatus(data.message || window.t('app.importProgress'));
                        } else if (data.type === 'file_import_complete') {
                            var d = data.data || {};
                            var msg = d.failed > 0 ? window.t('app.importDoneWithFailed', { imported: d.imported || 0, failed: d.failed }) : window.t('app.importDone', { imported: d.imported || 0 })
                            updateStatus(msg);
                            if (window.TreeModule && window.TreeModule.loadFileTree) {
                                window.TreeModule.loadFileTree();
                            }
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        } else if (data.type === 'file_import_error') {
                            updateStatus(window.t('app.importFailed', { message: data.error || window.t('common.unknownError') }));
                            if (_fileImportUnlisten) {
                                _fileImportUnlisten();
                                _fileImportUnlisten = null;
                            }
                        }
                    });
                }
            }
        } else {
            updateStatus(window.t('app.importFailed', { message: result?.message || window.t('common.unknownError') }));
        }
    } catch (e) {
        console.error('[App] Import error:', e);
        updateStatus(window.t('app.importFailedGeneric'));
    }
}

async function runPostWorkspaceSetup() {
    if (window.api && window.api.needsSchemaSetup) {
        try {
            var st = await window.api.needsSchemaSetup();
            if (st && st.needs_setup) return;
        } catch (e) {
            console.warn('[App] needs_schema_setup check:', e);
        }
    }
    if (window.IngestModule && window.IngestModule.startIngest) {
        window.IngestModule.startIngest('incremental').then(function() {
            if (window.EventListeners && window.EventListeners.markInitialIngestDone) {
                window.EventListeners.markInitialIngestDone();
            }
        }).catch(function(e) {
            console.warn('[App] start_ingest failed:', e);
        });
    } else if (window.api && window.api.autoConvertPending) {
        window.api.autoConvertPending().then(function() {
            if (window.EventListeners && window.EventListeners.markInitialIngestDone) {
                window.EventListeners.markInitialIngestDone();
            }
        }).catch(function(e) { console.warn('[App] auto_convert_pending failed:', e); });
    }
}

window.runPostWorkspaceSetup = runPostWorkspaceSetup;

var _tooltipTimer = null;

function initCustomTooltip() {
    var tip = document.getElementById('custom-tooltip');
    if (!tip) return;

    document.addEventListener('mouseover', function(e) {
        var el = e.target.closest('[title]');
        if (!el) return;
        var title = el.getAttribute('title');
        if (!title) return;

        clearTimeout(_tooltipTimer);
        _tooltipTimer = setTimeout(function() {
            tip.textContent = title;
            tip.classList.add('visible');

            var rect = el.getBoundingClientRect();
            var tipW = tip.offsetWidth;
            var tipH = tip.offsetHeight;
            var left = rect.left + rect.width / 2 - tipW / 2;
            var top = rect.bottom + 6;

            if (left < 4) left = 4;
            if (left + tipW > window.innerWidth - 4) left = window.innerWidth - tipW - 4;
            if (top + tipH > window.innerHeight - 4) top = rect.top - tipH - 6;

            tip.style.left = left + 'px';
            tip.style.top = top + 'px';
        }, 400);
    });

    document.addEventListener('mouseout', function(e) {
        var el = e.target.closest('[title]');
        if (!el) return;
        clearTimeout(_tooltipTimer);
        tip.classList.remove('visible');
    });

    document.addEventListener('mousedown', function() {
        clearTimeout(_tooltipTimer);
        tip.classList.remove('visible');
    });
}

window.importFiles = importFiles;

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
    updateStatus,
    initWorkspaceFileWatcher: function() {
        if (window.EventListeners) {
            window.EventListeners.initWorkspaceFileWatcher();
        }
    }
};

})();
