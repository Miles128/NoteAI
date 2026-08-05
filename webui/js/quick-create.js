(function() { 'use strict';

var _topicOptions = [];

function _overlay() {
    return document.getElementById('quick-create-overlay');
}

function _fillTopicSelects() {
    var parentSel = document.getElementById('qc-topic-parent');
    if (!parentSel) return;
    var prev = parentSel.value;
    parentSel.innerHTML = '<option value="">' + window.t('quickCreate.uncategorized') + '</option>';
    _topicOptions.forEach(function(t) {
        var opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t;
        parentSel.appendChild(opt);
    });
    if (prev) parentSel.value = prev;
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

function _close() {
    var el = _overlay();
    if (el) el.style.display = 'none';
}

function _open() {
    var el = _overlay();
    if (!el) return;
    el.style.display = 'flex';
    _loadTopics().then(function() {
        var nameInput = document.getElementById('qc-topic-name');
        if (nameInput) nameInput.focus();
    });
}

function _selectTab(tab) {
    document.querySelectorAll('#quick-create-overlay [data-qc-tab]').forEach(function(button) {
        button.classList.toggle('active', button.dataset.qcTab === tab);
    });
    document.querySelectorAll('#quick-create-overlay [data-qc-pane]').forEach(function(pane) {
        pane.hidden = pane.dataset.qcPane !== tab;
    });
}

function _submitTopic() {
    var nameEl = document.getElementById('qc-topic-name');
    var parentEl = document.getElementById('qc-topic-parent');
    var name = (nameEl && nameEl.value || '').trim();
    var parent = (parentEl && parentEl.value || '').trim();
    if (!name) {
        window.updateStatus(window.t('quickCreate.enterTopicName'));
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
            window.updateStatus(res.message || window.t('quickCreate.topicCreated'));
            if (typeof window.refreshWorkspaceViewsAfterChange === 'function') {
                window.refreshWorkspaceViewsAfterChange();
            }
        } else {
            window.updateStatus(window.t('quickCreate.createFailed', { message: (res && res.message) || window.t('common.unknownError') }));
        }
    }).catch(function(err) {
        if (btn) btn.disabled = false;
        window.updateStatus(window.t('quickCreate.createFailed', { message: err.message || err }));
    });
}

function initQuickCreate() {
    var overlay = _overlay();
    if (!overlay || overlay.dataset.qcBound) return;
    overlay.dataset.qcBound = '1';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) _close();
    });

    var topicSubmit = document.getElementById('qc-topic-submit');
    if (topicSubmit) topicSubmit.addEventListener('click', _submitTopic);

    var topicName = document.getElementById('qc-topic-name');
    if (topicName) {
        topicName.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); _submitTopic(); }
        });
    }
    overlay.addEventListener('click', function(e) {
        var tab = e.target.closest('[data-qc-tab]');
        if (tab) { _selectTab(tab.dataset.qcTab); return; }
        var template = e.target.closest('[data-note-template]');
        if (template && window.NoteDraftModule) {
            _close();
            window.NoteDraftModule.createNoteInContext(template.dataset.noteTemplate);
        }
    });
}

window.QuickCreateModule = {
    open: _open,
    close: _close,
    init: initQuickCreate
};

window.openQuickCreate = function(tab) {
    if (tab === 'note') {
        initQuickCreate();
        _selectTab('note');
        _open();
        return;
    }
    initQuickCreate();
    _selectTab('topic');
    _open();
};

window.onAddTopicFromFileTree = function() {
    window.openQuickCreate('topic');
};

window.onAddNoteFromFileTree = function() {
    if (window.NoteDraftModule && window.NoteDraftModule.createNoteInContext) {
        window.NoteDraftModule.createNoteInContext();
    } else if (window.createNoteFromNoteList) {
        window.createNoteFromNoteList();
    }
};

})();
