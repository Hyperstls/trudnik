/**
 * form-guard.js — Loading-state protection для форм.
 * Блокирует submit-кнопки на 1.5s после отправки для предотвращения двойных нажатий.
 */
document.addEventListener('submit', function(e) {
    if (e.defaultPrevented) return;
    var form = e.target;
    var btn = form.querySelector('button[type="submit"]');
    if (btn && !btn.disabled) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.pointerEvents = 'none';
        setTimeout(function() {
            btn.disabled = false;
            btn.style.opacity = '';
            btn.style.pointerEvents = '';
        }, 1500);
    }
});
