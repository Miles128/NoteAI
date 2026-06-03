(function() { 'use strict';

var _topicOptions = [];

function _overlay() {
    return document.getElementById('quick-create-overlay');
}

function _fillTopicSelects() {
    var parentSel = document.getElementById('qc-topic-parent');
    var noteSel = document.getElementById('qc-note-topic');
    [parentSel, noteSel].forEach(function(sel) {
        if (!sel) return;
        var prev = sel.value;
        sel.innerHTML = '<option value="">' + window.t('quickCreate.uncategorized') + '</option>';
        _topicOptions.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t;
            opt.textContent = t;
            sel.appendChild(opt);
        });
        if (prev) sel.value = prev;
    });
}

function _flattenTopics(nodes, prefix) {
    var out = [];
    (nodes || []).forEach(function(n) {
        var name = n.name || n.label || '';
        if (!name) return;
        var label = prefix ? prefix + ' > ' + name : name;
        out.push(label);
        if (n.children && n.children.length) {
            out = out.concat(_flattenTopics(n.children, label));
        }
    });
    return out;
}

function _loadTopics() {
    if (!window.api || !window.api.getTopicTree) return Promise.resolve();
    return window.api.getTopicTree().then(function(res) {
        _topicOptions = [];
        if (res && res.topics) {
            _topicOptions = _flattenTopics(res.topics, '');
        }
        _topicOptions.sort();
        _fillTopicSelects();
    }).catch(function() {});
}

function _switchTab(tab) {
    document.querySelectorAll('.qc-tab').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.qcTab === tab);
    });
    document.querySelectorAll('.qc-pane').forEach(function(pane) {
        pane.hidden = pane.dataset.qcPane !== tab;
    });
}

function _close() {
    var el = _overlay();
    if (el) el.style.display = 'none';
}

function _open(tab) {
    var el = _overlay();
    if (!el) return;
    el.style.display = 'flex';
    _switchTab(tab || 'note');
    _loadTopics().then(function() {
        if (tab === 'topic') {
            var nameInput = document.getElementById('qc-topic-name');
            if (nameInput) nameInput.focus();
        } else {
            var titleInput = document.getElementById('qc-note-title');
            if (titleInput) titleInput.focus();
        }
    });
}

function _submitTopic() {
    var nameEl = document.getElementById('qc-topic-name');
    var parentEl = document.getElementById('qc-topic-parent');
    var name = (nameEl && nameEl.value || '').trim();
    var parent = (parentEl && parentEl.value || '').trim();
    if (!name) {
        if (typeof window.updateStatus === 'function') window.updateStatus(window.t('quickCreate.enterTopicName'));
        return;
    }
    if (!window.api || !window.api.createTopic) return;
    var btn = document.getElementById('qc-topic-submit');
    if (btn) btn.disabled = true;
    window.api.createTopic(name, parent).then(function(res) {
        if (btn) btn.disabled = false;
        if (res && res.success) {
            _close();
            if (nameEl) nameEl.value = '';
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree(true);
            }
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(res.message || window.t('quickCreate.topicCreated'));
            }
            if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
                window.refreshWorkspaceViewsAfterChange();
            }
        } else if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('quickCreate.createFailed', { message: (res && res.message) || window.t('common.unknownError') }));
        }
    }).catch(function(err) {
        if (btn) btn.disabled = false;
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('quickCreate.createFailed', { message: err.message || err }));
        }
    });
}

function _submitNote() {
    var titleEl = document.getElementById('qc-note-title');
    var topicEl = document.getElementById('qc-note-topic');
    var title = (titleEl && titleEl.value || '').trim();
    var topic = (topicEl && topicEl.value || '').trim();
    if (!title) {
        if (typeof window.updateStatus === 'function') window.updateStatus(window.t('quickCreate.enterNoteTitle'));
        return;
    }
    if (!window.api || !window.api.createNote) return;
    var btn = document.getElementById('qc-note-submit');
    if (btn) btn.disabled = true;
    window.api.createNote(title, topic).then(function(res) {
        if (btn) btn.disabled = false;
        if (res && res.success) {
            _close();
            if (titleEl) titleEl.value = '';
            if (window.TreeModule && window.TreeModule.loadFileTree) {
                window.TreeModule.loadFileTree(true);
            }
            if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
                window.refreshWorkspaceViewsAfterChange();
            }
            if (typeof showPreview === 'function') {
                showPreview({ path: res.path, name: title });
            }
            if (typeof window.updateStatus === 'function') {
                window.updateStatus(res.message || window.t('quickCreate.noteCreated'));
            }
        } else if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('quickCreate.createFailed', { message: (res && res.message) || window.t('common.unknownError') }));
        }
    }).catch(function(err) {
        if (btn) btn.disabled = false;
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('quickCreate.createFailed', { message: err.message || err }));
        }
    });
}

function initQuickCreate() {
    var overlay = _overlay();
    if (!overlay || overlay.dataset.qcBound) return;
    overlay.dataset.qcBound = '1';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) _close();
    });

    document.querySelectorAll('.qc-tab').forEach(function(btn) {
        btn.addEventListener('click', function() {
            _switchTab(btn.dataset.qcTab);
        });
    });

    var topicSubmit = document.getElementById('qc-topic-submit');
    if (topicSubmit) topicSubmit.addEventListener('click', _submitTopic);
    var noteSubmit = document.getElementById('qc-note-submit');
    if (noteSubmit) noteSubmit.addEventListener('click', _submitNote);

    var topicName = document.getElementById('qc-topic-name');
    if (topicName) {
        topicName.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); _submitTopic(); }
        });
    }
    var noteTitle = document.getElementById('qc-note-title');
    if (noteTitle) {
        noteTitle.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); _submitNote(); }
        });
    }
}

window.QuickCreateModule = {
    open: _open,
    close: _close,
    init: initQuickCreate
};

window.openQuickCreate = function(tab) {
    initQuickCreate();
    _open(tab || 'note');
};

window.onAddTopicFromFileTree = function() {
    window.openQuickCreate('topic');
};

window.onAddNoteFromFileTree = function() {
    window.openQuickCreate('note');
};

})();
