/**
 * Anonymous job-view counter (J134).
 * Authenticated views are counted server-side once per session/job/day; anonymous
 * visitors get one beacon per browser/day via a localStorage marker (job id + time).
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-job-id]');
    if (!root || document.body.hasAttribute('data-user-id')) return;
    var jobId = root.getAttribute('data-job-id');
    if (!jobId) return;

    var key = 'trudnik-view:' + jobId;
    try {
        var last = parseInt(localStorage.getItem(key) || '0', 10);
        if (last && Date.now() - last < 24 * 60 * 60 * 1000) return;
        localStorage.setItem(key, String(Date.now()));
    } catch (e) {
        return; // storage unavailable: skip rather than inflate counters
    }

    try {
        var meta = document.querySelector('meta[name="csrf-token"]');
        fetch('/api/analytics/event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': meta ? meta.getAttribute('content') : ''
            },
            body: JSON.stringify({ event: 'job_view', job_id: jobId }),
            keepalive: true
        }).catch(function () {});
    } catch (e) { /* analytics must not break the page */ }
})();
