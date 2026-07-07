(function() { 'use strict';

var _jobs = [];
var _byId = {};

function _sortJobs(jobs) {
    return (jobs || []).slice().sort(function(a, b) {
        return (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0);
    });
}

function _remember(job) {
    if (!job || !job.id) return;
    _byId[job.id] = job;
    _jobs = _sortJobs(Object.keys(_byId).map(function(id) { return _byId[id]; })).slice(0, 100);
}

async function refresh(options) {
    if (!window.api || !window.api.getJobs) return _jobs;
    var opts = options || {};
    var result = await window.api.getJobs({
        include_finished: opts.include_finished !== false,
        limit: opts.limit || 50
    });
    if (result && result.success && Array.isArray(result.jobs)) {
        _byId = {};
        result.jobs.forEach(_remember);
    }
    return _jobs;
}

function getJobs(options) {
    var opts = options || {};
    var jobs = _jobs;
    if (opts.include_finished === false) {
        jobs = jobs.filter(function(job) { return job.status === 'running'; });
    }
    if (opts.kind) {
        jobs = jobs.filter(function(job) { return job.kind === opts.kind; });
    }
    return jobs.slice(0, opts.limit || jobs.length);
}

function getJob(id) {
    return _byId[id] || null;
}

function handleJobUpdate(job) {
    _remember(job);
    document.dispatchEvent(new CustomEvent('noteai_jobs_changed', { detail: { jobs: getJobs() } }));
}

document.addEventListener('job_update', function(e) {
    handleJobUpdate(e.detail || {});
});

window.JobCenterModule = {
    refresh: refresh,
    getJobs: getJobs,
    getJob: getJob,
    handleJobUpdate: handleJobUpdate
};

})();
