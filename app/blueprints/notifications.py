"""Blueprint уведомлений — тонкие обёртки над NotificationService."""

import re as _re_inv

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.services.notification_service import (
    NOTIFICATION_TYPES, DEFAULT_ENABLED_TYPES,
    get_notifications, get_unread_count, mark_all_read, mark_read
)
from app.utils import my_query, supabase_request, supabase_admin_request

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications')
@login_required
def notifications():
    resp = supabase_request('GET',
        my_query('notifications', extra='&order=created_at.desc&limit=50'))
    items = resp.json() if resp.ok else []

    # Отделяем приглашения трудника — они на странице /invitations
    # Фильтруем только "Вас пригласили", а "Приглашение принято" остаётся у работодателя
    general_items = [n for n in items if 'вас пригласили' not in (n.get('message') or '').lower()]

    # Очистка: удаляем уведомления-приглашения трудника, чьи задания уже удалены
    invitation_items = [n for n in items if 'вас пригласили' in (n.get('message') or '').lower()]
    if invitation_items:
        job_ids_in_notifications = set()
        for n in invitation_items:
            match = _re_inv.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', n.get('message') or '')
            if match:
                job_ids_in_notifications.add(match.group(0))
        if job_ids_in_notifications:
            ids_filter = ','.join(job_ids_in_notifications)
            jobs_check = supabase_admin_request('GET', f'jobs?id=in.({ids_filter})&select=id')
            existing_ids = {j['id'] for j in (jobs_check.json() or [])} if jobs_check.ok else set()
            for job_id in (job_ids_in_notifications - existing_ids):
                supabase_admin_request('DELETE', f'notifications?message=ilike.*{job_id}*')

    unread_ids = [str(n['id']) for n in general_items if not n.get('is_read')]
    safe_ids = [uid for uid in unread_ids if _re_inv.match(r'^[a-zA-Z0-9_-]+$', uid)]
    if safe_ids:
        supabase_request('PATCH', f'notifications?id=in.({",".join(safe_ids)})', json={'is_read': True})

    return render_template('notifications.html', items=general_items, unread=len(unread_ids))


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
def api_delete_notification(notification_id):
    """Удалить одно уведомление."""
    user_id = session['user_id']
    resp = supabase_admin_request('DELETE',
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
    supabase_admin_request('DELETE',
        f'notifications?user_id=eq.{user_id}&message=not.ilike.*вас пригласили*')
    return jsonify({'success': True})


@notifications_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
def mark_read_route(notification_id):
    mark_read(notification_id)
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
def api_save_preference():
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
    resp = supabase_admin_request('PATCH',
        f'profiles?id=eq.{user_id}',
        json={'notification_prefs': prefs})
    if resp.ok:
        return jsonify({'success': True, 'message': 'Настройка сохранена'})
    return jsonify({'success': False, 'error': 'Ошибка сохранения'}), 500


# ============================================================
# Push-уведомления (Web Push API)
# ============================================================

@notifications_bp.route('/push/vapid-public-key')
@login_required
def push_vapid_public_key():
    """Возвращает публичный VAPID-ключ для фронтенда."""
    import os as _os
    public_key = _os.environ.get('VAPID_PUBLIC_KEY', '')
    return jsonify({'public_key': public_key})


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
    success = push_service.delete_subscription(endpoint)
    return jsonify({'success': success})


@notifications_bp.route('/push/subscription', methods=['GET'])
@login_required
def push_get_subscriptions():
    """Получение списка активных push-подписок пользователя."""
    from app.services.push_service import PushService
    push_service = PushService()
    subscriptions = push_service.get_user_subscriptions(session['user_id'])
    return jsonify({'subscriptions': subscriptions})
