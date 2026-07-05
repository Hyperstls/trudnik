from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import postgrest_request
from app.utils.security import safe_redirect

blacklist_bp = Blueprint('blacklist', __name__)


def _is_ajax():
    """Определяет, является ли запрос AJAX-запросом (ожидает JSON-ответ)."""
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.headers.get('Accept') == 'application/json' or
            (request.headers.get('Content-Type') or '').startswith('application/json'))


def _reject_worker():
    """Запрещает доступ к ЧС для роли worker — возвращает 403 или редиректит."""
    if session.get('role') == 'worker':
        if _is_ajax():
            abort(403)
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('jobs.index'))
    return None


@blacklist_bp.route('/blacklist')
@login_required
def blacklist():
    err = _reject_worker()
    if err:
        return err
    resp = postgrest_request('GET',
        f'blacklists?user_id=eq.{session["user_id"]}&select=blocked:profiles!blacklists_blocked_user_id_fkey(id,full_name,photo_url,skills,city)')
    items = resp.json() if resp.ok else []
    # Разворачиваем вложенные объекты blocked → плоский список
    workers = []
    for item in items:
        if item.get('blocked'):
            workers.append(item['blocked'])
    return render_template('blacklist.html', workers=workers)


@blacklist_bp.route('/blacklist/<user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    err = _reject_worker()
    if err:
        return err
    resp = postgrest_request('POST', 'blacklists', json={'user_id': session['user_id'], 'blocked_user_id': user_id})
    if resp.ok:
        if _is_ajax():
            return jsonify({'success': True})
        return safe_redirect('jobs.index')
    if _is_ajax():
        return jsonify({'success': False, 'error': 'Ошибка блокировки'}), 400
    flash('Ошибка блокировки', 'danger')
    return safe_redirect('jobs.index')


@blacklist_bp.route('/unblock/<user_id>', methods=['POST'])
@login_required
def unblock_user(user_id):
    err = _reject_worker()
    if err:
        return err
    resp = postgrest_request('DELETE', f'blacklists?user_id=eq.{session["user_id"]}&blocked_user_id=eq.{user_id}')
    if resp.ok:
        if _is_ajax():
            return jsonify({'success': True})
        return redirect(url_for('blacklist.blacklist'))
    if _is_ajax():
        return jsonify({'success': False, 'error': 'Ошибка разблокировки'}), 400
    flash('Ошибка разблокировки', 'danger')
    return redirect(url_for('blacklist.blacklist'))
