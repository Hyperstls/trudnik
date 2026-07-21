"""Core blueprint: health checks, static files, PWA, redirects, Prometheus metrics."""

import os
import time as _time_module

from flask import (Blueprint, current_app, abort, redirect, render_template,
                   send_from_directory, url_for, jsonify, session, request)

from app.decorators import login_required

core_bp = Blueprint('core', __name__)

_app_start_time = _time_module.time()

# ═══════════════════════════════════════════════════════════
# Prometheus metrics (Задача 10-2)
# ═══════════════════════════════════════════════════════════
from prometheus_client import (generate_latest, CollectorRegistry,
                               Counter, Histogram, Gauge, CONTENT_TYPE_LATEST)

_registry = CollectorRegistry()
_http_requests = Counter(
    'trudnik_http_requests_total', 'Total HTTP requests',
    ['method', 'endpoint', 'status'], registry=_registry)
_postgrest_duration = Histogram(
    'trudnik_postgrest_request_duration_seconds',
    'PostgREST request duration', registry=_registry)
_circuit_breaker = Gauge(
    'trudnik_circuit_breaker_state',
    'Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)',
    ['name'], registry=_registry)
_outbox_pending = Gauge(
    'trudnik_notification_outbox_pending',
    'Pending notifications in outbox', registry=_registry)
_ws_connections = Gauge(
    'trudnik_active_websocket_connections',
    'Active WebSocket connections', registry=_registry)


@core_bp.route('/metrics')
def metrics():
    """Prometheus metrics endpoint (Задача 10-2)."""
    from app.utils.postgrest_client import get_circuit_breaker_state

    # Circuit breaker gauges
    cb = get_circuit_breaker_state()
    state_map = {'CLOSED': 0, 'HALF_OPEN': 1, 'OPEN': 2}
    for name, data in cb.items():
        _circuit_breaker.labels(name=name).set(
            state_map.get(data.get('state', 'CLOSED'), 0))

    # Outbox pending
    try:
        from app.utils import postgrest_admin_request
        resp = postgrest_admin_request(
            'GET', 'notification_outbox?status=eq.pending&select=id')
        if resp.ok:
            outbox_data = resp.json()
            if isinstance(outbox_data, list):
                _outbox_pending.set(len(outbox_data))
    except Exception as e:
        current_app.logger.warning('metrics outbox check failed: %s', e, exc_info=True)

    # WebSocket connections (cached in Redis, or 0)
    try:
        from app.utils.redis_client import redis_client
        conns = redis_client.get('trudnik:ws:active_connections')
        _ws_connections.set(int(conns) if conns else 0)
    except Exception as e:
        current_app.logger.warning('metrics ws connections check failed: %s', e, exc_info=True)
        _ws_connections.set(0)

    return generate_latest(_registry), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@core_bp.route('/health')
def health_check():
    """Проверка работоспособности приложения."""
    from app.utils import postgrest_admin_request
    from app.utils.postgrest_client import get_circuit_breaker_state
    from app.utils.redis_client import get_redis_client

    cb_state = get_circuit_breaker_state()

    # Проверяем БД через admin CB
    try:
        resp = postgrest_admin_request('GET', 'profiles?select=id&limit=1')
        db_ok = resp.ok
    except Exception as e:
        current_app.logger.error('Health check DB error: %s', e)
        db_ok = False

    # Проверяем Redis
    try:
        redis_client = get_redis_client()
        redis_ok = redis_client is not None and redis_client.ping()
    except Exception as e:
        current_app.logger.error('Health check Redis error: %s', e)
        redis_ok = False

    # Проверяем состояние CB
    cb_postgrest_open = cb_state['postgrest']['state'] == 'OPEN'
    cb_admin_open = cb_state['admin']['state'] == 'OPEN'

    # Общий статус: ok только если все компоненты работают
    all_ok = db_ok and redis_ok and not cb_postgrest_open and not cb_admin_open

    health_data = {
        'status': 'ok' if all_ok else 'degraded',
        'database': 'ok' if db_ok else 'error',
        'redis': 'ok' if redis_ok else 'error',
        'circuit_breaker': cb_state,
        'version': 'unknown',
        'timestamp': _time_module.strftime('%Y-%m-%dT%H:%M:%SZ', _time_module.gmtime()),
        'uptime_seconds': int(_time_module.time() - _app_start_time),
    }

    return jsonify(health_data), 200


@core_bp.route('/ready')
def ready_check():
    """Readiness check: возвращает 503 если PostgREST или Redis недоступен."""
    from app.config import Config
    import requests as req_lib
    from app.utils.redis_client import get_redis_client

    url = f"{Config.POSTGREST_URL}/profiles?select=id&limit=1"
    try:
        resp = req_lib.get(url, timeout=5)
        if not resp.ok:
            return jsonify({
                'status': 'not ready',
                'reason': f'PostgREST returned {resp.status_code}'
            }), 503
    except req_lib.RequestException as e:
        return jsonify({
            'status': 'not ready',
            'reason': f'PostgREST: {e}'
        }), 503

    # Redis check — без Redis не работают уведомления, self-heal, WS
    try:
        rc = get_redis_client()
        if rc is None or not rc.ping():
            return jsonify({
                'status': 'not ready',
                'reason': 'Redis unavailable'
            }), 503
    except Exception as e:
        return jsonify({
            'status': 'not ready',
            'reason': f'Redis: {e}'
        }), 503

    return jsonify({'status': 'ready'}), 200


@core_bp.route('/health/circuit-breaker')
def circuit_breaker_health():
    """Детальная информация о состоянии Circuit Breaker."""
    from app.utils.postgrest_client import get_circuit_breaker_state
    return jsonify(get_circuit_breaker_state())


@core_bp.route('/health/postgrest')
def postgrest_health():
    """Прямая проверка доступности PostgREST."""
    import time
    import requests as req_lib
    from app.config import Config

    url = f"{Config.POSTGREST_URL}/profiles?select=id&limit=1"
    start = time.time()
    try:
        resp = req_lib.get(url, timeout=5)
        elapsed = round((time.time() - start) * 1000)
        return jsonify({
            'status': 'ok' if resp.ok else 'error',
            'postgrest_url': Config.POSTGREST_URL,
            'http_status': resp.status_code,
            'response_time_ms': elapsed,
            'response_preview': (resp.text or '')[:200],
        }), 200 if resp.ok else 503
    except req_lib.RequestException as e:
        elapsed = round((time.time() - start) * 1000)
        return jsonify({
            'status': 'unreachable',
            'postgrest_url': Config.POSTGREST_URL,
            'error': str(e),
            'response_time_ms': elapsed,
        }), 503


@core_bp.route('/uploads/avatars/<path:filename>')
def uploaded_avatar(filename):
    """Аватары — публичные."""
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    response = send_from_directory(os.path.join(upload_folder, 'avatars'), filename)
    response.headers['Cache-Control'] = 'public, max-age=86400'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@core_bp.route('/uploads/verification-docs/<path:filename>')
@login_required
def uploaded_verification_doc(filename):
    """Документы верификации — только админ или владелец."""
    parts = filename.split('/')
    # Формат: verification/<user_id>/<file>.pdf
    if len(parts) < 3 or parts[0] != 'verification' or parts[1] != session.get('user_id', ''):
        if session.get('role') != 'admin':
            abort(403)
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    response = send_from_directory(
        os.path.join(upload_folder, 'verification-docs'), filename,
        as_attachment=True
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@core_bp.route('/sw.js')
def service_worker():
    """Service Worker для PWA (кроме TESTING)."""
    if os.environ.get('TESTING', '').strip().lower() in ('true', '1', 'yes'):
        return '', 404
    return current_app.send_static_file('sw.js')


@core_bp.route('/offline')
def offline():
    """Offline fallback page for PWA service worker."""
    return render_template('offline.html')


@core_bp.route('/.well-known/assetlinks.json')
def assetlinks():
    """Digital Asset Links for Trusted Web Activity (Google Play)."""
    return send_from_directory('static/.well-known', 'assetlinks.json',
                               mimetype='application/json')


@core_bp.route('/favicon.ico')
def favicon():
    return '', 204


@core_bp.route('/jobs')
def jobs_redirect():
    return redirect(url_for('jobs.index', tab='jobs'))


@core_bp.route('/search')
def search_redirect():
    return redirect(url_for('jobs.index', tab='search'))


@core_bp.before_request
def log_static_requests():
    """Диагностический лог: отслеживание запросов к /static/ для поиска 500."""
    if request.path.startswith('/static/'):
        current_app.logger.info('Static request: %s | method=%s | user_agent=%s',
                                request.path, request.method,
                                request.headers.get('User-Agent', 'unknown')[:120])


@core_bp.route('/static/')
def static_directory_redirect():
    """Запрос /static/ без имени файла → 404 вместо 500."""
    current_app.logger.warning('Static directory listing requested: %s', request.path)
    abort(404)


@core_bp.route('/terms')
def terms():
    """Страница «Условия использования»."""
    return render_template('terms.html')


@core_bp.route('/privacy')
def privacy():
    """Страница «Политика конфиденциальности»."""
    return render_template('privacy.html')


@core_bp.route('/api/client-error', methods=['POST'])
def client_error_report():
    """Приём отчётов об ошибках от frontend JavaScript.
    
    Frontend отправляет JSON с информацией об ошибке:
    - message: текст ошибки
    - source: источник (URL скрипта)
    - lineno: номер строки
    - colno: номер колонки
    - stack: стек вызовов (если доступен)
    - url: URL страницы
    - userAgent: User-Agent браузера
    
    Логирует ошибку с уровнем WARNING для мониторинга.
    
    Rate limited: 20 отчётов в минуту на IP (защита от log-flooding).
    """
    # Rate limiting: 20 отчётов в минуту на IP
    client_ip = request.remote_addr or 'unknown'
    rate_key = f'client_error_ratelimit:{client_ip}'
    try:
        from app.utils.redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            current = redis_client.incr(rate_key)
            if current == 1:
                redis_client.expire(rate_key, 60)
            if current > 20:
                return jsonify({'status': 'rate_limited'}), 429
    except Exception as e:
        current_app.logger.warning('client-error rate limit check failed: %s', e, exc_info=True)
    
    try:
        data = request.get_json(silent=True) or {}
        
        # Извлекаем информацию об ошибке
        message = data.get('message', 'Unknown error')[:500]  # Ограничиваем длину
        source = data.get('source', 'unknown')[:200]
        lineno = data.get('lineno', 0)
        colno = data.get('colno', 0)
        stack = data.get('stack', '')[:1000]  # Ограничиваем стек
        page_url = data.get('url', request.referrer or 'unknown')[:200]
        user_agent = data.get('userAgent', request.headers.get('User-Agent', 'unknown'))[:200]
        
        # Получаем информацию о пользователе (если есть)
        user_id = session.get('user_id', 'anonymous')
        
        # Логируем ошибку
        current_app.logger.warning(
            'Frontend error: user=%s message=%s source=%s line=%s col=%s url=%s userAgent=%s',
            user_id, message, source, lineno, colno, page_url, user_agent
        )
        
        # Если есть стек, логируем отдельно
        if stack:
            current_app.logger.warning('Frontend error stack: %s', stack)
        
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        current_app.logger.error('Failed to process client error report: %s', e, exc_info=True)
        return jsonify({'status': 'error', 'message': 'Internal error'}), 500
