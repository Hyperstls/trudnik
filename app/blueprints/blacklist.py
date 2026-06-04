from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request

blacklist_bp = Blueprint('blacklist', __name__)


@blacklist_bp.route('/blacklist')
@login_required
def blacklist():
    resp = supabase_request('GET',
        f'blacklists?user_id=eq.{session["user_id"]}&select=blocked:profiles!blacklists_blocked_user_id_fkey(id,full_name,photo_url)')
    return render_template('blacklist.html', items=resp.json() if resp.ok else [])


@blacklist_bp.route('/blacklist/<user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    supabase_request('POST', 'blacklists', json={'user_id': session['user_id'], 'blocked_user_id': user_id})
    return redirect(request.referrer or url_for('index'))


@blacklist_bp.route('/unblock/<user_id>', methods=['POST'])
@login_required
def unblock_user(user_id):
    supabase_request('DELETE', f'blacklists?user_id=eq.{session["user_id"]}&blocked_user_id=eq.{user_id}')
    return redirect(url_for('blacklist'))
