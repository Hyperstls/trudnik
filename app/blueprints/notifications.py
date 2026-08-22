"""Blueprint уведомлений — тонкие обёртки над NotificationService."""

import re as _re_inv

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, validate_uuid
from app.services.notification_service import (
    NOTIFICATION_TYPES, DEFAULT_ENABLED_TYPES,
    get_notifications, get_unread_count, mark_all_read, mark_read
)
from app.utils import my_query, postgrest_request, postgrest_admin_request

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/api/ws/token')
@login_required
def get_ws_token():
    """Выдать короткоживущий JWT для подключения к WebSocket-серверу.

    Токен НЕ встраивается в HTML каждой страницы (XSS-риск), а запрашивается
    клиентом по защищённому эндпоинту. TTL — 5 минут (минимум для установки
    WS-соединения), jti уникален для каждого запроса.
    """
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt
    from app.config import Config
    token = pyjwt.encode(
        {
            'user_id': str(session['user_id']),
            'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
            'jti': str(_uuid.uuid4()),
        },
        Config.WEBSOCKET_JWT_SECRET or Config.SECRET_KEY,
        algorithm='HS256',
    )
    return jsonify({'token': token, 'wsUrl': Config.WEBSOCKET_PUBLIC_URL})


@notifications_bp.route('/notifications')
@login_required
def notifications():
    resp = postgrest_request('GET',
        my_query('notifications', extra='&order=created_at.desc&limit=50'))
    items = resp.json() if resp.ok else []

    # Отделяем приглашения трудника — они на странице /invitations
    # Фильтруем только "Вас пригласили", а "Приглашение принято" остаётся у работодателя
    general_items = [n for n in items if 'вас пригласили' not in (n.get('message') or '').lower()]

    # Очистка orphaned-уведомлений вынесена в периодическую Celery-задачу
    # cleanup_orphaned_notifications (app/tasks/maintenance_tasks.py).
    # Здесь не делаем синхронных запросов для ускорения загрузки страницы.
    # Авто-отметка прочитанными убрана — теперь только через явное действие пользователя

    unread_count = len([str(n['id']) for n in general_items if not n.get('is_read')])
    return render_template('notifications.html', items=general_items, unread=unread_count)


@notifications_bp.route('/api/notifications/unread-count')
@login_required
def api_unread_count():
    return jsonify({'unread': get_unread_count(session['user_id'])})


@notifications_bp.route('/api/notifications')
@login_required
def api_notifications():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(50, max(1, request.args.get('per_page', 20, type=int)))
    return jsonify(get_notifications(session['user_id'], page, per_page))


@notifications_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_read_all():
    mark_all_read(session['user_id'])
    return jsonify({'success': True})


@notifications_bp.route('/api/notifications/<notification_id>/delete', methods=['POST'])
@login_required
@validate_uuid('notification_id')
def api_delete_notification(notification_id):
    """Удалить одно уведомление."""
    user_id = session['user_id']
    resp = postgrest_admin_request('DELETE',
        f'notifications?id=eq.{notification_id}&user_id=eq.{user_id}')
    if resp.ok:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Ошибка удаления'}), 400


@notifications_bp.route('/api/notifications/delete-all', methods=['POST'])
@login_required
def api_delete_all_notifications():
    """Удалить все уведомления пользователя (кроме приглашений)."""
    user_id = session['user_id']
    # Удаляем все уведомления, кроме "Вас пригласили" (приглашения трудника)
    postgrest_admin_request('DELETE',
        f'notifications?user_id=eq.{user_id}&message=not.ilike.*вас пригласили*')
    return jsonify({'success': True})


@notifications_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
@validate_uuid('notification_id')
def mark_read_route(notification_id):
    mark_read(notification_id, user_id=session['user_id'])
    return redirect(url_for('notifications.notifications'))


# ============================================================
# Настройки уведомлений
# ============================================================

@notifications_bp.route('/notifications/settings')
@login_required
def notification_settings_page():
    """Страница настроек уведомлений."""
    return render_template('notification_settings.html',
                           notification_types=NOTIFICATION_TYPES,
                           default_enabled=DEFAULT_ENABLED_TYPES)


@notifications_bp.route('/api/notifications/preferences', methods=['GET'])
@login_required
def api_get_preferences():
    """Получить настройки уведомлений пользователя."""
    from app.services.notification_service import get_user_prefs
    prefs = get_user_prefs(session['user_id'])
    # Возвращаем все типы с их статусом
    result = {}
    for key, label in NOTIFICATION_TYPES.items():
        result[key] = {
            'label': label,
            'enabled': prefs.get(key, DEFAULT_ENABLED_TYPES.get(key, True))
        }
    # Глобальные переключатели каналов
    channels = {
        'email_enabled': prefs.get('email_enabled', True),
        'push_enabled': prefs.get('push_enabled', True),
        'in_app_enabled': prefs.get('in_app_enabled', True),
    }
    return jsonify({'success': True, 'preferences': result, 'channels': channels})


@notifications_bp.route('/api/notifications/preferences', methods=['POST'])
@login_required
def api_update_preferences():
    """Сохранить одну настройку уведомления.
    Body: {type: str, enabled: bool}
    Поддерживаются как типы уведомлений, так и каналы (email_enabled, push_enabled, in_app_enabled).
    """
    data = request.get_json(silent=True) or {}
    notif_type = data.get('type')
    enabled = data.get('enabled')

    CHANNEL_KEYS = {'email_enabled', 'push_enabled', 'in_app_enabled'}
    if not notif_type or (notif_type not in NOTIFICATION_TYPES and notif_type not in CHANNEL_KEYS):
        return jsonify({'success': False, 'error': 'Неизвестный тип уведомления или канал'}), 400
    if not isinstance(enabled, bool):
        return jsonify({'success': False, 'error': 'enabled должен быть boolean'}), 400

    user_id = session['user_id']

    # Получить текущие настройки
    from app.services.notification_service import get_user_prefs
    prefs = get_user_prefs(user_id)
    prefs[notif_type] = enabled

    # Сохранить в profiles.notification_prefs
    resp = postgrest_admin_request('PATCH',
        f'profiles?id=eq.{user_id}',
        json={'notification_prefs': prefs})
    if resp.ok:
        return jsonify({'success': True, 'message': 'Настройка сохранена'})
    return jsonify({'success': False, 'error': 'Ошибка сохранения'}), 500


# ============================================================
# Push-уведомления (Web Push API)
# ============================================================

@notifications_bp.route('/push/vapid-public-key')
def push_vapid_public_key():
    """Возвращает публичный VAPID-ключ для фронтенда."""
    import os as _os
    public_key = _os.environ.get('VAPID_PUBLIC_KEY', '')
    return jsonify({'public_key': public_key})


@notifications_bp.route('/notifications/push/vapid-public-key')
def push_vapid_public_key_alias():
    return redirect(url_for('notifications.push_vapid_public_key'))


@notifications_bp.route('/push/subscription', methods=['POST'])
@login_required
def push_subscribe():
    """Подписка на push-уведомления.

    Тело запроса (JSON):
        {
            "endpoint": "...",
            "keys": {
                "p256dh": "...",
                "auth": "..."
            }
        }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400

    from app.services.push_service import PushService
    push_service = PushService()
    success = push_service.save_subscription(session['user_id'], data)
    return jsonify({'success': success})


@notifications_bp.route('/push/subscription', methods=['DELETE'])
@login_required
def push_unsubscribe():
    """Отписка от push-уведомлений.

    Тело запроса (JSON):
        {"endpoint": "https://..."}
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400

    endpoint = data.get('endpoint', '')
    if not endpoint:
        return jsonify({'success': False, 'error': 'endpoint обязателен'}), 400

    from app.services.push_service import PushService
    push_service = PushService()
    success = push_service.delete_subscription(endpoint, user_id=session['user_id'])
    return jsonify({'success': success})


@notifications_bp.route('/push/subscription', methods=['GET'])
@login_required
def push_get_subscriptions():
    """Получение списка активных push-подписок пользователя."""
    from app.services.push_service import PushService
    push_service = PushService()
    subscriptions = push_service.get_user_subscriptions(session['user_id'])
    return jsonify({'subscriptions': subscriptions})
