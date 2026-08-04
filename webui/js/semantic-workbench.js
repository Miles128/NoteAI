(function() { 'use strict';

var _visible = false;
var _category = 'objects';
var _objectKind = 'entities';
var _items = [];
var _selectedIndex = -1;
var _overview = {};
var _loadSeq = 0;
var _detailSeq = 0;
var _searchTimer = null;
var _compileTimer = null;
var _activeDetail = null;
var _activeDetailKind = null;
var _lastBrief = '';
var _pendingTargetId = null;
var _suppressAutoSelect = false;

function esc(value) {
    return window.escapeHtml ? window.escapeHtml(String(value == null ? '' : value)) : String(value == null ? '' : value);
}
function t(key, vars) { return window.t ? window.t(key, vars) : key; }
function currentTab() { return _category === 'objects' ? _objectKind : _category; }

function toggle() { _visible ? hide() : show(_category); }

function show(category) {
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
        button.classList.toggle('active', button.dataset.category === _category);
    });
    var switcher = document.getElementById('semantic-object-switch');
    if (switcher) switcher.style.display = _category === 'objects' ? 'flex' : 'none';
    var graphButton = document.getElementById('titlebar-graph-btn');
    if (graphButton) graphButton.classList.remove('active');
    if (typeof window._deactivatePendingBtn === 'function') window._deactivatePendingBtn();
    configureStatusFilter();
    loadOverview();
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

function setCategory(category) {
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
        button.classList.toggle('active', button.dataset.category === category);
    });
    var switcher = document.getElementById('semantic-object-switch');
    if (switcher) switcher.style.display = category === 'objects' ? 'flex' : 'none';
    configureStatusFilter();
    var search = document.getElementById('semantic-search');
    if (search) search.value = '';
    loadList();
}

function setObjectKind(kind) {
    _objectKind = kind;
    _selectedIndex = -1;
    document.querySelectorAll('#semantic-object-switch [data-object-kind]').forEach(function(button) {
        button.classList.toggle('active', button.dataset.objectKind === kind);
    });
    loadList();
}

function configureStatusFilter() {
    var status = document.getElementById('semantic-status-filter');
    if (!status) return;
    status.hidden = _category !== 'claims' && _category !== 'quality' && _category !== 'conflicts' && _category !== 'links';
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
        query: search ? search.value.trim() : '',
        status: status && !status.hidden ? status.value : undefined,
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
    var list = document.getElementById('semantic-workbench-list');
    if (!list) return;
    var seq = ++_loadSeq;
    list.innerHTML = '<div class="semantic-loading">' + esc(t('common.loading')) + '</div>';
    var title = document.getElementById('semantic-list-title');
    if (title) title.textContent = categoryTitle();
    window.api.getSemanticWorkbench(requestOptions()).then(function(result) {
        if (seq !== _loadSeq) return;
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        _items = result.items || [];
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
    var value = select ? Number(select.value) : 7;
    return value >= 1 && value <= 90 ? value : 7;
}

function loadBrief() {
    var list = document.getElementById('semantic-workbench-list');
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

function renderBriefControls(topics, days) {
    var list = document.getElementById('semantic-workbench-list');
    if (!list) return;
    var options = topics.length
        ? '<option value="">' + esc(t('semantic.brief.chooseTopic')) + '</option>' + topics.map(function(topic) { return '<option value="' + esc(topic) + '">' + esc(topic) + '</option>'; }).join('')
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
    var topicValue = topic ? topic.value.trim() : '';
    if (!topicValue) {
        if (window.ToastModule) window.ToastModule.error(t('semantic.brief.noTopicSelected'));
        return;
    }
    var button = document.querySelector('[data-brief-generate]');
    if (button) button.disabled = true;
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
        if (btn) btn.disabled = false;
    });
}

function renderBrief(result) {
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
    list.innerHTML = _items.map(function(item, index) {
        var title = item.canonical_name || item.statement || item.reason || linkTitle(item);
        var description = item.description || item.scope || conflictSummary(item) || item.reason || '';
        var meta = listMeta(item);
        return '<button type="button" class="semantic-list-item' + (index === _selectedIndex ? ' active' : '') + '" data-semantic-index="' + index + '"><strong>' + esc(title) + '</strong>' + (description ? '<p>' + esc(description) + '</p>' : '') + '<span class="semantic-list-item-meta">' + meta + '</span></button>';
    }).join('');
}

function listMeta(item) {
    if (_category === 'objects') return '<span>' + esc(item.entity_type || t('semantic.tabs.' + _objectKind)) + '</span><span>' + esc(t('semantic.mentions', { count: item.mention_count || 0 })) + '</span>';
    if (_category === 'quality') return '<span>' + esc(t('semantic.qualityRules.' + item.rule)) + '</span><span>' + esc(t('semantic.status.' + (item.status || 'pending'))) + '</span>';
    if (_category === 'claims') return '<span>' + esc(t('semantic.status.' + (item.status || 'active'))) + '</span><span>' + esc(t('semantic.claimTypes.' + (item.claim_type || 'conclusion'))) + '</span><span>' + esc(t('semantic.evidenceCount', { count: item.evidence_count || 0 })) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span>';
    return '<span>' + esc(t('semantic.status.' + (item.status || 'confirmed'))) + '</span>' + (item.has_reverse ? '<span>↔</span>' : '');
}

function linkTitle(item) { return shortPath(item.from) + ' → ' + shortPath(item.to); }
function shortPath(path) { var parts = String(path || '').split('/'); return parts[parts.length - 1] || path || ''; }
function conflictSummary(item) { var p = item.payload || {}; return p.claim_a || p.left_statement || p.statement_a || ''; }

function selectItem(index) {
    if (!_items[index]) return;
    _selectedIndex = index;
    renderList();
    var item = _items[index];
    if (_category === 'objects' || _category === 'claims') loadDetail(item);
    else if (_category === 'quality') renderQualityDetail(item);
    else renderLocalDetail(item);
}

function loadDetail(item) {
    var detail = document.getElementById('semantic-workbench-detail');
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

function openObject(kind, id) {
    if (kind !== 'entity' && kind !== 'concept') return;
    _category = 'objects';
    _objectKind = kind === 'entity' ? 'entities' : 'concepts';
    _pendingTargetId = id;
    _suppressAutoSelect = true;
    show('objects');
    loadDetail({ id: id });
}

function renderObjectDetail(kind, item) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    var title = item.canonical_name || item.statement || '';
    var kicker = kind === 'claim' ? t('semantic.categories.claims') : t('semantic.tabs.' + (kind === 'entity' ? 'entities' : 'concepts'));
    var description = item.description || (item.scope ? t('semantic.scope', { scope: item.scope }) : '');
    var sources = item.sources || [];
    _activeDetail = item;
    _activeDetailKind = kind;
    var sourceHtml = sources.map(function(source) { return renderSource(source, kind); }).join('');
    var typeLabel = kind === 'claim' ? t('semantic.claimTypes.' + (item.claim_type || 'conclusion')) : (item.entity_type || '');
    var status = kind === 'claim' ? '<span>' + esc(t('semantic.status.' + (item.status || 'active'))) + '</span>' : '';
    var pageControls = (kind === 'entity' || kind === 'concept') ? '<div class="semantic-actions"><button data-preview-object-page data-object-kind="' + kind + '" data-object-id="' + esc(item.id) + '">' + esc(t('semantic.previewTopicPage')) + '</button><button data-publish-object-page data-object-kind="' + kind + '" data-object-id="' + esc(item.id) + '">' + esc(t('semantic.publishTopicPage')) + '</button></div>' : '';
    var controls = kind === 'claim' ? renderClaimControls(item) : (kind === 'entity' ? renderEntityAliasControls(item) + pageControls : pageControls);
    var audit = renderAudit(item.audit || []);
    var related = (item.related || []).map(function(relation) {
        return '<button class="semantic-related-object" data-open-semantic-kind="' + esc(relation.object_kind) + '" data-open-semantic-id="' + esc(relation.object_id) + '">' + esc(relation.relation_type) + ' · ' + esc(relation.object_name) + '</button>';
    }).join('');
    var relatedSection = (kind === 'entity' || kind === 'concept') ? '<section class="semantic-detail-section"><h3>' + esc(t('semantic.related')) + '</h3>' + (related || '<div class="semantic-empty">' + esc(t('semantic.empty')) + '</div>') + '</section>' : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(kicker) + '</p><h2>' + esc(title) + '</h2>' + (description ? '<p class="semantic-detail-description">' + esc(description) + '</p>' : '') + '<div class="semantic-detail-meta">' + status + '<span>' + esc(typeLabel) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span><span>' + esc(t('semantic.sources', { count: sources.length })) + '</span></div>' + controls + relatedSection + '<section class="semantic-detail-section"><h3>' + esc(t(kind === 'claim' ? 'semantic.evidenceTitle' : 'semantic.sourceLocations')) + '</h3>' + (sourceHtml || '<div class="semantic-empty">' + esc(t('semantic.empty')) + '</div>') + '</section>' + audit + '</div>';
}

function renderClaimControls(item) {
    var deleted = item.status === 'deleted';
    var statusButton = deleted
        ? '<button class="primary" data-claim-status="active">' + esc(t('semantic.restoreClaim')) + '</button>'
        : '<button class="danger" data-claim-status="deleted">' + esc(t('semantic.deleteClaim')) + '</button>';
    var topic = ((item.sources || [])[0] || {}).topic || '';
    var pageActions = topic ? '<button data-preview-topic-page="' + esc(topic) + '">' + esc(t('semantic.previewTopicPage')) + '</button><button data-publish-topic-page="' + esc(topic) + '">' + esc(t('semantic.publishTopicPage')) + '</button>' : '';
    return '<div class="semantic-actions"><button data-edit-claim>' + esc(t('semantic.editClaim')) + '</button>' + statusButton + pageActions + '</div>' +
        '<form class="semantic-claim-editor" hidden><label>' + esc(t('semantic.claimStatement')) + '<textarea name="statement" required>' + esc(item.statement || '') + '</textarea></label><label>' + esc(t('semantic.claimScope')) + '<input name="scope" value="' + esc(item.scope || '') + '"></label><label>' + esc(t('semantic.claimType')) + '<select name="claim_type"><option value="conclusion"' + (item.claim_type === 'conclusion' ? ' selected' : '') + '>' + esc(t('semantic.claimTypes.conclusion')) + '</option><option value="hypothesis"' + (item.claim_type === 'hypothesis' ? ' selected' : '') + '>' + esc(t('semantic.claimTypes.hypothesis')) + '</option></select></label><div class="semantic-actions"><button type="submit" class="primary">' + esc(t('common.save')) + '</button><button type="button" data-cancel-claim-edit>' + esc(t('common.cancel')) + '</button></div></form>';
}

function renderEntityAliasControls(item) {
    var aliases = (item.aliases || []).map(function(alias) { return '<span class="semantic-alias-chip">' + esc(alias) + '</span>'; }).join('');
    return '<section class="semantic-detail-section"><h3>' + esc(t('semantic.aliases')) + '</h3><div class="semantic-aliases">' + (aliases || '<span class="semantic-muted">' + esc(t('semantic.noAliases')) + '</span>') + '</div><form class="semantic-alias-form"><input name="alias" required placeholder="' + esc(t('semantic.aliasPlaceholder')) + '"><button type="submit">' + esc(t('semantic.addAlias')) + '</button></form></section>';
}

function renderAudit(items) {
    if (!items.length) return '';
    return '<section class="semantic-detail-section semantic-audit"><h3>' + esc(t('semantic.auditTitle')) + '</h3>' + items.map(function(item) { return '<div><span>' + esc(t('semantic.auditActions.' + item.action)) + '</span><time>' + esc(item.created_at || '') + '</time></div>'; }).join('') + '</section>';
}

function renderSource(source, kind) {
    var heading = (source.heading_path || []).join(' › ');
    var label = (source.title || shortPath(source.path)) + (heading ? ' · ' + heading : '') + ' · L' + (source.start_line || 1);
    var evidenceAction = kind === 'claim' ? '<button class="semantic-evidence-action" data-evidence-id="' + esc(source.id) + '" data-evidence-status="' + (source.status === 'excluded' ? 'active' : 'excluded') + '">' + esc(t(source.status === 'excluded' ? 'semantic.restoreEvidence' : 'semantic.excludeEvidence')) + '</button>' : '';
    return '<article class="semantic-source-card' + (source.status === 'excluded' ? ' is-excluded' : '') + '"><div class="semantic-source-heading"><button class="semantic-source" data-open-path="' + esc(source.path) + '">' + esc(label) + '</button>' + evidenceAction + '</div><blockquote>' + esc(source.excerpt || '') + '</blockquote></article>';
}

function renderLocalDetail(item) {
    if (_category === 'links') return renderLinkDetail(item);
    renderConflictDetail(item);
}

function renderQualityDetail(item) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    _activeDetail = item;
    _activeDetailKind = 'quality';
    var candidates = (item.candidate_names || []).map(function(name, index) {
        var candidateId = (item.candidate_ids || [])[index] || '';
        return '<li>' + (candidateId ? '<button data-quality-merge-candidate="' + esc(candidateId) + '">' + esc(name) + '</button>' : esc(name)) + '</li>';
    }).join('');
    var action = item.status === 'pending'
        ? '<button class="primary" data-quality-id="' + esc(item.id) + '" data-quality-status="reviewed">' + esc(t('semantic.markReviewed')) + '</button>'
        : '<button data-quality-id="' + esc(item.id) + '" data-quality-status="pending">' + esc(t('semantic.restorePending')) + '</button>';
    var inbox = item.status === 'pending' ? '<button data-quality-enqueue="' + esc(item.id) + '">' + esc(t('semantic.addToInbox')) + '</button>' : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.quality')) + '</p><h2>' + esc(item.entity_name || '') + '</h2><div class="semantic-detail-meta"><span>' + esc(t('semantic.qualityRules.' + item.rule)) + '</span><span>' + esc(t('semantic.status.' + item.status)) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span></div><section class="semantic-detail-section"><h3>' + esc(t('semantic.qualityReason')) + '</h3><p>' + esc(item.reason || '') + '</p></section>' + (candidates ? '<section class="semantic-detail-section"><h3>' + esc(t('semantic.qualityCandidates')) + '</h3><ul>' + candidates + '</ul></section>' : '') + '<div class="semantic-actions"><button data-quality-open-entity="' + esc(item.entity_id) + '">' + esc(t('semantic.openEntity')) + '</button>' + inbox + action + '</div></div>';
}

function renderConflictDetail(item) {
    var detail = document.getElementById('semantic-workbench-detail');
    var payload = item.payload || {};
    var left = payload.left_statement || payload.claim_a || payload.statement_a || '';
    var right = payload.right_statement || payload.claim_b || payload.statement_b || '';
    var action = item.status === 'pending' ? '<button class="primary" data-review-id="' + esc(item.id) + '" data-review-status="reviewed">' + esc(t('semantic.markReviewed')) + '</button>' : '<button data-review-id="' + esc(item.id) + '" data-review-status="pending">' + esc(t('semantic.restorePending')) + '</button>';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.conflicts')) + '</p><h2>' + esc(item.reason || t('semantic.conflictCandidate')) + '</h2><div class="semantic-detail-meta"><span>' + esc(t('semantic.status.' + item.status)) + '</span><span>' + esc(item.created_at || '') + '</span></div><section class="semantic-detail-section"><h3>' + esc(t('semantic.conflictingClaims')) + '</h3><div class="semantic-route"><span>' + esc(left || '—') + '</span><span>↔</span><span>' + esc(right || '—') + '</span></div></section><div class="semantic-actions">' + action + '</div></div>';
}

function renderLinkDetail(item) {
    var detail = document.getElementById('semantic-workbench-detail');
    var actions = item.status === 'pending' ? '<div class="semantic-actions"><button class="primary" data-link-action="confirm" data-from="' + esc(item.from) + '" data-to="' + esc(item.to) + '">' + esc(t('semantic.confirm')) + '</button><button data-link-action="reject" data-from="' + esc(item.from) + '" data-to="' + esc(item.to) + '">' + esc(t('semantic.reject')) + '</button></div>' : '';
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(t('semantic.categories.links')) + '</p><h2>' + esc(t('semantic.linkRelation')) + '</h2><p class="semantic-detail-description">' + esc(item.reason || t('semantic.related')) + '</p><div class="semantic-detail-meta"><span>' + esc(t('semantic.status.' + item.status)) + '</span>' + (item.has_reverse ? '<span class="semantic-reverse">↔ ' + esc(t('semantic.bidirectional')) + '</span>' : '') + '</div><div class="semantic-route"><button class="semantic-link-endpoint" data-open-path="' + esc(item.from) + '">' + esc(item.from) + '</button><span>→</span><button class="semantic-link-endpoint" data-open-path="' + esc(item.to) + '">' + esc(item.to) + '</button></div>' + actions + '</div>';
}

function renderEmptyDetail(error) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    if (error) {
        detail.innerHTML = '<div class="semantic-error">' + esc(error) + '</div>';
        return;
    }
    var keys = ['documents', 'blocks', 'concepts', 'entities', 'claims', 'evidence'];
    var metrics = keys.map(function(key) {
        return '<div class="semantic-metric"><strong>' + esc(_overview[key] || 0) + '</strong><span>' + esc(t('semantic.metrics.' + key)) + '</span></div>';
    }).join('');
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">Semantic IR</p><h2>' + esc(t('semantic.categoryEmptyTitle')) + '</h2><p class="semantic-detail-description">' + esc(t(_category === 'conflicts' ? 'semantic.emptyConflicts' : 'semantic.selectHint')) + '</p><div class="semantic-metrics">' + metrics + '</div><section class="semantic-changes" id="semantic-changes"><h3>' + esc(t('semantic.changes.title')) + ' <span class="semantic-changes-window">' + esc(t('semantic.changes.window')) + '</span></h3><p class="semantic-detail-description">' + esc(t('semantic.changes.empty')) + '</p></section></div>';
    loadChanges();
}

function loadChanges() {
    if (!window.api || !window.api.getSemanticChanges) return;
    window.api.getSemanticChanges({ days: 7, limit: 8 }).then(function(result) {
        if (!result || !result.success) throw new Error((result && result.message) || '');
        renderChanges(result);
    }).catch(function() {
        var box = document.getElementById('semantic-changes');
        if (box) box.querySelector('p') && (box.querySelector('p').textContent = t('semantic.changes.loadFailed'));
    });
}

function renderChanges(result) {
    var box = document.getElementById('semantic-changes');
    if (!box) return;
    var counts = result.counts || [];
    var items = result.items || [];
    var total = result.total || 0;
    var summary = {};
    counts.forEach(function(entry) {
        summary[entry.change_kind] = (summary[entry.change_kind] || 0) + entry.count;
    });
    var badgeOrder = ['added', 'updated', 'invalidated', 'removed'];
    var badges = badgeOrder.filter(function(kind) { return summary[kind]; }).map(function(kind) {
        return '<span class="semantic-change-badge semantic-change-' + kind + '">' + esc(t('semantic.changes.' + kind)) + ' ' + summary[kind] + '</span>';
    }).join('');
    var rows = items.map(function(item) {
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
        renderCoverage(result.compile_job || null);
        if (_selectedIndex < 0 && !_suppressAutoSelect) renderEmptyDetail();
        if (result.compile_job && result.compile_job.status === 'running') scheduleCompilePoll();
    }).catch(function() {});
}

function renderCoverage(job) {
    var coverage = document.getElementById('semantic-coverage');
    var button = document.getElementById('semantic-compile-all');
    var progress = document.getElementById('semantic-compile-progress');
    var source = _overview.source_documents || 0;
    var compiled = _overview.documents || 0;
    var percent = source ? Math.min(100, Math.round(compiled * 100 / source)) : 0;
    if (coverage) {
        coverage.textContent = compiled + '/' + source;
        coverage.title = t('semantic.coverageLabel', { percent: percent, uncompiled: _overview.uncompiled_documents || 0 });
    }
    var running = job && job.status === 'running';
    if (button) { button.disabled = !!running; button.textContent = t(running ? 'semantic.compiling' : 'semantic.compileAll'); }
    if (progress) {
        progress.hidden = !job;
        progress.textContent = job ? (job.message || '') : '';
    }
}

function startCompileAll() {
    if (!window.api || !window.api.startSemanticFullCompile) return;
    var button = document.getElementById('semantic-compile-all');
    if (button) button.disabled = true;
    window.api.startSemanticFullCompile().then(function(result) {
        if (!result || !result.success) throw new Error(result && result.message ? result.message : t('common.unknownError'));
        renderCoverage(result.job || null);
        scheduleCompilePoll();
    }).catch(function(error) {
        if (button) button.disabled = false;
        if (window.ToastModule) window.ToastModule.error(String(error.message || error));
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

function openSource(path) {
    if (!path) return;
    deactivate();
    if (window.TreeModule && window.TreeModule.selectFile) window.TreeModule.selectFile(path, shortPath(path));
    else if (typeof window.showPreview === 'function') window.showPreview({ path: path });
}

function onDetailClick(event) {
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
        if (editor) editor.hidden = false;
        return;
    }
    var cancelEdit = event.target.closest('[data-cancel-claim-edit]');
    if (cancelEdit) {
        var editForm = document.querySelector('.semantic-claim-editor');
        if (editForm) editForm.hidden = true;
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
        if (window.api && window.api.getSemanticDetail) {
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

function onDetailSubmit(event) {
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

function init() {
    var categories = document.getElementById('semantic-categories');
    if (categories) categories.addEventListener('click', function(event) {
        var button = event.target.closest('[data-category]');
        if (button) setCategory(button.dataset.category);
    });
    var objectSwitch = document.getElementById('semantic-object-switch');
    if (objectSwitch) objectSwitch.addEventListener('click', function(event) {
        var button = event.target.closest('[data-object-kind]');
        if (button) setObjectKind(button.dataset.objectKind);
    });
    var list = document.getElementById('semantic-workbench-list');
    if (list) list.addEventListener('click', function(event) {
        var briefGenerate = event.target.closest('[data-brief-generate]');
        if (briefGenerate) { generateBrief(); return; }
        var button = event.target.closest('[data-semantic-index]');
        if (button) selectItem(Number(button.dataset.semanticIndex));
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
    configureStatusFilter();
    loadOverview();
}

window.SemanticWorkbenchModule = { init: init, toggle: toggle, show: show, hide: hide, deactivate: deactivate, load: loadList, openObject: openObject, isVisible: function() { return _visible; } };
window.toggleSemanticWorkbench = toggle;

})();
