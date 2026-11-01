/**
 * Local job-form draft (J077).
 * Autosaves non-sensitive fields to localStorage for 7 days. Coordinates,
 * CSRF tokens, files and passwords are never stored.
 */
(function () {
    'use strict';

    var KEY = 'trudnik-job-draft-v1';
    try {
        if (new URLSearchParams(window.location.search).get('created') === '1') {
            localStorage.removeItem(KEY);
        }
    } catch (e) {}
    var form = document.querySelector('form[data-job-draft="1"]');
    if (!form) return;

    var TTL = 7 * 24 * 60 * 60 * 1000;
    var banner = document.getElementById('job-draft-banner');
    var meta = document.getElementById('job-draft-meta');
    var restoreBtn = document.getElementById('job-draft-restore');
    var discardBtn = document.getElementById('job-draft-discard');
    var timer = null;

    function storageGet() {
        try {
            var raw = localStorage.getItem(KEY);
            if (!raw) return null;
            var draft = JSON.parse(raw);
            if (!draft || !draft.saved_at || !draft.fields) return null;
            if (Date.now() - draft.saved_at > TTL) {
                localStorage.removeItem(KEY);
                return null;
            }
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

    function collect() {
        var fields = {};
        var hasValue = false;
        Array.prototype.forEach.call(form.elements, function (el) {
            if (isExcluded(el)) return;
            if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
            var value = el.value == null ? '' : String(el.value);
            if (!fields[el.name]) fields[el.name] = [];
            fields[el.name].push(value);
            if (value.trim()) hasValue = true;
        });
        return hasValue ? { saved_at: Date.now(), fields: fields } : null;
    }

    var touched = false;

    function saveNow() {
        if (!touched) return;
        var draft = collect();
        if (draft) storageSet(draft);
        else storageRemove();
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
    if (draft) showBanner(draft);

    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);
    window.addEventListener('pagehide', saveNow);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') saveNow();
    });

    if (restoreBtn) {
        restoreBtn.addEventListener('click', function () {
            var current = storageGet();
            if (current) applyDraft(current);
        });
    }
    if (discardBtn) {
        discardBtn.addEventListener('click', function () {
            storageRemove();
            if (banner) banner.classList.add('hidden');
        });
    }
})();
