/**
 * PWA usage counters (J134).
 * In standalone mode sends one beacon per local day: app_open on the first ever
 * launch, app_return on later days. The marker lives only in localStorage and
 * contains a date, not a user identifier.
 */
(function () {
    'use strict';

    var standalone = false;
    try {
        standalone = window.matchMedia('(display-mode: standalone)').matches ||
            window.navigator.standalone === true;
    } catch (e) { /* older browsers */ }
    if (!standalone) return;

    function localDay() {
        var d = new Date();
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    var LAST_KEY = 'trudnik-pwa-last-open';
    var SEEN_KEY = 'trudnik-pwa-seen';
    var today = localDay();
    var first;
    try {
        if (localStorage.getItem(LAST_KEY) === today) return;
        first = localStorage.getItem(SEEN_KEY) !== '1';
        localStorage.setItem(LAST_KEY, today);
        localStorage.setItem(SEEN_KEY, '1');
    } catch (e) {
        return; // storage unavailable: skip rather than inflate daily counters
    }

    try {
        var meta = document.querySelector('meta[name="csrf-token"]');
        fetch('/api/analytics/event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': meta ? meta.getAttribute('content') : ''
            },
            body: JSON.stringify({ event: first ? 'app_open' : 'app_return' }),
            keepalive: true
        }).catch(function () {});
    } catch (e) { /* analytics must not break the app */ }
})();
