"""Middleware Flask: CSRF, CSP, Security Headers, Request ID, Cache-Control."""

import hmac
import json
import logging
import secrets
import uuid as _uuid

from flask import g, session, request, abort, Response, current_app

from app.utils import redis_client as _redis_module

logger = logging.getLogger(__name__)


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
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    # В режиме тестирования CSRF отключён
    if current_app.config.get('TESTING'):
        return
    # Emergency API endpoints protected by X-Admin-Token instead of CSRF
    if request.path in ('/api/reset-users', '/api/fix-permissions', '/api/reset-circuit-breaker'):
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
    except Exception as e:
        current_app.logger.warning('Failed to get CSRF token from form: %s', e, exc_info=True)
    # Если не в форме — пробуем JSON (для API-запросов с application/json)
    if not token and request.is_json:
        try:
            json_data = request.get_json(silent=True) or {}
            token = json_data.get('csrf_token') or json_data.get('_csrf_token')
        except Exception as e:
            current_app.logger.warning('Failed to get CSRF token from JSON: %s', e, exc_info=True)
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


def check_idempotency():
    """
    Middleware для идемпотентности (правило R2).
    Проверяет X-Client-Request-Id для POST/PUT/PATCH/DELETE запросов.
    При повторном запросе с тем же ID — возвращает кэшированный ответ.
    """
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    
    client_request_id = request.headers.get('X-Client-Request-Id')
    if not client_request_id:
        return None  # Не все запросы имеют этот заголовок
    
    # Валидируем формат UUID
    try:
        _uuid.UUID(client_request_id)
    except ValueError:
        return None  # Игнорируем невалидные ID
    
    user_id = session.get('user_id')
    if not user_id:
        return None  # Только для авторизованных пользователей
    
    cache_key = f'idempotency:{user_id}:{client_request_id}'
    
    try:
        r = _redis_module.get_redis_client()
        if r is None:
            return None
        
        cached = r.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.info('idempotency cache hit: %s', cache_key)
            return Response(
                data['body'],
                status=data['status'],
                headers={
                    'Content-Type': data.get('content_type', 'application/json'),
                    'X-Idempotency-Replayed': 'true'
                }
            )
    except Exception as e:
        logger.warning('idempotency check failed: %s', e, exc_info=True)
    
    return None


def cache_idempotency_response(response):
    """
    After-request hook: кэширует ответ для идемпотентности.
    """
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return response
    
    client_request_id = request.headers.get('X-Client-Request-Id')
    if not client_request_id:
        return response
    
    user_id = session.get('user_id')
    if not user_id:
        return response
    
    # Кэшируем только успешные JSON-ответы (2xx + application/json)
    # HTML-ответы не кэшируем — они могут содержать CSRF-токены
    if not (200 <= response.status_code < 300):
        return response
    if response.content_type and not response.content_type.startswith('application/json'):
        return response
    
    cache_key = f'idempotency:{user_id}:{client_request_id}'
    
    try:
        r = _redis_module.get_redis_client()
        if r is None:
            return response
        
        data = json.dumps({
            'body': response.get_data(as_text=True),
            'status': response.status_code,
            'content_type': response.content_type,
        })
        r.setex(cache_key, 86400, data)  # TTL 24h
    except Exception as e:
        logger.warning('idempotency cache store failed: %s', e, exc_info=True)
    
    return response


def register_middleware(app):
    """Зарегистрировать все middleware-функции на Flask-приложении.

    Args:
        app: экземпляр Flask.
    """
    app.before_request(generate_csp_nonce)
    app.before_request(set_request_id)
    app.before_request(csrf_check)
    app.before_request(check_idempotency)
    app.after_request(add_security_headers)
    app.after_request(cache_idempotency_response)
