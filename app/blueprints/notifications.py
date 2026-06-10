"""Blueprint уведомлений — тонкие обёртки над NotificationService."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.services.notification_service import (
    get_notifications, get_unread_count, mark_all_read, mark_read
)
from app.utils import my_query, supabase_request

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications')
@login_required
def notifications():
    resp = supabase_request('GET',
        my_query('notifications', extra='&order=created_at.desc&limit=50'))
    items = resp.json() if resp.ok else []

    import re
    unread_ids = [str(n['id']) for n in items if not n.get('is_read')]
    safe_ids = [uid for uid in unread_ids if re.match(r'^[a-zA-Z0-9_-]+$', uid)]
    if safe_ids:
        supabase_request('PATCH', f'notifications?id=in.({",".join(safe_ids)})', json={'is_read': True})

    return render_template('notifications.html', items=items, unread=len(unread_ids))


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


@notifications_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
def mark_read_route(notification_id):
    mark_read(notification_id)
    return redirect(url_for('notifications.notifications'))
