(function() { 'use strict';

var _jobs: any[] = [];
var _byId: Record<string, any> = {};

function _sortJobs(jobs: any) {
    return (jobs || []).slice().sort(function(a: any, b: any) {
        return (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0);
    });
}

function _remember(job: any) {
    if (!job || !job.id) return;
    _byId[job.id] = job;
    _jobs = _sortJobs(Object.keys(_byId).map(function(id: any) { return _byId[id]; })).slice(0, 100);
}

async function refresh(options: any) {
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

function getJobs(options?: any) {
    var opts = options || {};
    var jobs = _jobs;
    if (opts.include_finished === false) {
        jobs = jobs.filter(function(job: any) { return job.status === 'running'; });
    }
    if (opts.kind) {
        jobs = jobs.filter(function(job: any) { return job.kind === opts.kind; });
    }
    return jobs.slice(0, opts.limit || jobs.length);
}

function getJob(id: any) {
    return _byId[id] || null;
}

function handleJobUpdate(job: any) {
    _remember(job);
    document.dispatchEvent(new CustomEvent('noteai_jobs_changed', { detail: { jobs: getJobs() } }));
}

function replaceJobs(jobs: any) {
    _byId = {};
    _jobs = [];
    (jobs || []).forEach(_remember);
    return _jobs;
}

document.addEventListener('job_update', function(e: any) {
    handleJobUpdate(e.detail || {});
});

window.JobCenterModule = {
    refresh: refresh,
    getJobs: getJobs,
    getJob: getJob,
    handleJobUpdate: handleJobUpdate,
    replaceJobs: replaceJobs
};

})();
