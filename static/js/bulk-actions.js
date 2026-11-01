/**
 * Bulk selection UI (J080): select-all, count, disabled actions, confirm.
 * Works for jobs and received applications, one root per page.
 */
(function () {
    'use strict';

    document.querySelectorAll('[data-bulk-root]').forEach(function (root) {
        var formId = root.getAttribute('data-bulk-form');
        if (!formId) return;
        var all = root.querySelector('[data-bulk-all]');
        var count = root.querySelector('[data-bulk-count]');
        var actions = root.querySelectorAll('[data-bulk-action]');
        var boxes = document.querySelectorAll('[data-bulk-item][form="' + formId + '"]');

        function selected() {
            return Array.prototype.filter.call(boxes, function (box) { return box.checked; });
        }

        function refresh() {
            var chosen = selected().length;
            if (count) count.textContent = 'Выбрано: ' + chosen;
            actions.forEach(function (btn) {
                var requires = btn.getAttribute('data-bulk-requires');
                var applicable = chosen;
                if (requires) {
                    var allowed = requires.split(',');
                    applicable = selected().filter(function (box) {
                        return allowed.indexOf(box.getAttribute('data-job-status')) >= 0;
                    }).length;
                }
                var off = applicable === 0;
                btn.disabled = off;
                btn.classList.toggle('opacity-50', off);
                btn.classList.toggle('pointer-events-none', off);
            });
            if (all) {
                all.checked = chosen > 0 && chosen === boxes.length;
                all.indeterminate = chosen > 0 && chosen < boxes.length;
            }
        }

        boxes.forEach(function (box) {
            box.addEventListener('change', refresh);
        });

        if (all) {
            all.addEventListener('change', function () {
                boxes.forEach(function (box) { box.checked = all.checked; });
                refresh();
            });
        }

        actions.forEach(function (btn) {
            btn.addEventListener('click', function (event) {
                if (btn.disabled) {
                    event.preventDefault();
                    return;
                }
                var message = btn.getAttribute('data-confirm');
                if (message && !window.confirm(message)) {
                    event.preventDefault();
                }
            });
        });

        refresh();
    });
})();
