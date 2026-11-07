/**
 * Local job-form draft (J077).
 * Autosaves non-sensitive fields to localStorage for 7 days. Coordinates,
 * CSRF tokens, files and passwords are never stored.
 */
(function () {
    'use strict';

    // UMD: в Node экспортируем чистые функции для unit-тестов, в браузере
    // продолжаем обычную инициализацию (function declarations хойстятся).
    if (typeof module === 'object' && module.exports) {
        module.exports = {
            isExcluded: isExcluded,
            collectElements: collectElements,
            parseDraft: parseDraft
        };
        return;
    }

    var KEY = 'trudnik-job-draft-v1';
    var created = false;
    try {
        created = new URLSearchParams(window.location.search).get('created') === '1';
        if (created) localStorage.removeItem(KEY);
    } catch (e) {}
    var form = document.querySelector('form[data-job-draft="1"]');
    if (!form) {
        if (created) serverClear();
        return;
    }

    var TTL = 7 * 24 * 60 * 60 * 1000;
    var banner = document.getElementById('job-draft-banner');
    var meta = document.getElementById('job-draft-meta');
    var restoreBtn = document.getElementById('job-draft-restore');
    var discardBtn = document.getElementById('job-draft-discard');
    var timer = null;
    var serverTimer = null;
    var pendingDraft = null;

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function serverClear() {
        try {
            fetch('/api/jobs/draft', {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrfToken() },
                keepalive: true
            }).catch(function () {});
        } catch (e) {}
    }

    function serverSave(draft, keepalive) {
        try {
            fetch('/api/jobs/draft', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken()
                },
                body: JSON.stringify(draft),
                keepalive: !!keepalive
            }).catch(function () {});
        } catch (e) {}
    }

    function serverGet() {
        return fetch('/api/jobs/draft', {
            headers: { 'Accept': 'application/json' }
        }).then(function (response) {
            if (!response.ok) return null;
            return response.json();
        }).then(function (data) {
            return data && data.draft ? data.draft : null;
        }).catch(function () { return null; });
    }

    function queueServerSave() {
        clearTimeout(serverTimer);
        serverTimer = setTimeout(function () {
            var current = storageGet();
            if (current) serverSave(current, false);
        }, 5000);
    }

    function parseDraft(raw, now, ttl) {
        if (!raw) return null;
        try {
            var draft = JSON.parse(raw);
            if (!draft || !draft.saved_at || !draft.fields) return null;
            if (now - draft.saved_at > ttl) return null;
            return draft;
        } catch (e) {
            return null;
        }
    }

    function storageGet() {
        try {
            var raw = localStorage.getItem(KEY);
            if (!raw) return null;
            var draft = parseDraft(raw, Date.now(), TTL);
            if (!draft) localStorage.removeItem(KEY);
            return draft;
        } catch (e) {
            return null;
        }
    }

    function storageSet(value) {
        try { localStorage.setItem(KEY, JSON.stringify(value)); } catch (e) {}
    }

    function storageRemove() {
        try { localStorage.removeItem(KEY); } catch (e) {}
    }

    function isExcluded(el) {
        if (!el.name) return true;
        if (el.name === 'csrfmiddlewaretoken' || el.name === 'lat' || el.name === 'lng') return true;
        if (el.type === 'file' || el.type === 'password' || el.type === 'submit' || el.type === 'button') return true;
        return false;
    }

    function collectElements(elements) {
        var fields = {};
        var hasValue = false;
        Array.prototype.forEach.call(elements, function (el) {
            if (isExcluded(el)) return;
            if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
            var value = el.value == null ? '' : String(el.value);
            if (!fields[el.name]) fields[el.name] = [];
            fields[el.name].push(value);
            if (value.trim()) hasValue = true;
        });
        return hasValue ? { saved_at: Date.now(), fields: fields } : null;
    }

    function collect() {
        return collectElements(form.elements);
    }

    var touched = false;

    function saveNow() {
        if (!touched) return;
        var draft = collect();
        if (draft) {
            storageSet(draft);
            queueServerSave();
        } else {
            storageRemove();
            serverClear();
        }
    }

    function scheduleSave() {
        touched = true;
        clearTimeout(timer);
        timer = setTimeout(saveNow, 600);
    }

    function elementsByName(name) {
        return Array.prototype.filter.call(form.elements, function (el) {
            return el.name === name;
        });
    }

    function applyDraft(draft) {
        pendingDraft = draft;
        Object.keys(draft.fields).forEach(function (name) {
            var values = draft.fields[name] || [];
            elementsByName(name).forEach(function (el) {
                if (isExcluded(el)) return;
                if (el.type === 'checkbox' || el.type === 'radio') {
                    el.checked = values.indexOf(el.value) >= 0;
                } else {
                    el.value = values.length ? values[0] : '';
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
        touched = false;
        if (banner) banner.classList.add('hidden');
    }

    function showBanner(draft) {
        if (!banner) return;
        if (meta) {
            try {
                meta.textContent = 'Сохранён ' + new Date(draft.saved_at).toLocaleString('ru-RU', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                }) + '. Можно продолжить или удалить.';
            } catch (e) {
                meta.textContent = 'Можно продолжить заполнение или удалить черновик.';
            }
        }
        banner.classList.remove('hidden');
    }

    var draft = storageGet();
    if (draft) {
        pendingDraft = draft;
        showBanner(draft);
    }
    serverGet().then(function (remote) {
        if (!remote || !remote.fields) return;
        if (!draft || Number(remote.saved_at || 0) > Number(draft.saved_at || 0)) {
            pendingDraft = remote;
            storageSet(remote);
            showBanner(remote);
        }
    });

    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);
    window.addEventListener('pagehide', function () {
        saveNow();
        var current = storageGet();
        if (current) serverSave(current, true);
    });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') saveNow();
    });

    if (restoreBtn) {
        restoreBtn.addEventListener('click', function () {
            var current = pendingDraft || storageGet();
            if (current) applyDraft(current);
        });
    }
    if (discardBtn) {
        discardBtn.addEventListener('click', function () {
            storageRemove();
            serverClear();
            if (banner) banner.classList.add('hidden');
        });
    }
})();
