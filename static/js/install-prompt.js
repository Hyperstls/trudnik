/**
 * PWA install prompt (J075).
 * Chromium: uses beforeinstallprompt; iOS Safari: shows Share → Home Screen help.
 * The offer is dismissible for 30 days and never appears in standalone mode.
 */
(function () {
    'use strict';

    var banner = document.getElementById('install-prompt');
    var action = document.getElementById('install-action');
    var dismiss = document.getElementById('install-dismiss');
    var help = document.getElementById('install-help');
    var helpClose = document.getElementById('install-help-close');
    if (!banner || !action || !dismiss) return;

    var KEY = 'trudnik-install-dismissed';
    var INSTALLED_KEY = 'trudnik-install-installed';
    var MONTH = 30 * 24 * 60 * 60 * 1000;
    var deferredPrompt = null;

    function trackInstall() {
        try {
            var meta = document.querySelector('meta[name="csrf-token"]');
            fetch('/api/analytics/event', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': meta ? meta.getAttribute('content') : ''
                },
                body: JSON.stringify({event: 'install'}),
                keepalive: true
            }).catch(function () {});
        } catch (e) { /* analytics must not break install */ }
    }

    if (window.location.pathname.indexOf('/app') === 0) return;

    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches ||
            window.navigator.standalone === true;
    }

    function isDismissed() {
        try {
            if (localStorage.getItem(INSTALLED_KEY) === '1') return true;
            var ts = parseInt(localStorage.getItem(KEY) || '0', 10);
            return ts > 0 && (Date.now() - ts) < MONTH;
        } catch (e) {
            return false;
        }
    }

    function rememberDismiss() {
        try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {}
    }

    function hide() {
        banner.classList.add('hidden');
    }

    function show(label, text) {
        if (isStandalone() || isDismissed()) return;
        document.getElementById('install-title').textContent = 'Трудник под рукой';
        document.getElementById('install-text').textContent = text;
        action.textContent = label;
        banner.classList.remove('hidden');
    }

    function isIOS() {
        var ua = window.navigator.userAgent || '';
        return /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    }

    function openHelp() {
        if (!help) return;
        if (help.showModal) help.showModal();
        else help.setAttribute('open', '');
    }

    function closeHelp() {
        if (!help) return;
        if (help.close) help.close();
        else help.removeAttribute('open');
    }

    dismiss.addEventListener('click', function () {
        rememberDismiss();
        hide();
    });

    action.addEventListener('click', function () {
        if (deferredPrompt) {
            var promptEvent = deferredPrompt;
            deferredPrompt = null;
            promptEvent.prompt();
            promptEvent.userChoice.then(function (choice) {
                if (choice && choice.outcome === 'accepted') hide();
            }).catch(function () {});
            return;
        }
        openHelp();
    });

    if (helpClose) helpClose.addEventListener('click', closeHelp);
    if (help) {
        help.addEventListener('click', function (e) {
            if (e.target === help) closeHelp();
        });
        help.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeHelp();
        });
    }

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        show('Установить', 'Установите приложение — задания и чаты откроются в один клик.');
    });

    window.addEventListener('appinstalled', function () {
        try { localStorage.setItem(INSTALLED_KEY, '1'); } catch (e) {}
        deferredPrompt = null;
        hide();
        trackInstall();
    });

    if (isIOS()) {
        window.setTimeout(function () {
            show('Как установить', 'Добавьте Трудник на экран «Домой» — без адресной строки.');
        }, 1500);
    }
})();
