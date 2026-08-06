(function() { 'use strict';

var _lastPending = null;
var _refreshTimer = null;
var _weeklyBriefTimer = null;

function esc(text) {
    return window.escapeHtml ? window.escapeHtml(String(text || '')) : String(text || '');
}

function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setFlow(stage, state, text) {
    var node = document.querySelector('[data-home-stage="' + stage + '"]');
    var label = document.getElementById('home-flow-' + stage);
    if (node) {
        node.classList.remove('is-running', 'is-warning', 'is-failed');
        if (state && state !== 'ok') node.classList.add('is-' + state);
    }
    if (label) label.textContent = text;
}

function hasRunningJob(jobs, predicate) {
    return (jobs || []).some(function(job) {
        return job.status === 'running' && predicate(job);
    });
}

function hasFailedJob(jobs, predicate) {
    return (jobs || []).some(function(job) {
        return job.status === 'failed' && predicate(job);
    });
}

function countFiles(nodes) {
    var count = 0;
    (nodes || []).forEach(function(node) {
        if (node.type === 'file' && node.name && node.name.toLowerCase().endsWith('.md')) count++;
        if (node.children) count += countFiles(node.children);
    });
    return count;
}

function countTopics(nodes) {
    var count = 0;
    (nodes || []).forEach(function(node) {
        if (node.type === 'folder' && node.path && node.path.indexOf('Notes/') === 0) count++;
        if (node.children) count += countTopics(node.children);
    });
    return count;
}

function summarizePending(result) {
    var items = (result && Array.isArray(result.items)) ? result.items : [];
    var cascade = (result && Array.isArray(result.cascade_failures)) ? result.cascade_failures : [];
    var convert = (result && Array.isArray(result.convert_failures)) ? result.convert_failures : [];
    var lintTotal = result && result.lint && result.lint.summary ? (result.lint.summary.total || 0) : 0;
    return {
        count: items.length + cascade.length + convert.length + lintTotal,
        topics: items.filter(function(x) { return x.kind === 'topic' || x.type === 'topic'; }).length,
        links: items.filter(function(x) { return x.kind === 'link' || x.type === 'link'; }).length,
        cascade: cascade.length,
        convert: convert.length,
        lint: lintTotal
    };
}

function renderPending(summary) {
    var el = document.getElementById('home-pending-body');
    if (!el) return;
    if (!summary || summary.count < 1) {
        el.innerHTML = '<div class="home-empty">' + esc(window.t('home.pendingEmpty')) + '</div>';
        return;
    }
    var rows = [];
    if (summary.topics) rows.push([window.t('pending.typeTopic'), summary.topics]);
    if (summary.links) rows.push([window.t('pending.typeLink'), summary.links]);
    if (summary.cascade) rows.push([window.t('pending.typeCascade'), summary.cascade]);
    if (summary.convert) rows.push([window.t('pending.typeConvert'), summary.convert]);
    if (summary.lint) rows.push([window.t('pending.typeLint'), summary.lint]);
    el.innerHTML = rows.map(function(row) {
        return '<div class="home-status-row"><span>' + esc(row[0]) + '</span><strong>' + row[1] + '</strong></div>';
    }).join('');
}

function jobLabel(job) {
    return job.label || job.id || window.t('home.jobUnknown');
}

function statusLabel(status) {
    if (status === 'running') return window.t('home.statusRunning');
    if (status === 'complete') return window.t('home.statusComplete');
    if (status === 'failed') return window.t('home.statusFailed');
    if (status === 'cancelled') return window.t('home.statusCancelled');
    return status || '-';
}

function renderJobs(targetId, jobs, emptyText) {
    var el = document.getElementById(targetId);
    if (!el) return;
    if (!jobs || !jobs.length) {
        el.innerHTML = '<div class="home-empty">' + esc(emptyText) + '</div>';
        return;
    }
    el.innerHTML = jobs.slice(0, 4).map(function(job) {
        var progress = Math.round((job.progress || 0) * 100);
        var cls = 'home-job-status is-' + esc(job.status || 'idle');
        return '<div class="home-job-row">' +
            '<div class="home-job-main">' +
                '<span class="home-job-title">' + esc(jobLabel(job)) + '</span>' +
                '<span class="' + cls + '">' + esc(statusLabel(job.status)) + '</span>' +
            '</div>' +
            '<div class="home-job-message">' + esc(job.message || '') + '</div>' +
            '<div class="home-job-track"><div style="width:' + progress + '%"></div></div>' +
        '</div>';
    }).join('');
}

function renderOrganize(status, jobs) {
    var running = (jobs || []).filter(function(job) {
        return job.status === 'running' && (job.kind === 'ingest' || job.kind === 'conversion');
    });
    var body = document.getElementById('home-organize-body');
    if (!body) return;
    if (running.length) {
        renderJobs('home-organize-body', running, window.t('home.organizeIdle'));
        return;
    }
    var msg = window.t('home.organizeIdle');
    if (status && status.running) {
        msg = status.message || window.t('ingest.pipelineRunning');
    } else if (status && status.status === 'complete') {
        msg = status.message || window.t('home.organizeComplete');
    } else if (status && status.needs_resume) {
        msg = status.message || window.t('home.organizeNeedsResume');
    }
    body.innerHTML = '<div class="home-status-row"><span>' + esc(msg) + '</span><strong>' +
        esc((status && status.status) ? statusLabel(status.status) : window.t('home.flow.ready')) + '</strong></div>';
}

function renderCompile(jobs) {
    var compileJobs = (jobs || []).filter(function(job) {
        return job.kind === 'survey' || job.kind === 'rag_index' ||
            job.id === 'ingest_cascade_surveys' || job.id === 'rag-index-progress';
    });
    renderJobs('home-compile-body', compileJobs, window.t('home.compileIdle'));
}

function renderFlow(summary, ingestStatus, jobs, indexStatus) {
    var ingestRunning = hasRunningJob(jobs, function(job) { return job.kind === 'ingest'; }) || (ingestStatus && ingestStatus.running);
    var conversionRunning = hasRunningJob(jobs, function(job) { return job.kind === 'conversion'; });
    var surveyRunning = hasRunningJob(jobs, function(job) { return job.kind === 'survey' || job.id === 'ingest_cascade_surveys'; });
    var indexRunning = hasRunningJob(jobs, function(job) { return job.kind === 'rag_index' || job.id === 'rag-index-progress'; });
    var ingestFailed = hasFailedJob(jobs, function(job) { return job.kind === 'ingest' || job.kind === 'conversion'; });
    var surveyFailed = hasFailedJob(jobs, function(job) { return job.kind === 'survey' || job.id === 'ingest_cascade_surveys'; }) || summary.cascade > 0;
    var indexFailed = hasFailedJob(jobs, function(job) { return job.kind === 'rag_index' || job.id === 'rag-index-progress'; });

    setFlow('ingest', ingestFailed ? 'failed' : (ingestRunning || conversionRunning ? 'running' : 'ok'),
        ingestFailed ? window.t('home.flow.failed') : (ingestRunning || conversionRunning ? window.t('home.flow.running') : window.t('home.flow.ready')));
    setFlow('classify', summary.topics > 0 ? 'warning' : (ingestRunning ? 'running' : 'ok'),
        summary.topics > 0 ? window.t('home.flow.needsReview') : (ingestRunning ? window.t('home.flow.running') : window.t('home.flow.ready')));
    setFlow('survey', surveyFailed ? 'failed' : (surveyRunning ? 'running' : 'ok'),
        surveyFailed ? window.t('home.flow.needsReview') : (surveyRunning ? window.t('home.flow.running') : window.t('home.flow.ready')));
    var indexNeedsRepair = indexStatus && indexStatus.enabled && indexStatus.needs_rebuild;
    setFlow('index', indexFailed ? 'failed' : (indexRunning ? 'running' : (indexNeedsRepair ? 'warning' : 'ok')),
        indexFailed ? window.t('home.flow.failed') : (indexRunning ? window.t('home.flow.running') : (indexNeedsRepair ? window.t('home.flow.needsRebuild') : window.t('home.flow.ready'))));
}

function setCommand(command) {
    var cmd = command || {};
    setText('home-command-title', window.t(cmd.titleKey || 'home.commandTitle'));
    setText('home-command-desc', window.t(cmd.descKey || 'home.commandDesc', cmd.params || {}));
    var btn = document.getElementById('home-command-action-btn');
    if (!btn) return;
    btn.dataset.homeAction = cmd.action || 'refresh';
    btn.textContent = window.t(cmd.actionTextKey || 'home.actionRefresh');
    btn.disabled = cmd.action === 'running';
}

function command(titleKey, descKey, params, action, actionTextKey) {
    return {
        titleKey: titleKey,
        descKey: descKey,
        params: params || {},
        action: action || 'refresh',
        actionTextKey: actionTextKey || 'home.actionRefresh'
    };
}

function deriveRecommendation(summary, ingestStatus, jobs, updatePlan, indexStatus) {
    var running = (jobs || []).filter(function(job) { return job.status === 'running'; });
    if (running.length) {
        return command('home.commandTitleRunning', 'home.commandDescRunning', { count: running.length }, 'running', 'home.actionRunning');
    }
    if (summary && summary.count > 0) {
        return command('home.commandTitleAttention', 'home.commandDescAttention', { count: summary.count }, 'pending', 'home.actionOpenPending');
    }
    if (ingestStatus && ingestStatus.needs_resume) {
        return command('home.commandTitleResume', 'home.commandDescResume', {}, 'organize', 'home.actionResume');
    }
    if (updatePlan && updatePlan.action === 'start') {
        return command('home.commandTitleUpdateFound', 'home.commandDescUpdateFound', {}, 'organize', 'home.actionOrganize');
    }
    if (indexStatus && indexStatus.success && indexStatus.enabled && !indexStatus.built) {
        return command('home.commandTitleIndexMissing', 'home.commandDescIndexMissing', {}, 'rebuild_index', 'home.actionRebuildIndex');
    }
    return command('home.commandTitle', 'home.commandDesc', {}, 'refresh', 'home.actionRefresh');
}

function runRecommendedAction() {
    var btn = document.getElementById('home-command-action-btn');
    var action = btn && btn.dataset.homeAction || 'refresh';
    if (action === 'pending') {
        if (typeof window.togglePendingView === 'function') window.togglePendingView();
        return;
    }
    if (action === 'organize') {
        checkUpdates();
        return;
    }
    if (action === 'rebuild_index') {
        if (window.api && window.api.ragRebuildIndex) {
            window.api.ragRebuildIndex().then(function() {
                scheduleRefresh();
            }).catch(function(err) {
                console.warn('[Home] rebuild index failed:', err);
                if (window.updateStatus) {
                    window.updateStatus(window.t('assistant.indexRequestFailed', { message: err.message || String(err) }));
                }
            });
        }
        return;
    }
    refresh();
}

function renderActivityItems(result) {
    var body = document.getElementById('home-activity-body');
    if (!body) return;
    if (!result || !result.success || !result.items || !result.items.length) {
        body.innerHTML = '<div class="home-empty">' + esc(window.t('home.activityEmpty')) + '</div>';
        return;
    }
    var rows = result.items.slice(0, 5).map(function(item) {
        var label = esc(item.label || item.object_id || '');
        var source = item.source_path ? '<span class="home-activity-source">' + esc(item.source_path) + '</span>' : '';
        var kindKey = item.change_kind === 'added' ? 'activity.gained' :
            item.change_kind === 'updated' ? 'activity.corrected' :
            item.change_kind === 'invalidated' ? 'activity.doubted' :
            item.change_kind === 'removed' ? 'activity.removed' : null;
        var kindText = kindKey ? window.t(kindKey) : (window.t('semantic.changes.' + item.change_kind, {}) || item.change_kind);
        return '<div class="home-activity-row">' +
            '<span class="home-activity-kind">' + esc(kindText) + '</span>' +
            '<span class="home-activity-label" title="' + label + '">' + label + '</span>' +
            source +
            '</div>';
    }).join('');
    body.innerHTML = '<div class="home-activity-list">' + rows + '</div>' +
        (result.total > 5 ? '<button type="button" class="home-activity-more-btn" onclick="window.HomeDashboardModule.openSemanticChanges()">' + esc(window.t('home.activityViewAll')) + '</button>' : '');
}

function loadActivity() {
    if (!window.api || !window.api.getSemanticChanges) return;
    window.api.getSemanticChanges({ days: 7, limit: 5 }).then(function(result) {
        renderActivityItems(result);
    }).catch(function() {});
}

function renderDashboardStatus(status) {
    var summary = status.pending_summary || summarizePending(status.pending || {});
    var jobs = status.jobs || [];
    var ingestStatus = status.ingest || {};
    var running = jobs.filter(function(job) { return job.status === 'running'; });
    var stats = status.stats || {};
    _lastPending = status.pending || _lastPending || {};
    if (window.JobCenterModule && window.JobCenterModule.replaceJobs) {
        window.JobCenterModule.replaceJobs(jobs);
    }

    setText('home-stat-notes', stats.notes || 0);
    setText('home-stat-topics', stats.topics || 0);
    setText('home-stat-pending', summary.count || 0);
    setText('home-stat-running', running.length);
    setText('home-vital-pending', summary.count || 0);
    setText('home-vital-organize', running.some(function(job) { return job.kind === 'ingest' || job.kind === 'conversion'; })
        ? window.t('home.statusRunning')
        : window.t('home.statusComplete'));
    setText('home-vital-compile', running.some(function(job) { return job.kind === 'survey' || job.kind === 'rag_index'; })
        ? window.t('home.statusRunning')
        : window.t('home.statusComplete'));
    setCommand(deriveRecommendation(summary, ingestStatus, jobs, status.update_plan, status.index));
    renderPending(summary);
    renderOrganize(ingestStatus, jobs);
    renderCompile(jobs);
    renderFlow(summary, ingestStatus, jobs, status.index || {});
    loadActivity();
}

function refreshFallback() {
    var tree = window.AppState && window.AppState.lastFileTreeData ? window.AppState.lastFileTreeData : [];
    setText('home-stat-notes', countFiles(tree));
    setText('home-stat-topics', countTopics(tree));

    var pendingP = (window.api && window.api.getAllPending) ? window.api.getAllPending() : Promise.resolve(_lastPending || {});
    var ingestP = (window.api && window.api.getIngestStatus) ? window.api.getIngestStatus() : Promise.resolve({});
    var jobsP = window.JobCenterModule && window.JobCenterModule.refresh
        ? window.JobCenterModule.refresh({ include_finished: true, limit: 50 })
        : Promise.resolve([]);
    var updatePlanP = (window.api && window.api.checkIngestUpdates)
        ? window.api.checkIngestUpdates().catch(function() { return null; })
        : Promise.resolve(null);
    var indexP = (window.api && window.api.ragIndexStatus)
        ? window.api.ragIndexStatus().catch(function() { return null; })
        : Promise.resolve(null);

    return Promise.all([pendingP, ingestP, jobsP, updatePlanP, indexP]).then(function(results) {
        renderDashboardStatus({
            stats: { notes: countFiles(tree), topics: countTopics(tree) },
            pending: results[0] || {},
            pending_summary: summarizePending(results[0] || {}),
            ingest: results[1] || {},
            jobs: results[2] || [],
            update_plan: results[3],
            index: results[4]
        });
    });
}

var _refreshPromise = null;

function _refreshOnce() {
    if (!window.api || !window.api.getDashboardStatus) {
        return refreshFallback().catch(function(err) {
            console.warn('[Home] refresh failed:', err);
        });
    }
    return window.api.getDashboardStatus().then(function(status) {
        if (!status || !status.success) return refreshFallback();
        renderDashboardStatus(status);
    }).catch(function(err) {
        console.warn('[Home] refresh failed:', err);
        return refreshFallback();
    });
}

function refresh() {
    if (_refreshPromise) return _refreshPromise;
    _refreshPromise = Promise.resolve(_refreshOnce()).finally(function() {
        _refreshPromise = null;
    });
    return _refreshPromise;
}

async function checkUpdates() {
    var startBtn = document.getElementById('home-start-ingest-btn');
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = window.t('home.checkingUpdates');
    }
    setCommand(command('home.commandTitleChecking', 'home.commandDescChecking', {}, 'running', 'home.actionRunning'));
    try {
        var plan = window.api && window.api.checkIngestUpdates
            ? await window.api.checkIngestUpdates()
            : { success: true, action: 'start', mode: 'incremental', file_paths: [] };
        if (!plan || !plan.success) {
            setCommand(command('home.commandTitleCheckFailed', 'home.commandDescCheckFailed', { message: (plan && plan.message) || window.t('common.unknownError') }));
            return plan;
        }
        if (plan.action !== 'start') {
            await refresh();
            setCommand(command('home.commandTitleUpToDate', 'home.commandDescUpToDate'));
            return plan;
        }
        setCommand(command('home.commandTitleUpdateFound', 'home.commandDescUpdateFound', {}, 'running', 'home.actionRunning'));
        if (window.IngestModule && window.IngestModule.startIngest) {
            await window.IngestModule.startIngest(plan.mode || 'incremental', plan.file_paths || [], { resume: !!plan.resume });
        } else if (window.api && window.api.startIngest) {
            await window.api.startIngest({
                mode: plan.mode || 'incremental',
                file_paths: plan.file_paths || [],
                resume: !!plan.resume
            });
        }
        await refresh();
        return plan;
    } catch (err) {
        setCommand(command('home.commandTitleCheckFailed', 'home.commandDescCheckFailed', { message: err && err.message ? err.message : String(err) }));
        return { success: false, message: err && err.message ? err.message : String(err) };
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.textContent = window.t('home.checkUpdates');
        }
    }
}

function scheduleRefresh() {
    if (_refreshTimer) clearTimeout(_refreshTimer);
    _refreshTimer = setTimeout(function() {
        _refreshTimer = null;
        refresh();
    }, 100);
}

function show() {
    var contentPanel = document.getElementById('content-panel');
    var home = document.getElementById('home-dashboard');
    var graph = document.getElementById('graph-panel');
    var content = document.getElementById('content-area');
    var preview = document.getElementById('preview-panel');
    var pending = document.getElementById('pending-view');
    if (contentPanel) contentPanel.style.display = 'flex';
    if (home) home.style.display = '';
    if (graph) graph.style.display = 'none';
    if (content) content.style.display = 'none';
    if (preview) preview.style.display = 'none';
    if (pending) pending.style.display = 'none';
    refresh();
}

function openSemanticChanges() {
    if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.show) {
        window.SemanticWorkbenchModule.show('overview');
    }
}

function renderMarkdown(md) {
    if (!md) return '';
    var rendered = md;
    if (window.marked) {
        try { rendered = window.marked.parse(md); } catch (e) { /* fallback */ }
    } else {
        rendered = md.split('\n').map(function(line) {
            var t = String(line).trim();
            if (/^#{1,6}\s/.test(t)) {
                var level = t.match(/^#{1,6}/)[0].length;
                return '<h' + level + '>' + esc(t.replace(/^#{1,6}\s*/, '')) + '</h' + level + '>';
            }
            return '<p>' + esc(t) + '</p>';
        }).join('');
    }
    return rendered;
}

function showWeeklyBriefModal() {
    var modal = document.getElementById('weekly-brief-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    generateWeeklyBrief();
}

function closeWeeklyBriefModal() {
    var modal = document.getElementById('weekly-brief-modal');
    if (modal) modal.style.display = 'none';
}

function setWeeklyBriefBusy(busy) {
    var genBtn = document.getElementById('weekly-brief-regenerate-btn');
    var saveBtn = document.getElementById('weekly-brief-save-btn');
    if (genBtn) genBtn.disabled = busy;
    if (saveBtn) saveBtn.disabled = busy;
}

function generateWeeklyBrief() {
    var status = document.getElementById('weekly-brief-status');
    var content = document.getElementById('weekly-brief-content');
    var saveBtn = document.getElementById('weekly-brief-save-btn');
    if (!status || !content) return;
    status.hidden = false;
    content.hidden = true;
    status.textContent = window.t('weeklyBrief.generating');
    setWeeklyBriefBusy(true);
    if (saveBtn) saveBtn.dataset.path = '';
    if (!window.api || !window.api.generateWeeklyBrief) {
        status.textContent = window.t('weeklyBrief.notAvailable');
        setWeeklyBriefBusy(false);
        return;
    }
    window.api.generateWeeklyBrief({ days: 7 }).then(function(result) {
        setWeeklyBriefBusy(false);
        if (!result || !result.success) {
            status.textContent = (result && result.message) || window.t('weeklyBrief.failed');
            return;
        }
        if (result.fallback) {
            status.textContent = window.t('weeklyBrief.fallbackHint');
            status.hidden = false;
        } else {
            status.hidden = true;
        }
        content.innerHTML = renderMarkdown(result.brief || '');
        content.dataset.markdown = result.brief || '';
        content.hidden = false;
        if (saveBtn) saveBtn.dataset.path = '';
    }).catch(function(err) {
        setWeeklyBriefBusy(false);
        status.textContent = (err && err.message) || window.t('weeklyBrief.failed');
    });
}

function saveWeeklyBriefAsNote() {
    var content = document.getElementById('weekly-brief-content');
    var status = document.getElementById('weekly-brief-status');
    var saveBtn = document.getElementById('weekly-brief-save-btn');
    if (!content || !saveBtn || saveBtn.dataset.saving) return;
    var brief = (content.dataset && content.dataset.markdown) || '';
    if (!brief.trim()) return;
    saveBtn.dataset.saving = '1';
    saveBtn.disabled = true;
    var title = '知识库周报 ' + new Date().toISOString().slice(0, 10);
    window.api.createNoteFromDraft(title, '知识库周报', brief).then(function(result) {
        delete saveBtn.dataset.saving;
        saveBtn.disabled = false;
        if (!result || !result.success) {
            if (status) { status.hidden = false; status.textContent = (result && result.message) || window.t('weeklyBrief.saveFailed'); }
            return;
        }
        if (window.ToastModule) window.ToastModule.success(window.t('weeklyBrief.saved', { path: result.path || '' }));
        closeWeeklyBriefModal();
        scheduleRefresh();
    }).catch(function(err) {
        delete saveBtn.dataset.saving;
        saveBtn.disabled = false;
        if (status) { status.hidden = false; status.textContent = (err && err.message) || window.t('weeklyBrief.saveFailed'); }
    });
}

function init() {
    var refreshBtn = document.getElementById('home-refresh-btn');
    if (refreshBtn && !refreshBtn.dataset.bound) {
        refreshBtn.dataset.bound = '1';
        refreshBtn.addEventListener('click', refresh);
    }
    var startBtn = document.getElementById('home-start-ingest-btn');
    if (startBtn && !startBtn.dataset.bound) {
        startBtn.dataset.bound = '1';
        startBtn.addEventListener('click', checkUpdates);
    }
    var actionBtn = document.getElementById('home-command-action-btn');
    if (actionBtn && !actionBtn.dataset.bound) {
        actionBtn.dataset.bound = '1';
        actionBtn.addEventListener('click', runRecommendedAction);
    }
    var weeklyBtn = document.getElementById('home-weekly-brief-btn');
    if (weeklyBtn && !weeklyBtn.dataset.bound) {
        weeklyBtn.dataset.bound = '1';
        weeklyBtn.addEventListener('click', showWeeklyBriefModal);
    }
    var regenerateBtn = document.getElementById('weekly-brief-regenerate-btn');
    if (regenerateBtn && !regenerateBtn.dataset.bound) {
        regenerateBtn.dataset.bound = '1';
        regenerateBtn.addEventListener('click', generateWeeklyBrief);
    }
    var saveBtn = document.getElementById('weekly-brief-save-btn');
    if (saveBtn && !saveBtn.dataset.bound) {
        saveBtn.dataset.bound = '1';
        saveBtn.addEventListener('click', saveWeeklyBriefAsNote);
    }
    var weeklyModal = document.getElementById('weekly-brief-modal');
    if (weeklyModal && !weeklyModal.dataset.bound) {
        weeklyModal.dataset.bound = '1';
        weeklyModal.addEventListener('click', function(e) { if (e.target === weeklyModal) closeWeeklyBriefModal(); });
    }
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeWeeklyBriefModal();
    });
    document.addEventListener('noteai_jobs_changed', scheduleRefresh);
    document.addEventListener('localechange', scheduleRefresh);
    refresh();
}

window.HomeDashboardModule = {
    init: init,
    refresh: refresh,
    show: show,
    checkUpdates: checkUpdates,
    runRecommendedAction: runRecommendedAction,
    deriveRecommendation: deriveRecommendation,
    countFiles: countFiles,
    countTopics: countTopics,
    openSemanticChanges: openSemanticChanges,
    generateWeeklyBrief: generateWeeklyBrief,
    saveWeeklyBriefAsNote: saveWeeklyBriefAsNote,
    showWeeklyBriefModal: showWeeklyBriefModal,
    close: closeWeeklyBriefModal
};

})();
