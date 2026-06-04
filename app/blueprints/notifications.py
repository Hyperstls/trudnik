from flask import Blueprint, flash, redirect, render_template, request, session, url_for

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
    unread_ids = [n['id'] for n in items if not n.get('is_read')]
    if unread_ids:
        supabase_request('PATCH', f'notifications?id=in.({",".join(unread_ids)})', json={'is_read': True})

    return render_template('notifications.html', items=items, unread=len(unread_ids))


@notifications_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    supabase_request('PATCH', f'notifications?id=eq.{notification_id}',
        json={'is_read': True})
    return redirect(url_for('notifications'))
