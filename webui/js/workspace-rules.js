(function() { 'use strict';

var _resolveOpen = null;

function $(id) {
    return document.getElementById(id);
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function readOptionsFromDom(prefix) {
    var depthEl = document.querySelector('input[name="' + prefix + '-depth"]:checked');
    var surveyLevelEl = document.querySelector('input[name="' + prefix + '-survey-level"]:checked');
    var autoSurveyEl = prefix === 'organize-rules-modal'
        ? $('organize-rules-modal-auto-survey')
        : $('settings-organize-rules-auto-survey');
    return {
        max_topic_depth: depthEl ? parseInt(depthEl.value, 10) : 3,
        auto_update_survey: autoSurveyEl ? autoSurveyEl.checked : true,
        survey_at_level: surveyLevelEl ? parseInt(surveyLevelEl.value, 10) : 2
    };
}

function applyOptionsToForm(data, prefix) {
    var depth = String(data.max_topic_depth || 3);
    document.querySelectorAll('input[name="' + prefix + '-depth"]').forEach(function(el) {
        el.checked = el.value === depth;
        var card = el.closest('.schema-option-card');
        if (card) card.classList.toggle('selected', el.checked);
    });
    var surveyLevel = String(data.survey_at_level || 2);
    document.querySelectorAll('input[name="' + prefix + '-survey-level"]').forEach(function(el) {
        el.checked = el.value === surveyLevel;
        var card = el.closest('.schema-option-card');
        if (card) card.classList.toggle('selected', el.checked);
    });
    var autoSurveyEl = prefix === 'organize-rules-modal'
        ? $('organize-rules-modal-auto-survey')
        : $('settings-organize-rules-auto-survey');
    if (autoSurveyEl) autoSurveyEl.checked = data.auto_update_survey !== false;
}

function renderTopics(topics, containerId) {
    var el = $(containerId);
    if (!el) return;
    if (!topics || !topics.length) {
        el.textContent = window.t('settings.organizeRulesTopicsEmpty');
        return;
    }
    el.innerHTML = topics.map(function(name) {
        return '<span class="schema-l1-tag">' + escapeHtml(name) + '</span>';
    }).join('');
}

function bindOptionCards(root) {
    var scope = root || document;
    scope.querySelectorAll('.schema-option-card').forEach(function(card) {
        if (card.dataset.bound) return;
        card.dataset.bound = '1';
        card.addEventListener('click', function(e) {
            if (e.target.tagName === 'INPUT') return;
            var input = card.querySelector('input');
            if (!input) return;
            if (input.type === 'radio') {
                input.checked = true;
                card.parentElement.querySelectorAll('.schema-option-card').forEach(function(c) {
                    var inp = c.querySelector('input');
                    c.classList.toggle('selected', inp && inp.checked);
                });
            } else {
                input.checked = !input.checked;
                card.classList.toggle('selected', input.checked);
            }
        });
    });
}

function showStatus(msg, isError) {
    var el = $('settings-organize-rules-status');
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    el.style.color = isError ? '#e53e3e' : '';
    if (!isError) {
        setTimeout(function() { el.style.display = 'none'; }, 3000);
    }
}

async function fetchWorkspaceRules() {
    if (!window.api || !window.api.getWorkspaceRules) return null;
    return window.api.getWorkspaceRules();
}

async function loadOrganizeRules() {
    try {
        var result = await fetchWorkspaceRules();
        if (!result || !result.success) return;
        applyOptionsToForm(result, 'organize-rules');
        renderTopics(result.l1_topics, 'settings-organize-rules-topics');
    } catch (e) {
        console.error('[OrganizeRules] load:', e);
    }
}

async function saveOrganizeRules(fromModal) {
    var opts = readOptionsFromDom(fromModal ? 'organize-rules-modal' : 'organize-rules');
    if (!window.api || !window.api.saveWorkspaceRules) {
        throw new Error(window.t('organizeRules.saveUnavailable'));
    }
    var result = await window.api.saveWorkspaceRules(opts);
    if (!result || !result.success) {
        throw new Error((result && result.message) || window.t('organizeRules.saveFailed', { message: '' }));
    }
    return result;
}

async function finishModal() {
    try {
        await saveOrganizeRules(true);
        hideModal();
        await loadOrganizeRules();
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('organizeRules.saved'));
        }
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            await window.TreeModule.loadFileTree(true);
        }
        if (typeof window.runPostWorkspaceSetup === 'function') {
            window.runPostWorkspaceSetup();
        }
        if (_resolveOpen) _resolveOpen(true);
    } catch (e) {
        console.error('[OrganizeRules] save failed:', e);
        if (typeof window.updateStatus === 'function') {
            window.updateStatus(window.t('organizeRules.saveFailed', { message: e.message }));
        }
    }
}

function showModal() {
    var modal = $('organize-rules-modal');
    if (modal) modal.style.display = 'flex';
    fetchWorkspaceRules().then(function(result) {
        if (!result || !result.success) return;
        applyOptionsToForm(result, 'organize-rules-modal');
        renderTopics(result.l1_topics, 'organize-rules-modal-topics');
    });
}

function hideModal() {
    var modal = $('organize-rules-modal');
    if (modal) modal.style.display = 'none';
}

function openSetupModal() {
    return new Promise(function(resolve) {
        _resolveOpen = resolve;
        showModal();
    });
}

async function maybePromptSetup(flag) {
    if (!flag && window.api && window.api.needsWorkspaceRulesSetup) {
        try {
            var st = await window.api.needsWorkspaceRulesSetup();
            flag = st && st.needs_setup;
        } catch (e) {
            console.warn('[OrganizeRules] needs setup:', e);
            return false;
        }
    }
    if (!flag) return false;
    if (typeof window.showSettings === 'function') {
        window.showSettings();
        if (window.SettingsModule && window.SettingsModule.switchSettingsTab) {
            window.SettingsModule.switchSettingsTab('organize-rules');
        }
    }
    await openSetupModal();
    return true;
}

function initOrganizeRules() {
    bindOptionCards($('settings-organize-rules-card'));
    bindOptionCards($('organize-rules-modal'));

    var modalSaveBtn = $('organize-rules-modal-save');
    if (modalSaveBtn) {
        modalSaveBtn.addEventListener('click', function() {
            finishModal();
        });
    }

    var defaultBtn = $('organize-rules-use-default');
    if (defaultBtn) {
        defaultBtn.addEventListener('click', async function() {
            applyOptionsToForm({
                max_topic_depth: 3,
                auto_update_survey: true,
                survey_at_level: 2
            }, 'organize-rules-modal');
            try {
                await saveOrganizeRules(true);
                hideModal();
                await loadOrganizeRules();
                if (typeof window.runPostWorkspaceSetup === 'function') {
                    window.runPostWorkspaceSetup();
                }
                if (_resolveOpen) _resolveOpen(true);
            } catch (e) {
                console.error('[OrganizeRules] defaults:', e);
            }
        });
    }

    var setupBtn = $('settings-organize-rules-setup-btn');
    if (setupBtn && !setupBtn.dataset.bound) {
        setupBtn.dataset.bound = '1';
        setupBtn.addEventListener('click', function() {
            openSetupModal();
        });
    }

    var saveBtn = $('settings-organize-rules-save-btn');
    if (saveBtn && !saveBtn.dataset.bound) {
        saveBtn.dataset.bound = '1';
        saveBtn.addEventListener('click', async function() {
            try {
                await saveOrganizeRules(false);
                await loadOrganizeRules();
                showStatus(window.t('settings.organizeRulesSaved'));
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus(window.t('settings.organizeRulesSaved'));
                }
            } catch (e) {
                showStatus(e.message, true);
            }
        });
    }

    var modal = $('organize-rules-modal');
    if (modal && !modal.dataset.bound) {
        modal.dataset.bound = '1';
        modal.addEventListener('click', function(e) {
            if (e.target === modal) hideModal();
        });
    }
}

window.OrganizeRulesModule = {
    init: initOrganizeRules,
    open: openSetupModal,
    load: loadOrganizeRules,
    maybePromptSetup: maybePromptSetup
};

window.SchemaWizard = window.OrganizeRulesModule;

})();
