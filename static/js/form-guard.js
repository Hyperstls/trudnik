/**
 * form-guard.js — защита форм от двойной отправки.
 * После submit отключает все submit-кнопки формы (без таймера повторного
 * включения); учитывает e.submitter и e.defaultPrevented; сбрасывает
 * состояние кнопок при возврате страницы из bfcache (pageshow).
 */
(function () {
    'use strict';

    function resetBusyButtons() {
        var buttons = document.querySelectorAll('button[type="submit"][data-busy="1"]');
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            btn.disabled = false;
            btn.removeAttribute('aria-disabled');
            btn.removeAttribute('data-busy');
            btn.style.opacity = '';
            btn.style.cursor = '';
        }
    }

    document.addEventListener('submit', function (e) {
        if (e.defaultPrevented) return;
        var form = e.target;
        if (!form || !form.querySelectorAll) return;
        var submitter = e.submitter || form.querySelector('button[type="submit"]:not([disabled])');
        if (!submitter) return;
        setTimeout(function () {
            if (e.defaultPrevented) return;
            var buttons = form.querySelectorAll('button[type="submit"]');
            for (var i = 0; i < buttons.length; i++) {
                var btn = buttons[i];
                btn.disabled = true;
                btn.setAttribute('aria-disabled', 'true');
                btn.setAttribute('data-busy', '1');
                btn.style.opacity = '0.6';
                btn.style.cursor = 'not-allowed';
            }
        }, 0);
    });

    window.addEventListener('pageshow', function () {
        resetBusyButtons();
    });
})();
