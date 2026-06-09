from flask import Blueprint, jsonify, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications')
@login_required
def notifications():
    resp = supabase_request('GET',
        f'notifications?user_id=eq.{session["user_id"]}&order=created_at.desc&limit=50')
    items = resp.json() if resp.ok else []

    # Пометить все как прочитанные
    import re
    unread_ids = [str(n['id']) for n in items if not n.get('is_read')]
    safe_ids = [uid for uid in unread_ids if re.match(r'^[a-zA-Z0-9_-]+$', uid)]
    if safe_ids:
        supabase_request('PATCH', f'notifications?id=in.({",".join(safe_ids)})', json={'is_read': True})

    return render_template('notifications.html', items=items, unread=len(unread_ids))


# ── API эндпоинты ──────────────────────────────

@notifications_bp.route('/api/notifications/unread-count')
@login_required
def api_unread_count():
    """Быстрый счётчик непрочитанных для polling."""
    resp = supabase_request('GET',
        f'notifications?user_id=eq.{session["user_id"]}&is_read=eq.false&select=id&limit=100')
    count = len(resp.json()) if resp.ok else 0
    return jsonify({'unread': count})


@notifications_bp.route('/api/notifications')
@login_required
def api_notifications():
    """Список уведомлений с пагинацией (JSON)."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(50, max(1, request.args.get('per_page', 20, type=int)))
    offset = (page - 1) * per_page

    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET',
        f'notifications?user_id=eq.{session["user_id"]}&order=created_at.desc'
        f'&limit={per_page}&offset={offset}',
        headers=headers)
    items = resp.json() if resp.ok else []
    total = int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1]) if resp.ok else 0

    return jsonify({
        'results': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1
    })


@notifications_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_read_all():
    """Пометить все уведомления прочитанными."""
    supabase_request('PATCH',
        f'notifications?user_id=eq.{session["user_id"]}&is_read=eq.false',
        json={'is_read': True})
    return jsonify({'success': True})


@notifications_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    supabase_request('PATCH', f'notifications?id=eq.{notification_id}',
        json={'is_read': True})
    return redirect(url_for('notifications.notifications'))
