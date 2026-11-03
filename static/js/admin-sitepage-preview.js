/**
 * SitePage live preview (J141).
 * Staff-only admin helper: renders the HTML textarea in a sandboxed iframe.
 * Scripts cannot execute (sandbox without allow-scripts); the editor stays raw
 * HTML so legal pages/classes are not rewritten by a rich-text library.
 */
(function () {
    'use strict';

    var textarea = document.querySelector('textarea[name="content"]');
    var frame = document.getElementById('sitepage-preview');
    if (!textarea || !frame) return;

    var timer = null;

    function render() {
        var body = (textarea.value || '').trim();
        if (!body) {
            body = '<p style="color:#737373">Содержимое пустое.</p>';
        }
        frame.srcdoc = '<!doctype html><html lang="ru"><head><meta charset="utf-8">' +
            '<base href="/">' +
            '<link rel="stylesheet" href="/static/css/tailwind.min.css">' +
            '<link rel="stylesheet" href="/static/css/app.css">' +
            '<style>body{padding:24px;background:#fff;color:#262626}main{max-width:48rem;margin:0 auto}</style>' +
            '</head><body><main>' + body + '</main></body></html>';
    }

    textarea.addEventListener('input', function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(render, 250);
    });
    render();
})();
