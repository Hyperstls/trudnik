from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request
from app.services.notification_service import create as create_notification

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/chats')
@login_required
def chats_list():
    user_id = session['user_id']
    resp = supabase_request('GET',
        f'shifts?or=(worker_id.eq.{user_id},employer_id.eq.{user_id})&select=id,job:jobs(organization_name)')
    return render_template('chats_list.html', chats=resp.json() if resp.ok else [])


@chat_bp.route('/chat/<shift_id>')
@login_required
def chat(shift_id):
    try:
        resp = supabase_request('GET', f'messages?shift_id=eq.{shift_id}&select=id,sender_id,content,created_at&order=created_at.asc')
        messages = resp.json() if resp.ok else []
    except Exception as e:
        from flask import current_app
        current_app.logger.error('[CHAT] Error loading messages for shift %s: %s', shift_id, str(e))
        messages = []
    return render_template('chat.html', shift_id=shift_id,
                           messages=messages, user_id=session['user_id'])


@chat_bp.route('/chat/new/<worker_id>', methods=['GET'])
@login_required
def chat_new(worker_id):
    """Поиск существующего чата с работником или редирект на список чатов."""
    user_id = session['user_id']
    if session.get('role') != 'employer':
        flash('Только работодатели могут создавать чаты', 'danger')
        return redirect(url_for('jobs.index'))

    resp = supabase_request('GET', f'shifts?employer_id=eq.{user_id}&worker_id=eq.{worker_id}&select=id')
    if resp.ok and resp.json():
        shift_id = resp.json()[0]['id']
        return redirect(url_for('chat.chat', shift_id=shift_id))

    flash('Чат недоступен — сначала примите отклик этого работника на ваше задание', 'warning')
    return redirect(url_for('chat.chats_list'))


@chat_bp.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    sender_id = session['user_id']
    shift_id = data['shift_id']

    supabase_request('POST', 'messages', json={
        'shift_id': shift_id, 'sender_id': sender_id, 'content': data['content']
    })

    # Уведомить получателя
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=worker_id,employer_id')
    if shift_resp.ok and shift_resp.json():
        shift = shift_resp.json()[0]
        recipient = shift['worker_id'] if sender_id == shift['employer_id'] else shift['employer_id']
        create_notification(recipient, 'new_message', 'Новое сообщение',
                           data['content'][:100], data={'shift_id': shift_id})

    return jsonify({'status': 'ok'})


@chat_bp.route('/api/messages/<shift_id>/poll')
@login_required
def poll_messages(shift_id):
    """Polling-эндпоинт: вернуть сообщения новее указанного ID."""
    since_id = request.args.get('since_id', '')
    query = f'messages?shift_id=eq.{shift_id}&select=id,sender_id,content,created_at&order=created_at.asc'
    if since_id:
        # Запрашиваем сообщения после указанного ID по времени
        since_resp = supabase_request('GET', f'messages?id=eq.{since_id}&select=created_at')
        if since_resp.ok and since_resp.json():
            since_time = since_resp.json()[0]['created_at']
            query += f'&created_at=gt.{since_time}'
    resp = supabase_request('GET', query)
    messages = resp.json() if resp.ok else []
    return jsonify({'messages': messages, 'user_id': session['user_id']})


@chat_bp.route('/api/delete-chats', methods=['POST'])
@login_required
def delete_chats():
    """Удаление одного или нескольких чатов (shift_id). Доступно работодателю и труднику."""
    user_id = session['user_id']
    data = request.get_json()
    shift_ids = data.get('shift_ids', [])
    if not shift_ids:
        return jsonify({'status': 'error', 'message': 'Не указаны чаты для удаления'}), 400

    deleted = 0
    errors = []
    for sid in shift_ids:
        # Проверяем, что пользователь — участник чата
        resp = supabase_request('GET', f'shifts?id=eq.{sid}&select=id,worker_id,employer_id')
        if not resp.ok or not resp.json():
            errors.append(f'Чат {sid} не найден')
            continue
        shift = resp.json()[0]
        if shift['worker_id'] != user_id and shift['employer_id'] != user_id:
            errors.append(f'Нет доступа к чату {sid}')
            continue

        # Удаляем сообщения чата, затем сам shift
        supabase_request('DELETE', f'messages?shift_id=eq.{sid}')
        del_resp = supabase_request('DELETE', f'shifts?id=eq.{sid}')
        if del_resp.ok:
            deleted += 1
        else:
            errors.append(f'Не удалось удалить чат {sid}')

    return jsonify({
        'status': 'ok',
        'deleted': deleted,
        'errors': errors
    })
