(function() { 'use strict';

var _visible = false;
var _category = 'objects';
var _objectKind = 'entities';
var _items: any[] = [];
var _selectedIndex = -1;
var _overview: any = {};
var _promptVersionStatus: any = null;
var _loadSeq = 0;
var _detailSeq = 0;
var _searchTimer: any = null;
var _compileTimer: any = null;
var _activeDetail: any = null;
var _activeDetailKind: any = null;
var _lastBrief = '';
var _pendingTargetId: any = null;
var _suppressAutoSelect = false;
var _degradedHidden = 0;
var _recentAdded: any = null;
var _intensity = 'standard';
var _enabledCategories = ['objects', 'claims', 'quality', 'conflicts', 'links', 'brief'];
var _workbenchEnabled = true;
var _verifyAgents: any[] = [];

function esc(value: any): string {
    return window.escapeHtml ? window.escapeHtml(String(value == null ? '' : value)) : String(value == null ? '' : value);
}
function t(key: string, vars?: any): string { return window.t ? window.t(key, vars) : key; }
function currentTab() { return _category === 'objects' ? _objectKind : _category; }

function isEnabled() {
    var ui = window.uiConfig;
    return ui ? ui.semantic_workbench_enabled !== false : _workbenchEnabled;
}

function toggle() { _visible ? hide() : show(_category); }

function show(category: any) {
    if (!isEnabled()) return;
    if (category) _category = category;
    _visible = true;
    var notePanel = document.getElementById('note-list-panel');
    if (notePanel) {
        notePanel.classList.remove('collapsed');
        notePanel.style.width = '';
        notePanel.style.minWidth = '';
    }
    var normalList = document.getElementById('note-list-normal');
    var semanticList = document.getElementById('semantic-list-pane');
    if (normalList) normalList.hidden = true;
    if (semanticList) semanticList.hidden = false;
    var contentPanel = document.getElementById('content-panel');
    if (contentPanel) contentPanel.style.display = 'flex';
    ['home-dashboard', 'graph-home-view', 'graph-panel', 'content-area', 'preview-panel', 'pending-view',
     'topic-pending-panel', 'topic-files-panel', 'ai-suggestion-panel'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    var detail = document.getElementById('semantic-workbench-detail');
    if (detail) detail.hidden = false;
    document.querySelectorAll('#semantic-categories [data-category]').forEach(function(button) {
        button.classList.toggle('active', (button as HTMLElement).dataset.category === _category);
    });
    var switcher = document.getElementById('semantic-object-switch');
    if (switcher) switcher.style.display = _category === 'objects' ? 'flex' : 'none';
    var graphButton = document.getElementById('titlebar-graph-btn');
    if (graphButton) graphButton.classList.remove('active');
    if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();
    configureStatusFilter();
    loadOverview();
    loadVerifyAgents();
    loadList();
}

function deactivate() {
    if (!_visible) return;
    _visible = false;
    clearTimeout(_compileTimer);
    var normalList = document.getElementById('note-list-normal');
    var semanticList = document.getElementById('semantic-list-pane');
    var detail = document.getElementById('semantic-workbench-detail');
    if (normalList) normalList.hidden = false;
    if (semanticList) semanticList.hidden = true;
    if (detail) detail.hidden = true;
    document.querySelectorAll('#semantic-categories [data-category]').forEach(function(button) {
        button.classList.remove('active');
    });
    var contentPanel = document.getElementById('content-panel');
    var preview = document.getElementById('preview-panel');
    if (window.AppState && window.AppState.selectedFilePath) {
        if (contentPanel) contentPanel.style.display = 'none';
        if (preview) preview.style.display = 'flex';
    } else {
        var home = document.getElementById('home-dashboard');
        if (contentPanel) contentPanel.style.display = 'flex';
        if (preview) preview.style.display = 'none';
        if (home) home.style.display = '';
    }
}

function hide() {
    deactivate();
    if (window.AppState && window.AppState.selectedFilePath) {
        var contentPanel = document.getElementById('content-panel');
        var preview = document.getElementById('preview-panel');
        if (contentPanel) contentPanel.style.display = 'none';
        if (preview) preview.style.display = 'flex';
    } else {
        var home = document.getElementById('home-dashboard');
        if (home) home.style.display = '';
    }
}

function setCategory(category: any) {
    // Clicking the already-active category dismisses the workbench, giving
    // users an explicit way to return to the standard note view.
    if (_visible && _category === category) {
        hide();
        return;
    }
    _category = category;
    _selectedIndex = -1;
    if (!_visible) {
        show(category);
        return;
    }
    document.querySelectorAll('#semantic-categories [data-category]').forEach(function(button) {
        button.classList.toggle('active', (button as HTMLElement).dataset.category === category);
    });
    var switcher = document.getElementById('semantic-object-switch');
    if (switcher) switcher.style.display = category === 'objects' ? 'flex' : 'none';
    configureStatusFilter();
    var search = document.getElementById('semantic-search');
    if (search) (search as HTMLInputElement).value = '';
    loadList();
}

function setObjectKind(kind: any) {
    _objectKind = kind;
    _selectedIndex = -1;
    document.querySelectorAll('#semantic-object-switch [data-object-kind]').forEach(function(button) {
        button.classList.toggle('active', (button as HTMLElement).dataset.objectKind === kind);
    });
    loadList();
}

function configureStatusFilter() {
    var status = document.getElementById('semantic-status-filter');
    if (!status) return;
    status.hidden = _category !== 'claims' && _category !== 'quality' && _category !== 'conflicts' && _category !== 'links';
    var scan = document.getElementById('semantic-scan-conflicts');
    if (scan) scan.hidden = _category !== 'conflicts';
    if (_category === 'claims') {
        status.innerHTML = '<option value="active">' + esc(t('semantic.status.active')) + '</option><option value="deleted">' + esc(t('semantic.status.deleted')) + '</option><option value="all">' + esc(t('semantic.status.all')) + '</option>';
    } else if (_category === 'conflicts') {
        status.innerHTML = '<option value="pending">' + esc(t('semantic.status.pending')) + '</option><option value="reviewed">' + esc(t('semantic.status.reviewed')) + '</option><option value="all">' + esc(t('semantic.status.all')) + '</option>';
    } else if (_category === 'quality') {
        status.innerHTML = '<option value="pending">' + esc(t('semantic.status.pending')) + '</option><option value="reviewed">' + esc(t('semantic.status.reviewed')) + '</option><option value="all">' + esc(t('semantic.status.all')) + '</option>';
    } else if (_category === 'links') {
        status.innerHTML = '<option value="all">' + esc(t('semantic.status.all')) + '</option><option value="pending">' + esc(t('semantic.status.pending')) + '</option><option value="confirmed">' + esc(t('semantic.status.confirmed')) + '</option>';
    }
}

function requestOptions() {
    var search = document.getElementById('semantic-search');
    var status = document.getElementById('semantic-status-filter');
    return {
        tab: currentTab(),
        query: search ? (search as HTMLInputElement).value.trim() : '',
        status: status && !status.hidden ? (status as HTMLSelectElement).value : undefined,
        intensity: _intensity,
        limit: 100,
        offset: 0
    };
}

function categoryTitle() {
    if (_category === 'objects') return t('semantic.categories.objects') + ' · ' + t('semantic.tabs.' + _objectKind);
    return t('semantic.categories.' + _category);
}

function loadList() {
    if (!_visible || !window.api || !window.api.getSemanticWorkbench) return;
    if (_category === 'brief') return loadBrief();
    const list = document.getElementById('semantic-workbench-list');
    if (!list) return;
    var seq = ++_loadSeq;
    list.innerHTML = '<div class="semantic-loading">' + esc(t('common.loading')) + '</div>';
    var title = document.getElementById('semantic-list-title');
    if (title) title.textContent = categoryTitle();
    window.api.getSemanticWorkbench(requestOptions()).then(function(result) {
        if (seq !== _loadSeq) return;
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        _items = result.items || [];
        _degradedHidden = result.degraded_hidden || 0;
        _selectedIndex = -1;
        var count = document.getElementById('semantic-list-count');
        if (count) count.textContent = t('semantic.itemCount', { count: result.total || 0 });
        renderList();
        if (_suppressAutoSelect) {
            // openObject 等待目标详情加载：不高亮/选中第一项，改为高亮列表中的目标项
            _suppressAutoSelect = false;
            var targetId = _pendingTargetId;
            _pendingTargetId = null;
            if (_items.length) {
                for (var i = 0; i < _items.length; i++) {
                    if (String(_items[i].id) === String(targetId)) {
                        _selectedIndex = i;
                        renderList();
                        break;
                    }
                }
            }
        } else if (_items.length) {
            selectItem(0);
        } else {
            renderEmptyDetail();
        }
    }).catch(function(error) {
        if (seq !== _loadSeq) return;
        _suppressAutoSelect = false;
        _pendingTargetId = null;
        list.innerHTML = '<div class="semantic-error">' + esc(t('semantic.loadFailed', { error: String(error.message || error) })) + '</div>';
        renderEmptyDetail(String(error.message || error));
    });
}

function briefDays() {
    var select = document.getElementById('semantic-brief-days');
    var value = select ? Number((select as HTMLSelectElement).value) : 7;
    return value >= 1 && value <= 90 ? value : 7;
}

function loadBrief() {
    const list = document.getElementById('semantic-workbench-list');
    if (!list || !window.api || !window.api.getTopicBrief) return;
    var seq = ++_loadSeq;
    _items = [];
    _selectedIndex = -1;
    var title = document.getElementById('semantic-list-title');
    if (title) title.textContent = categoryTitle();
    var count = document.getElementById('semantic-list-count');
    if (count) count.textContent = '';
    list.innerHTML = '<div class="semantic-loading">' + esc(t('common.loading')) + '</div>';
    renderEmptyDetail();
    window.api.getTopicBrief({ days: briefDays() }).then(function(result) {
        if (seq !== _loadSeq) return;
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        renderBriefControls(result.topics || [], result.days || briefDays());
    }).catch(function(error) {
        if (seq !== _loadSeq) return;
        list.innerHTML = '<div class="semantic-error">' + esc(t('semantic.loadFailed', { error: String(error.message || error) })) + '</div>';
    });
}

function renderBriefControls(topics: any, days: any) {
    var list = document.getElementById('semantic-workbench-list');
    if (!list) return;
    var options = topics.length
        ? '<option value="">' + esc(t('semantic.brief.chooseTopic')) + '</option>' + topics.map(function(topic: any) { return '<option value="' + esc(topic) + '">' + esc(topic) + '</option>'; }).join('')
        : '<option value="">' + esc(t('semantic.brief.noTopics', { days: days })) + '</option>';
    list.innerHTML = '<div class="semantic-brief-controls">' +
        '<label>' + esc(t('semantic.brief.days')) + '<select id="semantic-brief-days">' +
        [7, 14, 30, 90].map(function(d) { return '<option value="' + d + '"' + (d === days ? ' selected' : '') + '>' + esc(t('semantic.brief.daysShort', { days: d })) + '</option>'; }).join('') +
        '</select></label>' +
        '<label>' + esc(t('semantic.brief.topic')) + '<select id="semantic-brief-topic">' + options + '</select></label>' +
        '<button type="button" class="primary" data-brief-generate' + (topics.length ? '' : ' disabled') + '>' + esc(t('semantic.brief.generate')) + '</button>' +
        '</div>';
    var daysSelect = list.querySelector('#semantic-brief-days');
    if (daysSelect) daysSelect.addEventListener('change', loadBrief);
}

function generateBrief() {
    if (!window.api || !window.api.getTopicBrief) return;
    var topic = document.getElementById('semantic-brief-topic');
    var topicValue = topic ? (topic as HTMLSelectElement).value.trim() : '';
    if (!topicValue) {
        if (window.ToastModule) window.ToastModule.error(t('semantic.brief.noTopicSelected'));
        return;
    }
    var button = document.querySelector('[data-brief-generate]');
    if (button) (button as HTMLButtonElement).disabled = true;
    var detail = document.getElementById('semantic-workbench-detail');
    if (detail) detail.innerHTML = '<div class="semantic-loading">' + esc(t('semantic.brief.generating')) + '</div>';
    window.api.getTopicBrief({ topic: topicValue, days: briefDays() }).then(function(result) {
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        renderBrief(result);
    }).catch(function(error) {
        var detailPane = document.getElementById('semantic-workbench-detail');
        if (detailPane) detailPane.innerHTML = '<div class="semantic-error">' + esc(String(error.message || error)) + '</div>';
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
    }).finally(function() {
        var btn = document.querySelector('[data-brief-generate]');
        if (btn) (btn as HTMLButtonElement).disabled = false;
    });
}

function renderBrief(result: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    _lastBrief = result.brief || '';
    var body = _lastBrief;
    var html = window.marked && window.marked.parse ? window.marked.parse(body) : '<pre>' + esc(body) + '</pre>';
    if (typeof DOMPurify !== 'undefined') html = DOMPurify.sanitize(html);
    var fallback = result.fallback ? '<div class="semantic-brief-fallback">' + esc(t('semantic.brief.fallback')) + '</div>' : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.brief')) + '</p><h2>' + esc(result.topic || '') + '</h2><p class="semantic-detail-description">' + esc(t('semantic.brief.windowLabel', { days: result.days || 7 })) + '</p><div class="semantic-brief-body">' + html + '</div>' + fallback + '<div class="semantic-actions"><button data-brief-copy>' + esc(t('semantic.brief.copy')) + '</button></div></div>';
}

function renderList() {
    var list = document.getElementById('semantic-workbench-list');
    if (!list) return;
    if (!_items.length) {
        list.innerHTML = '<div class="semantic-empty">' + esc(t(_category === 'conflicts' ? 'semantic.emptyConflicts' : 'semantic.empty')) + '</div>';
        return;
    }
    var html = '';
    if (_category === 'quality' && (window.api as any).resolveCrossKindMerges) {
        html += '<button type="button" class="semantic-list-action" data-quality-resolve-cross-kind>' + esc(t('semantic.resolveAllCrossKind')) + '</button>';
    }
    if (_category === 'quality' && (window.api as any).enqueueCrossKindSemanticMerges) {
        html += '<button type="button" class="semantic-list-action" data-quality-enqueue-all-cross-kind>' + esc(t('semantic.enqueueAllCrossKind')) + '</button>';
    }
    html += _items.map(function(item, index) {
        var title = item.canonical_name || item.statement || item.reason || linkTitle(item);
        var description = item.description || item.scope || conflictSummary(item) || item.reason || '';
        var meta = listMeta(item);
        var cls = 'semantic-list-item' + (index === _selectedIndex ? ' active' : '');
        if (_category === 'claims' && needsResearch(item)) cls += ' needs-verify';
        return '<button type="button" class="' + cls + '" data-semantic-index="' + index + '"><strong>' + esc(title) + '</strong>' + (description ? '<p>' + esc(description) + '</p>' : '') + '<span class="semantic-list-item-meta">' + meta + '</span></button>';
    }).join('');
    list.innerHTML = html;
    if (_degradedHidden > 0 && _category === 'objects') {
        list.insertAdjacentHTML('beforeend', '<div class="semantic-degraded-hint">' + esc(t('semantic.degradedHint', { count: _degradedHidden })) + '</div>');
    }
}

function listMeta(item: any) {
    if (_category === 'objects') return '<span>' + esc(item.entity_type || t('semantic.tabs.' + _objectKind)) + '</span><span>' + esc(t('semantic.mentions', { count: item.mention_count || 0 })) + '</span>';
    if (_category === 'quality') return '<span>' + esc(t('semantic.qualityRules.' + item.rule)) + '</span><span>' + esc(t('semantic.status.' + (item.status || 'pending'))) + '</span>';
    if (_category === 'claims') return (item.verification ? '<span class="semantic-verdict semantic-verdict-' + esc(item.verification.verdict) + '">' + esc(t('semantic.verdicts.' + item.verification.verdict)) + '</span>' : '') + '<span>' + esc(t('semantic.status.' + (item.status || 'active'))) + '</span><span>' + esc(t('semantic.claimTypes.' + (item.claim_type || 'conclusion'))) + '</span><span>' + esc(t('semantic.evidenceCount', { count: item.evidence_count || 0 })) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span>';
    return '<span>' + esc(t('semantic.status.' + (item.status || 'confirmed'))) + '</span>' + (item.has_reverse ? '<span>↔</span>' : '');
}

function linkTitle(item: any) { return shortPath(item.from) + ' → ' + shortPath(item.to); }
function shortPath(path: any) { var parts = String(path || '').split('/'); return parts[parts.length - 1] || path || ''; }
function conflictSummary(item: any) { var p = item.payload || {}; return p.claim_a || p.left_statement || p.statement_a || ''; }

function needsResearch(item: any) {
    if (!item.verification) return true;
    if (item.verification.verdict === 'unclear') return true;
    return false;
}

function selectItem(index: any) {
    if (!_items[index]) return;
    _selectedIndex = index;
    renderList();
    var item = _items[index];
    if (_category === 'objects' || _category === 'claims') loadDetail(item);
    else if (_category === 'quality') renderQualityDetail(item);
    else renderLocalDetail(item);
    if (_category === 'claims' && needsResearch(item) && !_verifiedInSession[item.id]) {
        if (_autoVerifyTimer) {
            clearTimeout(_autoVerifyTimer);
            _autoVerifyTimer = null;
        }
        _autoVerifyClaimId = item.id;
        _autoVerifyTimer = setTimeout(function() {
            _autoVerifyTimer = null;
            if (_autoVerifyClaimId !== item.id) return;
            _autoVerifyClaimId = null;
            if (!_activeDetail || _activeDetail.id !== item.id || _verifyRunning) return;
            _verifiedInSession[item.id] = true;
            verifyClaim(null, '__llm__');
        }, 350);
    } else if (!_verifyRunning) {
        resetVerifyStream();
    }
}

function loadDetail(item: any) {
    const detail = document.getElementById('semantic-workbench-detail');
    if (!detail || !window.api.getSemanticDetail) return;
    var kind = _category === 'claims' ? 'claim' : (_objectKind === 'entities' ? 'entity' : 'concept');
    var seq = ++_detailSeq;
    detail.innerHTML = '<div class="semantic-loading">' + esc(t('common.loading')) + '</div>';
    window.api.getSemanticDetail(kind, item.id).then(function(result) {
        if (seq !== _detailSeq) return;
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        renderObjectDetail(kind, result.item || {});
    }).catch(function(error) {
        if (seq !== _detailSeq) return;
        detail.innerHTML = '<div class="semantic-error">' + esc(String(error.message || error)) + '</div>';
    });
}

function openObject(kind: any, id: any) {
    if (kind !== 'entity' && kind !== 'concept') return;
    if (!isEnabled()) return;
    _category = 'objects';
    _objectKind = kind === 'entity' ? 'entities' : 'concepts';
    _pendingTargetId = id;
    _suppressAutoSelect = true;
    show('objects');
    loadDetail({ id: id });
}

function renderObjectDetail(kind: any, item: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    var title = item.canonical_name || item.statement || '';
    var kicker = kind === 'claim' ? t('semantic.categories.claims') : t('semantic.tabs.' + (kind === 'entity' ? 'entities' : 'concepts'));
    var description = item.description || (item.scope ? t('semantic.scope', { scope: item.scope }) : '');
    var sources = item.sources || [];
    _activeDetail = item;
    _activeDetailKind = kind;
    var sourceHtml = sources.map(function(source: any) { return renderSource(source, kind); }).join('');
    var typeLabel = kind === 'claim' ? t('semantic.claimTypes.' + (item.claim_type || 'conclusion')) : (item.entity_type || '');
    var status = kind === 'claim' ? '<span>' + esc(t('semantic.status.' + (item.status || 'active'))) + '</span>' : '';
    var pageControls = (kind === 'entity' || kind === 'concept') ? '<div class="semantic-actions"><button data-preview-object-page data-object-kind="' + kind + '" data-object-id="' + esc(item.id) + '">' + esc(t('semantic.previewTopicPage')) + '</button><button data-publish-object-page data-object-kind="' + kind + '" data-object-id="' + esc(item.id) + '">' + esc(t('semantic.publishTopicPage')) + '</button></div>' : '';
    var controls = kind === 'claim' ? renderClaimControls(item) : (kind === 'entity' ? renderEntityAliasControls(item) + pageControls : pageControls);
    var audit = renderAudit(item.audit || []);
    var related = (item.related || []).map(function(relation: any) {
        return '<button class="semantic-related-object" data-open-semantic-kind="' + esc(relation.object_kind) + '" data-open-semantic-id="' + esc(relation.object_id) + '">' + esc(relation.relation_type) + ' · ' + esc(relation.object_name) + '</button>';
    }).join('');
    var relatedSection = (kind === 'entity' || kind === 'concept') ? '<section class="semantic-detail-section"><h3>' + esc(t('semantic.related')) + '</h3>' + (related || '<div class="semantic-empty">' + esc(t('semantic.empty')) + '</div>') + '</section>' : '';
    var verificationSection = kind === 'claim' ? renderVerifications(item) : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(kicker) + '</p><h2>' + esc(title) + '</h2>' + (description ? '<p class="semantic-detail-description">' + esc(description) + '</p>' : '') + '<div class="semantic-detail-meta">' + status + '<span>' + esc(typeLabel) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span><span>' + esc(t('semantic.sources', { count: sources.length })) + '</span></div>' + controls + verificationSection + relatedSection + '<section class="semantic-detail-section"><h3>' + esc(t(kind === 'claim' ? 'semantic.evidenceTitle' : 'semantic.sourceLocations')) + '</h3>' + (sourceHtml || '<div class="semantic-empty">' + esc(t('semantic.empty')) + '</div>') + '</section>' + audit + '</div>';
    if (kind === 'claim' && _verifyStreamText) ensureVerifyStream();
}

function renderClaimControls(item: any) {
    var deleted = item.status === 'deleted';
    var statusButton = deleted
        ? '<button class="primary" data-claim-status="active">' + esc(t('semantic.restoreClaim')) + '</button>'
        : '<button class="danger" data-claim-status="deleted">' + esc(t('semantic.deleteClaim')) + '</button>';
    var topic = ((item.sources || [])[0] || {}).topic || '';
    var pageActions = topic ? '<button data-preview-topic-page="' + esc(topic) + '">' + esc(t('semantic.previewTopicPage')) + '</button><button data-publish-topic-page="' + esc(topic) + '">' + esc(t('semantic.publishTopicPage')) + '</button>' : '';
    var verifyControl = !deleted
        ? '<select data-verify-agent><option value="__llm__">' + esc(t('semantic.verifyViaLlm')) + '</option>' + _verifyAgents.map(function(agent) { return '<option value="' + esc(agent.id) + '">' + esc(agent.name || agent.id) + '</option>'; }).join('') + '</select><button data-verify-claim>' + esc(t('semantic.verifyClaim')) + '</button>'
        : '';
    return '<div class="semantic-actions">' + verifyControl + '<button data-edit-claim>' + esc(t('semantic.editClaim')) + '</button>' + statusButton + pageActions + '</div>' +
        '<form class="semantic-claim-editor" hidden><label>' + esc(t('semantic.claimStatement')) + '<textarea name="statement" required>' + esc(item.statement || '') + '</textarea></label><label>' + esc(t('semantic.claimScope')) + '<input name="scope" value="' + esc(item.scope || '') + '"></label><label>' + esc(t('semantic.claimType')) + '<select name="claim_type"><option value="conclusion"' + (item.claim_type === 'conclusion' ? ' selected' : '') + '>' + esc(t('semantic.claimTypes.conclusion')) + '</option><option value="hypothesis"' + (item.claim_type === 'hypothesis' ? ' selected' : '') + '>' + esc(t('semantic.claimTypes.hypothesis')) + '</option></select></label><div class="semantic-actions"><button type="submit" class="primary">' + esc(t('common.save')) + '</button><button type="button" data-cancel-claim-edit>' + esc(t('common.cancel')) + '</button></div></form>';
}

function loadVerifyAgents() {
    if (!window.api.listCliAgents) return;
    window.api.listCliAgents().then(function(result) {
        if (!result || !result.success) return;
        _verifyAgents = (result.agents || []).filter(function(agent: any) { return agent.installed; });
        if (_activeDetail && _activeDetailKind === 'claim') renderObjectDetail(_activeDetailKind, _activeDetail);
    }).catch(function() {});
}

var _verifyStreamUnlisten: any = null;
var _verifyStreamEl: any = null;
var _verifyStreamText: string = '';
var _verifyRunning: boolean = false;
var _verifiedInSession: any = {};
var _autoVerifyClaimId: any = null;
var _autoVerifyTimer: any = null;

function ensureVerifyStream() {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return null;
    var panel = detail.querySelector('.semantic-verify-stream');
    if (!panel) {
        panel = document.createElement('section');
        panel.className = 'semantic-verify-stream';
        panel.innerHTML = '<h3>' + esc(t('semantic.verifyStreamTitle')) + '</h3><div class="semantic-verify-stream-body" aria-live="polite"></div>';
        detail.appendChild(panel);
    }
    _verifyStreamEl = panel;
    var body = panel.querySelector('.semantic-verify-stream-body');
    if (body) body.textContent = _verifyStreamText;
    panel.classList.add('active');
    panel.scrollTop = panel.scrollHeight;
    return panel;
}

function appendVerifyStream(text: any) {
    _verifyStreamText += text;
    if (_verifyStreamEl) {
        var body = _verifyStreamEl.querySelector('.semantic-verify-stream-body');
        if (body) body.textContent = _verifyStreamText;
        _verifyStreamEl.scrollTop = _verifyStreamEl.scrollHeight;
    }
}

function resetVerifyStream() {
    _verifyStreamText = '';
    _verifyStreamEl = null;
    var detail = document.getElementById('semantic-workbench-detail');
    var panel = detail ? detail.querySelector('.semantic-verify-stream') : null;
    if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
}

function initVerifyStreamListener() {
    if (_verifyStreamUnlisten) return;
    var eventAPI = typeof window.getTauriEventAPI === 'function' ? window.getTauriEventAPI() : null;
    if (!eventAPI || typeof eventAPI.listen !== 'function') return;
    eventAPI.listen('python-event', function(event: any) {
        var data = event.payload;
        if (!data || !data.type) return;
        if (data.type === 'cli_agent_output' && _verifyStreamEl) {
            appendVerifyStream(data.content || '');
        } else if (data.type === 'verify_llm_output' && _verifyStreamEl) {
            appendVerifyStream(data.content || '');
        }
    }).then(function(unlisten: any) { _verifyStreamUnlisten = unlisten; });
}

function verifyClaim(button: any, forceAgent?: any) {
    if (!_activeDetail || !window.api.verifySemanticClaim) return;
    if (_verifyRunning) return;
    var claimId = _activeDetail.id;
    var actions = button ? button.closest('.semantic-actions') : null;
    var select = actions ? actions.querySelector('[data-verify-agent]') : null;
    var agentId = forceAgent || (select ? select.value : '') || '__llm__';
    var method = 'cli';
    if (agentId === '__llm__') {
        agentId = 'api';
        method = 'llm';
    }
    var originalLabel = button ? button.textContent : '';
    var streamTitle = method === 'llm' ? t('semantic.verifyViaLlm') : agentId;
    _verifyRunning = true;
    if (button) {
        button.disabled = true;
        button.textContent = t('semantic.verifyRunning');
    }
    if (select) select.disabled = true;
    ensureVerifyStream();
    var statement = (_activeDetail.statement || '').replace(/\s+/g, ' ').slice(0, 48);
    appendVerifyStream('\n>>> ' + streamTitle + ' ' + t('semantic.verifyStart') + ' · ' + (statement || claimId) + '\n');
    window.api.verifySemanticClaim(claimId, agentId, method).then(function(result) {
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        appendVerifyStream('\n>>> ' + t('semantic.verifyDone') + '\n');
        if (window.ToastModule) window.ToastModule.success(t('semantic.verifyDone'));
        loadList();
        if (_activeDetail && _activeDetail.id === claimId) loadDetail(_activeDetail);
    }).catch(function(error) {
        appendVerifyStream('\n>>> ' + t('semantic.verifyFailed') + ': ' + String(error.message || error) + '\n');
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
    }).finally(function() {
        _verifyRunning = false;
        if (button) {
            button.disabled = false;
            button.textContent = originalLabel;
        }
        if (select) select.disabled = false;
        if (_verifyStreamText) ensureVerifyStream();
    });
}

function renderVerifications(item: any) {
    var records = item.verifications || [];
    var header = '<h3>' + esc(t('semantic.verificationTitle')) + '</h3>';
    if (!records.length) {
        return '<section class="semantic-detail-section">' + header + '<div class="semantic-empty">' + esc(t('semantic.verificationEmpty')) + '</div></section>';
    }
    var history = records.length > 1 ? '<span class="semantic-muted">' + esc(t('semantic.verificationHistory', { count: records.length })) + '</span>' : '';
    var cards = records.map(function(record: any) {
        var sources = (record.sources || []).map(function(source: any) {
            var safeHref = window.safeUrl ? window.safeUrl(source.url || '#') : '#';
            return '<li><a href="' + esc(safeHref) + '" target="_blank" rel="noopener">' + esc(source.title || source.url || '') + '</a></li>';
        }).join('');
        return '<article class="semantic-verification"><div class="semantic-verification-head"><span class="semantic-verdict semantic-verdict-' + esc(record.verdict) + '">' + esc(t('semantic.verdicts.' + record.verdict)) + '</span><span>' + Math.round((record.confidence || 0) * 100) + '%</span><span>' + esc(record.agent || record.method || '') + '</span><time>' + esc(record.created_at || '') + '</time></div>' + (record.summary ? '<p>' + esc(record.summary) + '</p>' : '') + (sources ? '<ul class="semantic-verification-sources">' + sources + '</ul>' : '') + '</article>';
    }).join('');
    return '<section class="semantic-detail-section">' + header + history + cards + '</section>';
}

function renderEntityAliasControls(item: any) {
    var aliases = (item.aliases || []).map(function(alias: any) { return '<span class="semantic-alias-chip">' + esc(alias) + '</span>'; }).join('');
    return '<section class="semantic-detail-section"><h3>' + esc(t('semantic.aliases')) + '</h3><div class="semantic-aliases">' + (aliases || '<span class="semantic-muted">' + esc(t('semantic.noAliases')) + '</span>') + '</div><form class="semantic-alias-form"><input name="alias" required placeholder="' + esc(t('semantic.aliasPlaceholder')) + '"><button type="submit">' + esc(t('semantic.addAlias')) + '</button></form></section>';
}

function renderAudit(items: any) {
    if (!items.length) return '';
    return '<section class="semantic-detail-section semantic-audit"><h3>' + esc(t('semantic.auditTitle')) + '</h3>' + items.map(function(item: any) { return '<div><span>' + esc(t('semantic.auditActions.' + item.action)) + '</span><time>' + esc(item.created_at || '') + '</time></div>'; }).join('') + '</section>';
}

function renderSource(source: any, kind: any) {
    var heading = (source.heading_path || []).join(' › ');
    var label = (source.title || shortPath(source.path)) + (heading ? ' · ' + heading : '') + ' · L' + (source.start_line || 1);
    var evidenceAction = kind === 'claim' ? '<button class="semantic-evidence-action" data-evidence-id="' + esc(source.id) + '" data-evidence-status="' + (source.status === 'excluded' ? 'active' : 'excluded') + '">' + esc(t(source.status === 'excluded' ? 'semantic.restoreEvidence' : 'semantic.excludeEvidence')) + '</button>' : '';
    return '<article class="semantic-source-card' + (source.status === 'excluded' ? ' is-excluded' : '') + '"><div class="semantic-source-heading"><button class="semantic-source" data-open-path="' + esc(source.path) + '">' + esc(label) + '</button>' + evidenceAction + '</div><blockquote>' + esc(source.excerpt || '') + '</blockquote></article>';
}

function renderLocalDetail(item: any) {
    if (_category === 'links') return renderLinkDetail(item);
    renderConflictDetail(item);
}

function renderQualityDetail(item: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    _activeDetail = item;
    _activeDetailKind = 'quality';
    var candidates = (item.candidate_names || []).map(function(name: any, index: any) {
        var candidateId = (item.candidate_ids || [])[index] || '';
        return '<li>' + (candidateId ? '<button data-quality-merge-candidate="' + esc(candidateId) + '">' + esc(name) + '</button>' : esc(name)) + '</li>';
    }).join('');
    var action = item.status === 'pending'
        ? '<button class="primary" data-quality-id="' + esc(item.id) + '" data-quality-status="reviewed">' + esc(t('semantic.markReviewed')) + '</button>'
        : '<button data-quality-id="' + esc(item.id) + '" data-quality-status="pending">' + esc(t('semantic.restorePending')) + '</button>';
    var inbox = item.status === 'pending' ? '<button data-quality-enqueue="' + esc(item.id) + '">' + esc(t('semantic.addToInbox')) + '</button>' : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.quality')) + '</p><h2>' + esc(item.entity_name || '') + '</h2><div class="semantic-detail-meta"><span>' + esc(t('semantic.qualityRules.' + item.rule)) + '</span><span>' + esc(t('semantic.status.' + item.status)) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span></div><section class="semantic-detail-section"><h3>' + esc(t('semantic.qualityReason')) + '</h3><p>' + esc(item.reason || '') + '</p></section>' + (candidates ? '<section class="semantic-detail-section"><h3>' + esc(t('semantic.qualityCandidates')) + '</h3><ul>' + candidates + '</ul></section>' : '') + '<div class="semantic-actions"><button data-quality-open-entity="' + esc(item.entity_id) + '">' + esc(t('semantic.openEntity')) + '</button>' + inbox + action + '</div></div>';
}

function renderConflictDetail(item: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    var payload = item.payload || {};
    var left = payload.left_statement || payload.claim_a || payload.statement_a || '';
    var right = payload.right_statement || payload.claim_b || payload.statement_b || '';
    var action = item.status === 'pending' ? '<button class="primary" data-review-id="' + esc(item.id) + '" data-review-status="reviewed">' + esc(t('semantic.markReviewed')) + '</button>' : '<button data-review-id="' + esc(item.id) + '" data-review-status="pending">' + esc(t('semantic.restorePending')) + '</button>';
    (detail as HTMLElement).innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.conflicts')) + '</p><h2>' + esc(item.reason || t('semantic.conflictCandidate')) + '</h2><div class="semantic-detail-meta"><span>' + esc(t('semantic.status.' + item.status)) + '</span><span>' + esc(item.created_at || '') + '</span></div><section class="semantic-detail-section"><h3>' + esc(t('semantic.conflictingClaims')) + '</h3><div class="semantic-route"><span>' + esc(left || '—') + '</span><span>↔</span><span>' + esc(right || '—') + '</span></div></section><div class="semantic-actions">' + action + '</div></div>';
}

function renderLinkDetail(item: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    var actions = item.status === 'pending' ? '<div class="semantic-actions"><button class="primary" data-link-action="confirm" data-from="' + esc(item.from) + '" data-to="' + esc(item.to) + '">' + esc(t('semantic.confirm')) + '</button><button data-link-action="reject" data-from="' + esc(item.from) + '" data-to="' + esc(item.to) + '">' + esc(t('semantic.reject')) + '</button></div>' : '';
    (detail as HTMLElement).innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.links')) + '</p><h2>' + esc(t('semantic.linkRelation')) + '</h2><p class="semantic-detail-description">' + esc(item.reason || t('semantic.related')) + '</p><div class="semantic-detail-meta"><span>' + esc(t('semantic.status.' + item.status)) + '</span>' + (item.has_reverse ? '<span class="semantic-reverse">↔ ' + esc(t('semantic.bidirectional')) + '</span>' : '') + '</div><div class="semantic-route"><button class="semantic-link-endpoint" data-open-path="' + esc(item.from) + '">' + esc(item.from) + '</button><span>→</span><button class="semantic-link-endpoint" data-open-path="' + esc(item.to) + '">' + esc(item.to) + '</button></div>' + actions + '</div>';
}

function renderEmptyDetail(error?: any) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    if (error) {
        detail.innerHTML = '<div class="semantic-error">' + esc(error) + '</div>';
        return;
    }
    var keys = ['documents', 'blocks', 'concepts', 'entities', 'claims', 'evidence'];
    // 展示层用用户语言，原治理术语以 tooltip 次级标注保留（避免治理场景歧义）。
    var metricHints: Record<string, string> = { claims: 'Claim', evidence: 'Evidence' };
    var metrics = keys.map(function(key) {
        var hint = metricHints[key] ? ' title="' + metricHints[key] + '"' : '';
        return '<div class="semantic-metric"><strong>' + esc(_overview[key] || 0) + '</strong><span' + hint + '>' + esc(t('semantic.metrics.' + key)) + '</span></div>';
    }).join('');
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">Semantic IR</p><h2>' + esc(t('semantic.categoryEmptyTitle')) + '</h2><p class="semantic-detail-description">' + esc(t(_category === 'conflicts' ? 'semantic.emptyConflicts' : 'semantic.selectHint')) + '</p>' + narrativeSummaryHtml() + '<div class="semantic-metrics">' + metrics + '</div><section class="semantic-changes" id="semantic-changes"><h3>' + esc(t('semantic.changes.title')) + ' <span class="semantic-changes-window">' + esc(t('semantic.changes.window')) + '</span></h3><p class="semantic-detail-description">' + esc(t('semantic.changes.empty')) + '</p></section></div>';
    _recentAdded = null;
    loadChanges();
}

// 「你的知识库」叙事卡片：把概览指标转译为用户语言（PRD §10.10.1：仅陈述事实数量，无任何评分/健康度）。
// X=结论数、主题覆盖数来自 get_semantic_overview；Z=近 7 天新增来自 get_semantic_changes。
// 某数据缺失时优雅降级（省略对应短语）。
function narrativePhrases() {
    var overview = _overview || {};
    var phrases = [];
    if (typeof overview.claims === 'number') {
        phrases.push(t('semantic.narrative.conclusions', { count: overview.claims }));
    }
    var topics = overview.topics_with_changes;
    if (Array.isArray(topics)) topics = topics.length;
    if (typeof topics !== 'number' && typeof overview.topics === 'number') topics = overview.topics;
    if (typeof topics === 'number') {
        phrases.push(t('semantic.narrative.topics', { count: topics }));
    }
    if (typeof _recentAdded === 'number') {
        phrases.push(t('semantic.narrative.recent', { count: _recentAdded }));
    }
    return phrases;
}

function narrativeSummaryHtml() {
    var phrases = narrativePhrases();
    if (!phrases.length) return '';
    return '<section class="semantic-narrative-card" aria-label="' + esc(t('semantic.narrative.title')) + '"><h3 class="semantic-narrative-title" title="Claim / Evidence">' + esc(t('semantic.narrative.title')) + '</h3><p class="semantic-narrative-text">' + phrases.map(esc).join(' &middot; ') + '</p></section>';
}

function updateNarrativeText() {
    var text = document.querySelector('.semantic-narrative-text');
    if (!text) return;
    var phrases = narrativePhrases();
    if (phrases.length) text.innerHTML = phrases.map(esc).join(' &middot; ');
}

function loadChanges() {
    if (!window.api || !window.api.getSemanticChanges) return;
    window.api.getSemanticChanges({ days: 7, limit: 8 }).then(function(result) {
        if (!result || !result.success) throw new Error((result && result.message) || '');
        renderChanges(result);
    }).catch(function() {
        var box = document.getElementById('semantic-changes');
        if (box) {
            var paragraph = box.querySelector('p');
            if (paragraph) paragraph.textContent = t('semantic.changes.loadFailed');
        }
    });
}

function renderChanges(result: any) {
    var box = document.getElementById('semantic-changes');
    if (!box) return;
    var counts = result.counts || [];
    var items = result.items || [];
    var total = result.total || 0;
    var summary: any = {};
    counts.forEach(function(entry: any) {
        summary[entry.change_kind] = (summary[entry.change_kind] || 0) + entry.count;
    });
    _recentAdded = summary.added || 0;
    updateNarrativeText();
    var badgeOrder = ['added', 'updated', 'invalidated', 'removed'];
    var badges = badgeOrder.filter(function(kind: any) { return summary[kind]; }).map(function(kind: any) {
        return '<span class="semantic-change-badge semantic-change-' + kind + '">' + esc(t('semantic.changes.' + kind)) + ' ' + summary[kind] + '</span>';
    }).join('');
    var rows = items.map(function(item: any) {
        var objectLabel = t('semantic.changes.objects.' + item.object_kind) || item.object_kind;
        var source = item.source_path ? '<span class="semantic-change-source">' + esc(item.source_path) + '</span>' : '';
        return '<li class="semantic-change-row"><span class="semantic-change-badge semantic-change-' + esc(item.change_kind) + '">' + esc(t('semantic.changes.' + item.change_kind)) + '</span><span class="semantic-change-kind">' + esc(objectLabel) + '</span><span class="semantic-change-label" title="' + esc(item.label || '') + '">' + esc(item.label || '') + '</span>' + source + '</li>';
    }).join('');
    var body = items.length
        ? '<ul class="semantic-change-list">' + rows + '</ul><p class="semantic-changes-total">' + esc(t('semantic.changes.total', { total: total })) + '</p>'
        : '<p class="semantic-detail-description">' + esc(t('semantic.changes.empty')) + '</p>';
    box.innerHTML = '<h3>' + esc(t('semantic.changes.title')) + ' <span class="semantic-changes-window">' + esc(t('semantic.changes.window')) + '</span></h3>' + (badges ? '<div class="semantic-change-summary">' + badges + '</div>' : '') + body;
}

function loadOverview() {
    if (!window.api || !window.api.getSemanticWorkbench) return;
    window.api.getSemanticWorkbench({ tab: 'overview' }).then(function(result) {
        if (!result || !result.success) return;
        _overview = result.overview || {};
        _promptVersionStatus = result.prompt_version_status || null;
        renderCoverage(result.compile_job || null);
        if (_selectedIndex < 0 && !_suppressAutoSelect) renderEmptyDetail();
        if (result.compile_job && result.compile_job.status === 'running') scheduleCompilePoll();
    }).catch(function() {});
}

function renderCoverage(job: any) {
    var coverage = document.getElementById('semantic-coverage');
    var button = document.getElementById('semantic-compile-all');
    var progress = document.getElementById('semantic-compile-progress');
    var versionHint = document.getElementById('semantic-version-hint');
    var source = _overview.source_documents || 0;
    var compiled = _overview.documents || 0;
    var percent = source ? Math.min(100, Math.round(compiled * 100 / source)) : 0;
    if (coverage) {
        coverage.textContent = compiled + '/' + source;
        coverage.title = t('semantic.coverageLabel', { percent: percent, uncompiled: _overview.uncompiled_documents || 0 });
    }
    if (versionHint) {
        var pvs = _promptVersionStatus;
        if (pvs && pvs.prompt_version_stale) {
            versionHint.textContent = t('semantic.versionHint', { version: pvs.prompt_version_latest });
            versionHint.hidden = false;
            versionHint.title = t('semantic.versionHintTitle', { current: pvs.prompt_version, latest: pvs.prompt_version_latest });
        } else {
            versionHint.hidden = true;
        }
    }
    var running = job && job.status === 'running';
    if (button) { (button as HTMLButtonElement).disabled = !!running; button.textContent = t(running ? 'semantic.compiling' : 'semantic.compileAll'); }
    if (progress) {
        progress.hidden = !job;
        progress.textContent = job ? (job.message || '') : '';
    }
}

function startCompileAll() {
    if (!window.api || !window.api.startSemanticFullCompile) return;
    var button = document.getElementById('semantic-compile-all');
    if (button) (button as HTMLButtonElement).disabled = true;
    window.api.startSemanticFullCompile().then(function(result) {
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        renderCoverage(result.job || null);
        scheduleCompilePoll();
    }).catch(function(error) {
        if (button) (button as HTMLButtonElement).disabled = false;
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
    });
}

function scanConflicts(button: any) {
    if (!window.api || !window.api.scanSemanticConflicts) return;
    var original = button.textContent;
    button.disabled = true;
    window.api.scanSemanticConflicts().then(function(result) {
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        if (window.ToastModule) window.ToastModule.success(t('semantic.scanConflictsDone'));
        loadOverview();
        loadList();
    }).catch(function(error) {
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
    }).finally(function() {
        button.disabled = false;
        button.textContent = original;
    });
}

function scheduleCompilePoll() {
    clearTimeout(_compileTimer);
    if (!_visible) return;
    _compileTimer = setTimeout(function() {
        if (!window.api || !window.api.getSemanticCompileStatus) return;
        window.api.getSemanticCompileStatus().then(function(result) {
            var job = result && result.job;
            renderCoverage(job || null);
            loadOverview();
            if (job && job.status === 'running') scheduleCompilePoll();
            else loadList();
        }).catch(function() { scheduleCompilePoll(); });
    }, 1600);
}

function openSource(path: any) {
    if (!path) return;
    deactivate();
    if (window.TreeModule && window.TreeModule.selectFile) window.TreeModule.selectFile(path, shortPath(path));
    else if (typeof window.showPreview === 'function') window.showPreview({ path: path });
}

function onDetailClick(event: any) {
    var relatedObject = event.target.closest('[data-open-semantic-kind]');
    if (relatedObject) {
        openObject(relatedObject.dataset.openSemanticKind, relatedObject.dataset.openSemanticId);
        return;
    }
    var source = event.target.closest('[data-open-path]');
    if (source) return openSource(source.dataset.openPath);
    var edit = event.target.closest('[data-edit-claim]');
    if (edit) {
        var editor = document.querySelector('.semantic-claim-editor');
        if (editor) (editor as HTMLElement).hidden = false;
        return;
    }
    var cancelEdit = event.target.closest('[data-cancel-claim-edit]');
    if (cancelEdit) {
        var editForm = document.querySelector('.semantic-claim-editor');
        if (editForm) (editForm as HTMLElement).hidden = true;
        return;
    }
    var previewTopic = event.target.closest('[data-preview-topic-page]');
    if (previewTopic && window.api.getSemanticTopicWikiPage) {
        var previewButton = previewTopic;
        previewButton.disabled = true;
        window.api.getSemanticTopicWikiPage(previewButton.dataset.previewTopicPage).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            var detail = document.getElementById('semantic-workbench-detail');
            if (detail) detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.topicPagePreview')) + '</p><h2>' + esc(result.topic) + '</h2><pre class="semantic-topic-page-preview">' + esc(result.content || '') + '</pre></div>';
        }).catch(function(error) {
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        }).finally(function() { previewButton.disabled = false; });
        return;
    }
    var previewObject = event.target.closest('[data-preview-object-page]');
    if (previewObject && window.api.getSemanticObjectWikiPage) {
        window.api.getSemanticObjectWikiPage(previewObject.dataset.objectKind, previewObject.dataset.objectId).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            var detail = document.getElementById('semantic-workbench-detail');
            if (detail) detail.innerHTML = '<div class="semantic-detail-inner"><pre class="semantic-topic-page-preview">' + esc(result.content || '') + '</pre></div>';
        }).catch(function(error) { if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
        return;
    }
    var publishObject = event.target.closest('[data-publish-object-page]');
    if (publishObject && window.api.publishSemanticObjectWikiPage) {
        window.api.publishSemanticObjectWikiPage(publishObject.dataset.objectKind, publishObject.dataset.objectId).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            if (window.ToastModule) window.ToastModule.success(t('semantic.topicPagePublished'));
        }).catch(function(error) { if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
        return;
    }
    var publishTopic = event.target.closest('[data-publish-topic-page]');
    if (publishTopic && window.api.publishSemanticTopicWikiPage) {
        var publishButton = publishTopic;
        publishButton.disabled = true;
        window.api.publishSemanticTopicWikiPage(publishButton.dataset.publishTopicPage).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            if (window.ToastModule) window.ToastModule.success(t('semantic.topicPagePublished'));
        }).catch(function(error) {
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        }).finally(function() { publishButton.disabled = false; });
        return;
    }
    var verifyButton = event.target.closest('[data-verify-claim]');
    if (verifyButton) {
        verifyClaim(verifyButton);
        return;
    }
    var claimStatus = event.target.closest('[data-claim-status]');
    if (claimStatus && _activeDetail && window.api.setSemanticClaimStatus) {
        claimStatus.disabled = true;
        return window.api.setSemanticClaimStatus(_activeDetail.id, claimStatus.dataset.claimStatus).then(function(result) {
            if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
            loadList();
        }).catch(function(error) { claimStatus.disabled = false; if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
    }
    var evidence = event.target.closest('[data-evidence-id]');
    if (evidence && window.api.setSemanticEvidenceStatus) {
        evidence.disabled = true;
        return window.api.setSemanticEvidenceStatus(evidence.dataset.evidenceId, evidence.dataset.evidenceStatus).then(function(result) {
            if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
            loadDetail(_activeDetail);
            loadOverview();
        }).catch(function(error) { evidence.disabled = false; if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
    }
    var review = event.target.closest('[data-review-id]');
    if (review && window.api.reviewSemanticConflict) {
        review.disabled = true;
        window.api.reviewSemanticConflict(review.dataset.reviewId, review.dataset.reviewStatus).then(loadList).catch(function(error) {
            review.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var qualityEntity = event.target.closest('[data-quality-open-entity]');
    if (qualityEntity) {
        _category = 'objects';
        _objectKind = 'entities';
        show('objects');
        if ((window.api as any).getSemanticDetail) {
            loadDetail({ id: qualityEntity.dataset.qualityOpenEntity });
        }
        return;
    }
    var quality = event.target.closest('[data-quality-id]');
    if (quality && window.api.reviewSemanticEntityQuality) {
        quality.disabled = true;
        window.api.reviewSemanticEntityQuality(quality.dataset.qualityId, quality.dataset.qualityStatus).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            loadList();
        }).catch(function(error) {
            quality.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var enqueueQuality = event.target.closest('[data-quality-enqueue]');
    if (enqueueQuality && window.api.enqueueSemanticEntityQuality) {
        enqueueQuality.disabled = true;
        window.api.enqueueSemanticEntityQuality(enqueueQuality.dataset.qualityEnqueue).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            if (window.ToastModule) window.ToastModule.success(t('semantic.qualityAddedToInbox'));
        }).catch(function(error) {
            enqueueQuality.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var enqueueAllCrossKind = event.target.closest('[data-quality-enqueue-all-cross-kind]');
    if (enqueueAllCrossKind && window.api.enqueueCrossKindSemanticMerges) {
        enqueueAllCrossKind.disabled = true;
        window.api.enqueueCrossKindSemanticMerges().then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            if (window.ToastModule) window.ToastModule.success(t('semantic.enqueueAllCrossKindDone', { count: result.count || 0 }));
        }).catch(function(error) {
            enqueueAllCrossKind.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var resolveCrossKind = event.target.closest('[data-quality-resolve-cross-kind]');
    if (resolveCrossKind && window.api.resolveCrossKindMerges) {
        if (!window.confirm(t('semantic.resolveAllCrossKindConfirm'))) return;
        resolveCrossKind.disabled = true;
        window.api.resolveCrossKindMerges().then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            var stats = result.stats || {};
            if (window.ToastModule) window.ToastModule.success(t('semantic.resolveAllCrossKindDone', { total: result.total || 0, merged: (stats.merge_entity || 0) + (stats.merge_concept || 0), kept: stats.keep_both || 0, skipped: stats.skip || 0 }));
            loadList();
        }).catch(function(error) {
            resolveCrossKind.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var mergeCandidate = event.target.closest('[data-quality-merge-candidate]');
    if (mergeCandidate && _activeDetail && window.api.getSemanticEntityMergePreview) {
        mergeCandidate.disabled = true;
        window.api.getSemanticEntityMergePreview(_activeDetail.entity_id, mergeCandidate.dataset.qualityMergeCandidate).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            var source = result.source || {};
            var target = result.target || {};
            var impact = result.impact || {};
            var sourceImpact = impact[source.id] || {};
            var targetImpact = impact[target.id] || {};
            var detail = document.getElementById('semantic-workbench-detail');
            if (detail) detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.mergePreview')) + '</p><h2>' + esc(source.canonical_name || '') + ' → ' + esc(target.canonical_name || '') + '</h2><p class="semantic-detail-description">' + esc(result.message || '') + '</p><section class="semantic-detail-section"><h3>' + esc(t('semantic.mergeImpact')) + '</h3><div class="semantic-route"><span>' + esc(source.canonical_name || '') + ' · ' + esc(t('semantic.mergeImpactSummary', { mentions: sourceImpact.mentions || 0, aliases: (sourceImpact.aliases || []).length, relations: sourceImpact.relations || 0 })) + '</span><span>→</span><span>' + esc(target.canonical_name || '') + ' · ' + esc(t('semantic.mergeImpactSummary', { mentions: targetImpact.mentions || 0, aliases: (targetImpact.aliases || []).length, relations: targetImpact.relations || 0 })) + '</span></div></section><div class="semantic-actions"><button class="danger" data-confirm-entity-merge data-merge-source="' + esc(source.id) + '" data-merge-target="' + esc(target.id) + '">' + esc(t('semantic.confirmEntityMerge')) + '</button></div></div>';
        }).catch(function(error) {
            mergeCandidate.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var confirmMerge = event.target.closest('[data-confirm-entity-merge]');
    if (confirmMerge && window.api.mergeSemanticEntities) {
        if (!window.confirm(t('semantic.confirmEntityMergeWarning'))) return;
        confirmMerge.disabled = true;
        window.api.mergeSemanticEntities(confirmMerge.dataset.mergeSource, confirmMerge.dataset.mergeTarget).then(function(result) {
            if (!result || !result.success) throw new Error((result && result.message) || t('common.unknownError'));
            if (window.ToastModule) window.ToastModule.success(result.message || t('semantic.entityMerged'));
            show('objects');
        }).catch(function(error) {
            confirmMerge.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
        return;
    }
    var briefCopy = event.target.closest('[data-brief-copy]');
    if (briefCopy && _lastBrief) {
        var briefText = _lastBrief;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(briefText).then(function() {
                if (window.ToastModule) window.ToastModule.success(t('semantic.brief.copied'));
            }).catch(function() {});
        } else if (window.ToastModule) {
            window.ToastModule.error(t('semantic.brief.copyFailed'));
        }
        return;
    }
    var link = event.target.closest('[data-link-action]');
    if (!link) return;
    link.disabled = true;
    var promise = link.dataset.linkAction === 'confirm' ? window.api.confirmLink(link.dataset.from, link.dataset.to) : window.api.rejectLink(link.dataset.from, link.dataset.to);
    promise.then(loadList).catch(function(error) {
        link.disabled = false;
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
    });
}

function onDetailSubmit(event: any) {
    var claimForm = event.target.closest('.semantic-claim-editor');
    if (claimForm && _activeDetail && window.api.updateSemanticClaim) {
        event.preventDefault();
        var submit = claimForm.querySelector('[type="submit"]');
        if (submit) submit.disabled = true;
        window.api.updateSemanticClaim(_activeDetail.id, claimForm.elements.statement.value, claimForm.elements.scope.value, claimForm.elements.claim_type.value).then(function(result) {
            if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
            loadList();
        }).catch(function(error) { if (submit) submit.disabled = false; if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
        return;
    }
    var aliasForm = event.target.closest('.semantic-alias-form');
    if (aliasForm && _activeDetail && window.api.addSemanticEntityAlias) {
        event.preventDefault();
        var alias = aliasForm.elements.alias.value.trim();
        if (!alias) return;
        window.api.addSemanticEntityAlias(_activeDetail.id, alias).then(function(result) {
            if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
            loadDetail(_activeDetail);
        }).catch(function(error) { if (window.ToastModule) window.ToastModule.error(String(error.message || error)); });
    }
}

function applyVisibilityConfig() {
    var ui = window.uiConfig;
    if (ui) {
        applyVisibilityConfigWith(ui);
        return;
    }
    if (window.api && window.api.getUiConfig) {
        window.api.getUiConfig().then(function(cfg) {
            if (cfg) applyVisibilityConfigWith(cfg);
        }).catch(function() {});
    }
}

function applyVisibilityConfigWith(ui: any) {
    if (!ui) return;
    _workbenchEnabled = ui.semantic_workbench_enabled !== false;
    var group = document.getElementById('semantic-sidebar-group');
    if (group) group.style.display = _workbenchEnabled ? '' : 'none';
    if (!_workbenchEnabled) {
        if (_visible) hide();
        return;
    }
    var tabs = Array.isArray(ui.semantic_workbench_tabs) && ui.semantic_workbench_tabs.length
        ? ui.semantic_workbench_tabs
        : ['objects', 'claims', 'quality', 'conflicts', 'links', 'brief'];
    _enabledCategories = tabs.slice();
    var visible: any = {};
    tabs.forEach(function(tab: any) { visible[tab] = true; });
    document.querySelectorAll('#semantic-categories [data-category]').forEach(function(button) {
        (button as HTMLElement).style.display = visible[(button as HTMLElement).dataset.category as string] ? '' : 'none';
    });
    if (_category && !visible[_category]) {
        var fallback = tabs[0] || 'objects';
        _category = fallback;
        document.querySelectorAll('#semantic-categories [data-category]').forEach(function(button) {
            button.classList.toggle('active', (button as HTMLElement).dataset.category === _category);
        });
        if (_visible) {
            _selectedIndex = -1;
            loadList();
        }
    }
    if (['light', 'standard', 'deep'].indexOf(ui.semantic_workbench_intensity) !== -1) {
        _intensity = ui.semantic_workbench_intensity;
    } else {
        _intensity = 'standard';
    }
}

function init() {
    var categories = document.getElementById('semantic-categories');
    if (categories) categories.addEventListener('click', function(event) {
        var button = (event.target as Element).closest('[data-category]');
        if (button) setCategory((button as HTMLElement).dataset.category);
    });
    var objectSwitch = document.getElementById('semantic-object-switch');
    if (objectSwitch) objectSwitch.addEventListener('click', function(event) {
        var button = (event.target as Element).closest('[data-object-kind]');
        if (button) setObjectKind((button as HTMLElement).dataset.objectKind);
    });
    var list = document.getElementById('semantic-workbench-list');
    if (list) list.addEventListener('click', function(event) {
        var briefGenerate = (event.target as Element).closest('[data-brief-generate]');
        if (briefGenerate) { generateBrief(); return; }
        var button = (event.target as Element).closest('[data-semantic-index]');
        if (button) selectItem(Number((button as HTMLElement).dataset.semanticIndex));
    });
    var detail = document.getElementById('semantic-workbench-detail');
    if (detail) { detail.addEventListener('click', onDetailClick); detail.addEventListener('submit', onDetailSubmit); }
    var refresh = document.getElementById('semantic-refresh');
    if (refresh) refresh.addEventListener('click', function() { loadOverview(); loadList(); });
    var close = document.getElementById('semantic-close');
    if (close) close.addEventListener('click', hide);
    var compile = document.getElementById('semantic-compile-all');
    if (compile) compile.addEventListener('click', startCompileAll);
    var search = document.getElementById('semantic-search');
    if (search) search.addEventListener('input', function() { clearTimeout(_searchTimer); _searchTimer = setTimeout(loadList, 220); });
    var status = document.getElementById('semantic-status-filter');
    if (status) status.addEventListener('change', loadList);
    var scan = document.getElementById('semantic-scan-conflicts');
    if (scan) scan.addEventListener('click', function() { scanConflicts(scan); });
    configureStatusFilter();
    applyVisibilityConfig();
    initVerifyStreamListener();
}

window.SemanticWorkbenchModule = { init: init, toggle: toggle, show: show, hide: hide, deactivate: deactivate, load: loadList, openObject: openObject, isVisible: function() { return _visible; }, applyVisibilityConfig: applyVisibilityConfig, isEnabled: isEnabled, enabledCategories: function() { return _enabledCategories.slice(); } };
window.toggleSemanticWorkbench = toggle;

})();
