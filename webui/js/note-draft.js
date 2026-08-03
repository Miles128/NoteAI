(function() { 'use strict';

var STORAGE_KEY = 'noteai.noteDrafts.v1';
var _activeDraftId = null;
var _committing = false;

function _loadAll() {
    if (window.Storage && window.Storage.getItem) {
        return window.Storage.getItem(STORAGE_KEY, {}) || {};
    }
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {};
    } catch (_e) {
        return {};
    }
}

function _saveAll(map) {
    if (window.Storage && window.Storage.setItem) {
        window.Storage.setItem(STORAGE_KEY, map || {});
        return;
    }
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(map || {}));
    } catch (e) {
        console.warn('[NoteDraft] save failed:', e);
    }
}

function pathToTopic(folderPath) {
    if (!folderPath) return '';
    var norm = String(folderPath).replace(/\\/g, '/');
    if (norm.indexOf('Notes/') !== 0) return '';
    var rel = norm.slice('Notes/'.length);
    if (!rel || rel === '_未分类') return '';
    return rel.split('/').filter(Boolean).join(' > ');
}

function extractTitleFromMarkdown(content) {
    var text = String(content || '');
    var body = text;
    var fm = text.match(/^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n)?/);
    if (fm) {
        body = text.slice(fm[0].length);
    }
    var h1 = body.match(/^#\s+(.+?)\s*(?:\r?\n|$)/m);
    if (h1 && h1[1].trim()) {
        return h1[1].trim();
    }
    return '';
}

function _untitledLabel() {
    return (window.t && window.t('noteDraft.untitled')) || '未命名';
}

function _draftLabel(title) {
    var suffix = (window.t && window.t('noteDraft.labelSuffix')) || '(草稿)';
    var name = String(title || '').trim() || _untitledLabel();
    return name + ' ' + suffix;
}

function createDraft(topic, folderPath, template) {
    var cleanTopic = String(topic || '').trim();
    var cleanFolder = String(folderPath || '').trim();
    var id = 'draft_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    var fmLines = ['---'];
    if (cleanTopic) {
        fmLines.push('topic: ' + cleanTopic);
    }
    fmLines.push('---');
    var bodies = {
        meeting: '# 会议记录\n\n## 目标\n\n## 讨论\n\n## 决策\n\n## 待办\n\n- [ ] ',
        research: '# 研究笔记\n\n## 问题\n\n## 资料与证据\n\n## 结论\n\n## 待验证\n\n',
        task: '# 待办\n\n- [ ] \n\n## 背景\n\n'
    };
    var content = fmLines.join('\n') + '\n\n' + (bodies[template] || '# \n\n');
    var draft = {
        id: id,
        title: '',
        topic: cleanTopic,
        topicFolderPath: cleanFolder,
        content: content,
        createdAt: Date.now(),
        updatedAt: Date.now()
    };
    var all = _loadAll();
    all[id] = draft;
    _saveAll(all);
    return draft;
}

function getDraft(id) {
    if (!id) return null;
    var all = _loadAll();
    return all[id] || null;
}

function updateDraft(id, patch) {
    if (!id) return null;
    var all = _loadAll();
    var draft = all[id];
    if (!draft) return null;
    if (patch && patch.content != null) {
        draft.content = patch.content;
        var extracted = extractTitleFromMarkdown(patch.content);
        draft.title = extracted;
    }
    if (patch && patch.title != null) {
        draft.title = patch.title;
    }
    if (patch && patch.topic != null) {
        draft.topic = patch.topic;
    }
    if (patch && patch.topicFolderPath != null) {
        draft.topicFolderPath = patch.topicFolderPath;
    }
    draft.updatedAt = Date.now();
    all[id] = draft;
    _saveAll(all);
    return draft;
}

function removeDraft(id) {
    if (!id) return;
    var all = _loadAll();
    if (!all[id]) return;
    delete all[id];
    _saveAll(all);
    if (_activeDraftId === id) {
        _activeDraftId = null;
    }
}

function setActiveDraft(id) {
    _activeDraftId = id || null;
    if (window.StatusbarModule && window.StatusbarModule.setDraftActionsVisible) {
        window.StatusbarModule.setDraftActionsVisible(!!id);
    } else if (window.StatusbarModule && window.StatusbarModule.setSaveButtonVisible) {
        window.StatusbarModule.setSaveButtonVisible(!!id);
    }
}

function clearActiveDraft() {
    setActiveDraft(null);
}

function isDraftActive() {
    return !!(_activeDraftId || (window.TiptapEditor && window.TiptapEditor.draftId));
}

function refreshDraftChrome(content) {
    var label = _draftLabel(extractTitleFromMarkdown(content));
    if (window.PreviewModule && window.PreviewModule.updateTitlebarFileName) {
        window.PreviewModule.updateTitlebarFileName(label, true);
    }
    if (window.StatusbarModule && window.StatusbarModule.updateFromContent) {
        window.StatusbarModule.updateFromContent(content, null, label);
    }
}

function isDraftEffectivelyEmpty(content) {
    var text = String(content || '');
    var body = text;
    var fm = text.match(/^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n)?/);
    if (fm) {
        body = text.slice(fm[0].length);
    }
    body = body.replace(/^#\s*\r?\n?/, '');
    return body.trim() === '';
}

async function openDraft(draft) {
    if (!draft || !draft.id) return false;

    setActiveDraft(draft.id);

    var previewPanel = document.getElementById('preview-panel');
    if (previewPanel) {
        previewPanel.classList.add('active');
        previewPanel.style.display = '';
    }

    if (window.PreviewModule && window.PreviewModule.showPreviewView) {
        window.PreviewModule.showPreviewView();
    }

    refreshDraftChrome(draft.content);

    if (!window.TiptapEditorModule || !window.TiptapEditorModule.openMarkdownInEditor) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('noteDraft.editorUnavailable'));
        }
        return false;
    }

    var ok = await window.TiptapEditorModule.openMarkdownInEditor(draft.content, null, {
        draftId: draft.id,
        draftTitle: draft.title || '',
        draftTopic: draft.topic || ''
    });

    if (ok && window.TiptapEditor && window.TiptapEditor.focus) {
        window.requestAnimationFrame(function() {
            window.TiptapEditor.focus();
        });
    }

    if (!ok && typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('noteDraft.editorUnavailable'));
    }
    return !!ok;
}

async function createNoteInContext(template) {
    var info = window.NoteListModule && window.NoteListModule.getCurrentTopicInfo
        ? window.NoteListModule.getCurrentTopicInfo()
        : null;

    if (!info || !info.folderPath) {
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('noteDraft.selectFolderFirst'));
        }
        return false;
    }

    var draft = createDraft(info.topic, info.folderPath, template || 'blank');
    var ok = await openDraft(draft);
    if (ok && typeof window.updateStatus === 'function') {
        window.updateStatus(window.t('noteDraft.openedInFolder', { folder: info.folderName || info.folderPath }));
    }
    return ok;
}

async function commitCurrentDraft() {
    if (_committing) return { success: false, message: 'busy' };

    var editor = window.TiptapEditor;
    if (!editor || !editor.draftId) {
        return { success: false, message: (window.t && window.t('noteDraft.noActiveDraft')) || '没有可保存的草稿' };
    }
    if (!window.api || !window.api.createNoteFromDraft) {
        return { success: false, message: (window.t && window.t('noteDraft.apiUnavailable')) || '保存接口不可用' };
    }

    _committing = true;
    if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
        window.StatusbarModule.updateSaveStatus('saving', window.t('editor.saving'));
    }

    try {
        var body = editor.getContent();
        var fullContent = editor.getFullContent(body || '');
        var title = extractTitleFromMarkdown(fullContent) || _untitledLabel();
        var topic = String(editor.draftTopic || '').trim();
        var draftId = editor.draftId;

        var createRes = await window.api.createNoteFromDraft(title, topic, fullContent);
        if (!createRes || !createRes.success || !createRes.path) {
            var createMsg = (createRes && createRes.message) || window.t('common.unknownError');
            if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
                window.StatusbarModule.updateSaveStatus('error', window.t('editor.saveFailed'));
            }
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(window.t('quickCreate.createFailed', { message: createMsg }));
            }
            return { success: false, message: createMsg };
        }

        removeDraft(draftId);
        editor.draftId = null;
        editor.draftTitle = '';
        editor.draftTopic = '';
        editor.filePath = createRes.path;
        editor.originalContent = fullContent;
        editor.userEdited = false;
        clearActiveDraft();

        if (window.PreviewModule && window.PreviewModule.currentPreviewData) {
            window.PreviewModule.currentPreviewData.path = createRes.path;
            window.PreviewModule.currentPreviewData.name = title;
            window.PreviewModule.currentPreviewData.content = fullContent;
        }
        if (window.PreviewModule && window.PreviewModule.updateTitlebarFileName) {
            window.PreviewModule.updateTitlebarFileName(title, true);
        }
        if (window.StatusbarModule && window.StatusbarModule.onFileSelected) {
            window.StatusbarModule.onFileSelected(createRes.path);
        }
        if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
            window.StatusbarModule.updateSaveStatus('saved', window.t('editor.saveSaved'));
        }
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree(true);
        }
        if (window.NoteListModule && window.NoteListModule.refresh) {
            window.NoteListModule.refresh();
        }
        if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
            window.refreshWorkspaceViewsAfterChange();
        }
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('noteDraft.savedToWorkspace', { path: createRes.path }));
        }

        return { success: true, path: createRes.path };
    } catch (err) {
        var msg = (err && err.message) ? err.message : String(err || window.t('common.unknownError'));
        if (window.StatusbarModule && window.StatusbarModule.updateSaveStatus) {
            window.StatusbarModule.updateSaveStatus('error', window.t('editor.saveFailed'));
        }
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('quickCreate.createFailed', { message: msg }));
        }
        return { success: false, message: msg };
    } finally {
        _committing = false;
    }
}

async function discardCurrentDraft() {
    var editor = window.TiptapEditor;
    var draftId = _activeDraftId || (editor && editor.draftId);
    if (!draftId) {
        return { success: false, message: (window.t && window.t('noteDraft.noActiveDraft')) || '没有可保存的草稿' };
    }

    var fullContent = '';
    if (editor && editor.draftId === draftId && editor.getContent && editor.getFullContent) {
        fullContent = editor.getFullContent(editor.getContent() || '');
    } else {
        var draft = getDraft(draftId);
        fullContent = draft && draft.content ? draft.content : '';
    }

    if (!isDraftEffectivelyEmpty(fullContent) && typeof window.confirm === 'function') {
        var ok = window.confirm((window.t && window.t('noteDraft.discardConfirm')) || '确定作废当前草稿吗？');
        if (!ok) return { success: false, cancelled: true };
    }

    removeDraft(draftId);
    if (editor && editor.draftId === draftId) {
        editor.draftId = null;
        editor.draftTitle = '';
        editor.draftTopic = '';
    }
    clearActiveDraft();

    if (window.TiptapEditorModule && window.TiptapEditorModule.hideEditorUI) {
        await window.TiptapEditorModule.hideEditorUI();
    }
    if (window.PreviewModule && window.PreviewModule.closePreview) {
        window.PreviewModule.closePreview();
    }
    if (window.StatusbarModule && window.StatusbarModule.clearStats) {
        window.StatusbarModule.clearStats();
    }
    if (typeof window.updateStatus === 'function') {
        window.updateStatus((window.t && window.t('noteDraft.discarded')) || '草稿已作废');
    }
    return { success: true };
}

function bindShortcuts() {
    if (document.body.dataset.noteDraftBound) return;
    document.body.dataset.noteDraftBound = '1';

    document.addEventListener('keydown', function(e) {
        if (!(e.metaKey || e.ctrlKey) || e.key !== 's') return;
        if (!window.TiptapEditor || !window.TiptapEditor.draftId) return;
        e.preventDefault();
        commitCurrentDraft();
    });
}

window.NoteDraftModule = {
    pathToTopic: pathToTopic,
    extractTitleFromMarkdown: extractTitleFromMarkdown,
    createDraft: createDraft,
    getDraft: getDraft,
    updateDraft: updateDraft,
    removeDraft: removeDraft,
    setActiveDraft: setActiveDraft,
    clearActiveDraft: clearActiveDraft,
    isDraftActive: isDraftActive,
    refreshDraftChrome: refreshDraftChrome,
    openDraft: openDraft,
    createNoteInContext: createNoteInContext,
    commitCurrentDraft: commitCurrentDraft,
    discardCurrentDraft: discardCurrentDraft,
    bindShortcuts: bindShortcuts
};

bindShortcuts();

})();
