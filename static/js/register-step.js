/**
 * Progressive registration stepper with a session draft (J114).
 * Without JS all fields stay visible and the noscript submit works.
 * The draft stores only intent and skill ids (no personal data).
 */
(function () {
    var T = window.TRUDNIK_I18N || {};
    'use strict';

    var form = document.querySelector('form[data-register-stepper]');
    if (!form) return;

    var steps = Array.prototype.slice.call(form.querySelectorAll('[data-register-step]'));
    if (steps.length < 2) return;

    var progress = document.getElementById('register-progress');
    var indicators = Array.prototype.slice.call(document.querySelectorAll('[data-register-indicator]'));
    var nav = document.getElementById('register-nav');
    var back = document.getElementById('register-back');
    var next = document.getElementById('register-next');
    var submitWrap = document.getElementById('register-submit-wrap');
    var status = document.getElementById('register-step-status');
    var total = steps.length;
    var current = 1;
    var DRAFT_KEY = 'trudnik-register-draft-v1';
    var DRAFT_TTL = 7 * 24 * 60 * 60 * 1000;

    function stepOf(element) {
        var panel = element.closest('[data-register-step]');
        return panel ? Number(panel.getAttribute('data-register-step')) : 0;
    }

    function setIndicators(step) {
        indicators.forEach(function (item) {
            var number = Number(item.getAttribute('data-register-indicator'));
            item.className = 'rounded-xl border px-2 py-1.5 text-center ' + (number === step
                ? 'border-primary-500 bg-primary-50 font-semibold text-primary-700'
                : 'border-neutral-200 text-neutral-500');
            if (number === step) item.setAttribute('aria-current', 'step');
            else item.removeAttribute('aria-current');
        });
    }

    var captchaTries = 0;

    function renderCaptcha() {
        var container = document.getElementById('register-captcha');
        if (!container || container.dataset.rendered) return;
        if (!window.smartCaptcha) {
            if (captchaTries < 20) {
                captchaTries += 1;
                window.setTimeout(renderCaptcha, 300);
            }
            return;
        }
        window.smartCaptcha.render(container, { sitekey: container.getAttribute('data-sitekey') });
        container.dataset.rendered = '1';
    }

    function show(step, focus) {
        current = Math.min(total, Math.max(1, step));
        steps.forEach(function (panel) {
            panel.hidden = Number(panel.getAttribute('data-register-step')) !== current;
        });
        if (progress) progress.classList.remove('hidden');
        if (nav) nav.classList.remove('hidden');
        if (back) back.classList.toggle('hidden', current === 1);
        if (next) next.classList.toggle('hidden', current === total);
        if (submitWrap) submitWrap.classList.toggle('hidden', current !== total);
        setIndicators(current);
        if (status) status.textContent = (T.step_word || 'Шаг') + ' ' + current + ' ' + (T.of || 'из') + ' ' + total;
        if (current === total) renderCaptcha();
        if (!focus) return;
        var first = steps[current - 1].querySelector('input:not([type="hidden"]), select, textarea');
        if (first) first.focus({ preventScroll: true });
        var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        steps[current - 1].scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
    }

    function valid(panel) {
        var fields = panel.querySelectorAll('input, select, textarea');
        for (var i = 0; i < fields.length; i += 1) {
            var field = fields[i];
            if (field.type === 'hidden' || field.disabled) continue;
            if (!field.checkValidity()) {
                field.reportValidity();
                field.focus();
                return false;
            }
        }
        return true;
    }

    if (next) {
        next.addEventListener('click', function () {
            if (valid(steps[current - 1])) show(current + 1, true);
        });
    }
    if (back) {
        back.addEventListener('click', function () { show(current - 1, true); });
    }
    form.addEventListener('submit', function (event) {
        if (form.checkValidity()) return;
        event.preventDefault();
        var invalid = form.querySelector(':invalid');
        if (!invalid) return;
        var panel = stepOf(invalid);
        if (panel) show(panel, false);
        invalid.reportValidity();
        invalid.focus();
    });

    function saveDraft() {
        try {
            var intent = form.querySelector('input[name="intent"]:checked');
            var skills = Array.prototype.map.call(
                form.querySelectorAll('input[name="skills"]:checked'),
                function (item) { return item.value; }
            );
            sessionStorage.setItem(DRAFT_KEY, JSON.stringify({
                intent: intent ? intent.value : null,
                skills: skills,
                savedAt: Date.now()
            }));
        } catch (error) { /* private mode / storage disabled */ }
    }

    function restoreDraft() {
        // Server-rendered values (after a validation error) win over the draft.
        if (form.querySelector('.form-error')) return;
        try {
            var raw = sessionStorage.getItem(DRAFT_KEY);
            if (!raw) return;
            var draft = JSON.parse(raw);
            if (!draft || !draft.savedAt || Date.now() - draft.savedAt > DRAFT_TTL) return;
            if (draft.intent) {
                var radio = form.querySelector('input[name="intent"][value="' + draft.intent + '"]');
                if (radio) radio.checked = true;
            }
            if (draft.skills && draft.skills.length) {
                form.querySelectorAll('input[name="skills"]').forEach(function (item) {
                    item.checked = draft.skills.indexOf(item.value) !== -1;
                });
            }
        } catch (error) { /* ignore broken draft */ }
    }

    form.addEventListener('change', function (event) {
        if (event.target && (event.target.name === 'intent' || event.target.name === 'skills')) {
            saveDraft();
        }
    });

    restoreDraft();
    var firstError = form.querySelector('.form-error');
    show(firstError ? (stepOf(firstError) || 1) : 1, false);
})();
