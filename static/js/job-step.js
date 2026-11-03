/**
 * Progressive job-form stepper (J082).
 * Without JS the original single form is untouched. With JS the existing
 * fields are grouped into three steps; server validation and local draft stay.
 */
(function () {
    'use strict';

    var T = window.TRUDNIK_I18N || {};
    var form = document.querySelector('form[data-job-draft="1"]');
    if (!form) return;

    var groups = {
        1: ['work_type', 'organization_name', 'org_description', 'object_description', 'detailed_description'],
        2: ['payment_amount', 'max_workers', 'date_time'],
        3: ['is_remote', 'address', 'city']
    };
    var titles = { 1: T.step_desc || 'Описание', 2: T.step_pay || 'Оплата и срок', 3: T.step_address || 'Адрес и карта' };

    function nodeFor(name) {
        var el = form.querySelector('[name="' + name + '"]');
        if (!el) return null;
        return el.closest('.form-field') || el;
    }

    function makePanel(step) {
        var panel = document.createElement('section');
        panel.setAttribute('data-job-step-panel', String(step));
        panel.className = 'space-y-3';
        var heading = document.createElement('h3');
        heading.className = 'text-sm font-semibold text-neutral-800';
        heading.textContent = (T.step_word || 'Шаг') + ' ' + step + '. ' + titles[step];
        panel.appendChild(heading);
        return panel;
    }

    var panels = { 1: makePanel(1), 2: makePanel(2), 3: makePanel(3) };
    var submit = form.querySelector('button[type="submit"]');
    var footer = submit ? submit.parentNode : null;

    // Move existing field wrappers into panels without touching their inputs/errors.
    groups[1].forEach(function (name) {
        var node = nodeFor(name);
        if (node) panels[1].appendChild(node);
    });
    var skills = form.querySelector('fieldset');
    if (skills) panels[1].appendChild(skills);
    groups[2].forEach(function (name) {
        var node = nodeFor(name);
        if (node) panels[2].appendChild(node);
    });
    groups[3].forEach(function (name) {
        var node = nodeFor(name);
        if (node) panels[3].appendChild(node);
    });
    var map = document.getElementById('job-map');
    if (map) {
        var mapField = map.closest('.form-field');
        if (mapField) panels[3].appendChild(mapField);
    }
    ['lat', 'lng'].forEach(function (name) {
        var input = form.querySelector('[name="' + name + '"]');
        if (!input) return;
        // Hidden fields render their errors as following .form-error siblings.
        var errors = [];
        var sibling = input.nextElementSibling;
        while (sibling && sibling.classList.contains('form-error')) {
            errors.push(sibling);
            sibling = sibling.nextElementSibling;
        }
        panels[3].appendChild(input);
        errors.forEach(function (error) { panels[3].appendChild(error); });
    });
    if (footer) panels[3].appendChild(footer);

    function addNavButton(parent, step, label) {
        var button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        button.className = 'px-3 h-9 rounded-xl border border-neutral-200 bg-white text-sm font-medium text-neutral-600';
        button.addEventListener('click', function () { show(step); });
        parent.appendChild(button);
        return button;
    }

    var progress = document.createElement('nav');
    progress.className = 'hidden sm:flex flex-wrap gap-2 mb-4';
    progress.setAttribute('aria-label', T.form_steps || 'Шаги формы');
    var navButtons = {};
    [1, 2, 3].forEach(function (step) {
        navButtons[step] = addNavButton(progress, step, step + '. ' + titles[step]);
    });

    var navBox = document.createElement('div');
    navBox.className = 'flex gap-2 pt-2';
    if (footer) navBox.className = 'flex flex-wrap gap-2 pt-2';
    var back = null;
    var next = null;
    var step = 1;

    function show(nextStep) {
        step = nextStep;
        [1, 2, 3].forEach(function (n) {
            panels[n].hidden = n !== step;
            if (navButtons[n]) {
                navButtons[n].className = 'px-3 h-9 rounded-xl border text-sm font-medium ' +
                    (n === step
                        ? 'border-primary-500 bg-primary-500 text-white'
                        : 'border-neutral-200 bg-white text-neutral-600');
                if (n === step) navButtons[n].setAttribute('aria-current', 'step');
                else navButtons[n].removeAttribute('aria-current');
            }
        });
        if (navBox.parentNode) navBox.parentNode.removeChild(navBox);
        panels[step].appendChild(navBox);
        if (back) back.hidden = step === 1;
        if (next) next.hidden = step === 3;
        if (step === 3 && window.__trudnikJobMap && window.__trudnikJobMap.container) {
            window.setTimeout(function () { window.__trudnikJobMap.container.fitToViewport(); }, 0);
        }
        if (step < 3) panels[step].scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    back = document.createElement('button');
    back.type = 'button';
    back.textContent = T.back || '← Назад';
    back.className = 'px-4 h-10 rounded-xl border border-neutral-200 bg-white text-sm font-medium text-neutral-700';
    back.addEventListener('click', function () { show(Math.max(1, step - 1)); });
    navBox.appendChild(back);

    next = document.createElement('button');
    next.type = 'button';
    next.textContent = T.next || 'Далее →';
    next.className = 'px-4 h-10 rounded-xl bg-primary-500 hover:bg-primary-600 text-white text-sm font-semibold';
    next.addEventListener('click', function () {
        var invalid = null;
        panels[step].querySelectorAll('input, select, textarea').forEach(function (el) {
            if (el.type === 'hidden' || el.disabled) return;
            if (!el.checkValidity()) {
                invalid = el;
            }
        });
        if (invalid) {
            invalid.reportValidity();
            invalid.focus();
            return;
        }
        show(Math.min(3, step + 1));
    });
    navBox.appendChild(next);

    form.insertBefore(progress, form.firstChild);
    panels[1].hidden = false;
    panels[2].hidden = true;
    panels[3].hidden = true;
    form.appendChild(panels[1]);
    form.appendChild(panels[2]);
    form.appendChild(panels[3]);
    progress.classList.remove('hidden');

    var error = form.querySelector('.form-error');
    if (error) {
        var panel = error.closest('[data-job-step-panel]');
        show(panel ? Number(panel.getAttribute('data-job-step-panel')) : 1);
    } else {
        show(1);
    }
})();
