"""Middleware Flask: CSRF, CSP, Security Headers, Request ID, Cache-Control."""

import secrets
import uuid as _uuid

from flask import g, session, request, abort


def generate_csp_nonce():
    """Генерация случайного nonce для Content-Security-Policy."""
    g.csp_nonce = secrets.token_hex(24)


def set_request_id():
    """Установить X-Request-ID в g для трассировки запросов."""
    g.request_id = request.headers.get('X-Request-ID') or str(_uuid.uuid4())


def csrf_check():
    """Глобальная CSRF-защита: проверка токена для всех мутирующих запросов.

    Пропускаем: GET/HEAD/OPTIONS, тестовые запросы, auth-роуты.
    Приоритет: 1) X-CSRF-Token заголовок (fetch/AJAX), 2) csrf_token в форме/JSON.
    """
    from flask import current_app

    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    # В режиме тестирования CSRF отключён
    if current_app.config.get('TESTING'):
        return
    # Emergency API endpoints protected by X-Admin-Token instead of CSRF
    if request.path in ('/api/reset-users', '/api/fix-permissions', '/api/reset-circuit-breaker'):
        import hmac
        expected = current_app.config.get('ADMIN_API_TOKEN', '')
        # X12: fail-closed — если токен не настроен, блокируем доступ
        if not expected:
            abort(503)
        admin_token = request.headers.get('X-Admin-Token', '')
        if not hmac.compare_digest(admin_token, expected):
            abort(403)
        return
    # Проверяем заголовок X-CSRF-Token (для fetch/AJAX-запросов)
    header_token = request.headers.get('X-CSRF-Token')
    if header_token:
        if header_token != session.get('_csrf_token'):
            abort(400, description='CSRF-токен недействителен')
        return
    # Для обычных форм (устойчиво к не-form Content-Type, например text/plain)
    token = None
    try:
        token = request.form.get('csrf_token') or request.form.get('_csrf_token')
    except Exception:
        pass
    # Если не в форме — пробуем JSON (для API-запросов с application/json)
    if not token and request.is_json:
        try:
            json_data = request.get_json(silent=True) or {}
            token = json_data.get('csrf_token') or json_data.get('_csrf_token')
        except Exception:
            pass
    if not token or token != session.get('_csrf_token'):
        abort(400, description='CSRF-токен отсутствует или недействителен')


def add_security_headers(response):
    """Добавить HTTP Security Headers для защиты от XSS, clickjacking, MIME sniffing."""
    nonce = getattr(g, 'csp_nonce', '')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https://cdn.jsdelivr.net https://api-maps.yandex.ru https://yastatic.net; "
        f"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"img-src 'self' data: https:; "
        f"connect-src 'self' https://*.yandex.ru https://core-renderer-tiles.maps.yandex.net https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru https://fonts.googleapis.com https://fonts.gstatic.com ws://localhost:* wss://*; "
        f"worker-src 'self' blob:; "
        f"frame-src 'self'"
    )
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=self'
    # Cache-Control: статические ассеты кешируем на 24 часа, динамику — не кешируем
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    else:
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'Cookie'

    # Устанавливаем CSRF-токен в cookie для Service Worker
    if hasattr(g, 'csp_nonce') and '_csrf_token' in session:
        response.set_cookie(
            'csrf_token',
            session['_csrf_token'],
            httponly=False,  # JS должен читать
            samesite='Lax',
            secure=request.is_secure
        )

    # X-Request-ID в ответе
    request_id = getattr(g, 'request_id', None)
    if request_id:
        response.headers['X-Request-ID'] = request_id

    return response


def register_middleware(app):
    """Зарегистрировать все middleware-функции на Flask-приложении.

    Args:
        app: экземпляр Flask.
    """
    app.before_request(generate_csp_nonce)
    app.before_request(set_request_id)
    app.before_request(csrf_check)
    app.after_request(add_security_headers)
