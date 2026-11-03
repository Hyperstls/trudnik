/**
 * Light/dark theme (J142).
 * The early inline script in base.html applies the saved theme before paint.
 * This controller follows the system preference until the user makes a choice,
 * then persists that choice in localStorage.
 */
(function () {
    'use strict';

    var KEY = 'trudnik-theme';
    var root = document.documentElement;
    var media = window.matchMedia('(prefers-color-scheme: dark)');

    function stored() {
        try {
            var value = localStorage.getItem(KEY);
            return value === 'dark' || value === 'light' ? value : null;
        } catch (e) {
            return null;
        }
    }

    function current() {
        return stored() || (media.matches ? 'dark' : 'light');
    }

    function apply(theme, persist) {
        root.setAttribute('data-theme', theme);
        if (persist) {
            try { localStorage.setItem(KEY, theme); } catch (e) { /* private mode */ }
        }

        var dark = theme === 'dark';
        var toggle = document.getElementById('theme-toggle');
        if (toggle) {
            var label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
            toggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
            toggle.setAttribute('aria-label', label);
            toggle.setAttribute('title', label);
            var sun = toggle.querySelector('[data-theme-sun]');
            var moon = toggle.querySelector('[data-theme-moon]');
            if (sun) sun.classList.toggle('hidden', !dark);
            if (moon) moon.classList.toggle('hidden', dark);
        }

        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute('content', dark ? '#171717' : '#d97706');
    }

    apply(current(), false);

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', function () {
            apply(current() === 'dark' ? 'light' : 'dark', true);
        });
    }

    if (media.addEventListener) {
        media.addEventListener('change', function () {
            if (!stored()) apply(current(), false);
        });
    }
})();
