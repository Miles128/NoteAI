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
    status.hidden = _category !== 'conflicts' && _category !== 'links';
    if (_category === 'conflicts') {
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
        if (_items.length) selectItem(0);
        else renderEmptyDetail();
    }).catch(function(error) {
        if (seq !== _loadSeq) return;
        list.innerHTML = '<div class="semantic-error">' + esc(t('semantic.loadFailed', { error: String(error.message || error) })) + '</div>';
        renderEmptyDetail(String(error.message || error));
    });
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
    if (_category === 'claims') return '<span>' + esc(t('semantic.claimTypes.' + (item.claim_type || 'conclusion'))) + '</span><span>' + esc(t('semantic.evidenceCount', { count: item.evidence_count || 0 })) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span>';
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

function renderObjectDetail(kind, item) {
    var detail = document.getElementById('semantic-workbench-detail');
    if (!detail) return;
    var title = item.canonical_name || item.statement || '';
    var kicker = kind === 'claim' ? t('semantic.categories.claims') : t('semantic.tabs.' + (kind === 'entity' ? 'entities' : 'concepts'));
    var description = item.description || (item.scope ? t('semantic.scope', { scope: item.scope }) : '');
    var sources = item.sources || [];
    var sourceHtml = sources.map(renderSource).join('');
    var typeLabel = kind === 'claim' ? t('semantic.claimTypes.' + (item.claim_type || 'conclusion')) : (item.entity_type || '');
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">' + esc(kicker) + '</p><h2>' + esc(title) + '</h2>' + (description ? '<p class="semantic-detail-description">' + esc(description) + '</p>' : '') + '<div class="semantic-detail-meta"><span>' + esc(typeLabel) + '</span><span>' + Math.round((item.confidence || 0) * 100) + '%</span><span>' + esc(t('semantic.sources', { count: sources.length })) + '</span></div><section class="semantic-detail-section"><h3>' + esc(t(kind === 'claim' ? 'semantic.evidenceTitle' : 'semantic.sourceLocations')) + '</h3>' + (sourceHtml || '<div class="semantic-empty">' + esc(t('semantic.empty')) + '</div>') + '</section></div>';
}

function renderSource(source) {
    var heading = (source.heading_path || []).join(' › ');
    var label = (source.title || shortPath(source.path)) + (heading ? ' · ' + heading : '') + ' · L' + (source.start_line || 1);
    return '<article class="semantic-source-card"><button class="semantic-source" data-open-path="' + esc(source.path) + '">' + esc(label) + '</button><blockquote>' + esc(source.excerpt || '') + '</blockquote></article>';
}

function renderLocalDetail(item) {
    if (_category === 'links') return renderLinkDetail(item);
    renderConflictDetail(item);
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
    detail.innerHTML = '<div class="semantic-detail-inner"><p class="semantic-detail-kicker">Semantic IR</p><h2>' + esc(t('semantic.categoryEmptyTitle')) + '</h2><p class="semantic-detail-description">' + esc(t(_category === 'conflicts' ? 'semantic.emptyConflicts' : 'semantic.selectHint')) + '</p><div class="semantic-metrics">' + metrics + '</div></div>';
}

function loadOverview() {
    if (!window.api || !window.api.getSemanticWorkbench) return;
    window.api.getSemanticWorkbench({ tab: 'overview' }).then(function(result) {
        if (!result || !result.success) return;
        _overview = result.overview || {};
        renderCoverage(result.compile_job || null);
        if (_selectedIndex < 0) renderEmptyDetail();
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
    var source = event.target.closest('[data-open-path]');
    if (source) return openSource(source.dataset.openPath);
    var review = event.target.closest('[data-review-id]');
    if (review && window.api.reviewSemanticConflict) {
        review.disabled = true;
        window.api.reviewSemanticConflict(review.dataset.reviewId, review.dataset.reviewStatus).then(loadList).catch(function(error) {
            review.disabled = false;
            if (window.ToastModule) window.ToastModule.error(String(error.message || error));
        });
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
        var button = event.target.closest('[data-semantic-index]');
        if (button) selectItem(Number(button.dataset.semanticIndex));
    });
    var detail = document.getElementById('semantic-workbench-detail');
    if (detail) detail.addEventListener('click', onDetailClick);
    var refresh = document.getElementById('semantic-refresh');
    if (refresh) refresh.addEventListener('click', function() { loadOverview(); loadList(); });
    var compile = document.getElementById('semantic-compile-all');
    if (compile) compile.addEventListener('click', startCompileAll);
    var search = document.getElementById('semantic-search');
    if (search) search.addEventListener('input', function() { clearTimeout(_searchTimer); _searchTimer = setTimeout(loadList, 220); });
    var status = document.getElementById('semantic-status-filter');
    if (status) status.addEventListener('change', loadList);
    configureStatusFilter();
    loadOverview();
}

window.SemanticWorkbenchModule = { init: init, toggle: toggle, show: show, hide: hide, deactivate: deactivate, load: loadList, isVisible: function() { return _visible; } };
window.toggleSemanticWorkbench = toggle;

})();
