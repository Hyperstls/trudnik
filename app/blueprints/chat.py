from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import rate_limit, supabase_request
from app.services.notification_service import create as create_notification

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/chats')
@login_required
def chats_list():
    """Список чатов пользователя: все принятые заявки, где он участник."""
    user_id = session['user_id']
    role = session.get('role', '')
    if role == 'employer':
        # Заявки, где пользователь — работодатель задания
        # employer_id берётся через join с jobs (нет колонки employer_id в applications)
        resp = supabase_request('GET',
            f'applications?or=(worker_id.eq.{user_id},job.employer_id.eq.{user_id})'
            f'&status=eq.accepted&select=id,job:jobs(organization_name,employer_id)')
    else:
        # Заявки, где пользователь — принятый работник
        resp = supabase_request('GET',
            f'applications?worker_id=eq.{user_id}&status=eq.accepted'
            f'&select=id,job:jobs(organization_name)')
    return render_template('chats_list.html', chats=resp.json() if resp.ok else [])


@chat_bp.route('/chat/<application_id>')
@login_required
def chat(application_id):
    """Чат по заявке (application_id)."""
    user_id = session['user_id']

    # Проверить, что пользователь — участник заявки
    # employer_id получаем через join с jobs
    app_resp = supabase_request('GET',
        f'applications?id=eq.{application_id}&select=worker_id,job_id,job:jobs(employer_id)')
    if not app_resp.ok or not app_resp.json():
        flash('Чат не найден', 'danger')
        return redirect(url_for('chat.chats_list'))

    app_data = app_resp.json()[0]
    employer_id = (app_data.get('job') or {}).get('employer_id')
    if user_id not in (app_data.get('worker_id'), employer_id):
        flash('Нет доступа к этому чату', 'danger')
        return redirect(url_for('chat.chats_list'))

    try:
        resp = supabase_request('GET',
            f'messages?application_id=eq.{application_id}'
            f'&select=id,sender_id,content,created_at&order=created_at.asc')
        messages = resp.json() if resp.ok else []
    except Exception as e:
        from flask import current_app
        current_app.logger.error('[CHAT] Error loading messages for app %s: %s', application_id, str(e))
        messages = []
    return render_template('chat.html', application_id=application_id,
                           messages=messages, user_id=session['user_id'])


@chat_bp.route('/chat/new/<worker_id>', methods=['GET'])
@login_required
def chat_new(worker_id):
    """Поиск существующего чата с работником (по accepted-заявке) или редирект на список чатов."""
    user_id = session['user_id']
    if session.get('role') != 'employer':
        flash('Только работодатели могут создавать чаты', 'danger')
        return redirect(url_for('jobs.index'))

    # Ищем accepted-заявку от этого работодателя этому работнику
    # employer_id фильтруется через join с jobs (нет колонки employer_id в applications)
    resp = supabase_request('GET',
        f'applications?job.employer_id=eq.{user_id}&worker_id=eq.{worker_id}'
        f'&status=eq.accepted&select=id')
    if resp.ok and resp.json():
        application_id = resp.json()[0]['id']
        return redirect(url_for('chat.chat', application_id=application_id))

    flash('Чат недоступен — сначала примите отклик этого работника на ваше задание', 'warning')
    return redirect(url_for('chat.chats_list'))


@chat_bp.route('/api/send_message', methods=['POST'])
@login_required
@rate_limit
def send_message():
    """Отправить сообщение в чат заявки."""
    data = request.get_json()
    sender_id = session['user_id']
    application_id = data['application_id']
    content = data['content']

    # Серверная валидация длины сообщения
    if len(content) > 2000:
        return jsonify({'status': 'error', 'message': 'Сообщение слишком длинное (максимум 2000 символов)'}), 400

    # Проверить, что пользователь — участник заявки
    # employer_id получаем через join с jobs
    app_resp = supabase_request('GET',
        f'applications?id=eq.{application_id}&select=worker_id,job_id,status,job:jobs(employer_id)')
    if not app_resp.ok or not app_resp.json():
        return jsonify({'status': 'error', 'message': 'Заявка не найдена'}), 404

    app_data = app_resp.json()[0]
    employer_id = (app_data.get('job') or {}).get('employer_id')
    if sender_id not in (app_data.get('worker_id'), employer_id):
        return jsonify({'status': 'error', 'message': 'Нет доступа к этому чату'}), 403

    # Чат доступен только для принятых заявок
    if app_data.get('status') != 'accepted':
        return jsonify({'status': 'error', 'message': 'Чат доступен только после принятия отклика'}), 403

    # Отправка сообщений разрешена только для заданий в статусе completed
    job_resp = supabase_request('GET', f'jobs?id=eq.{app_data["job_id"]}&select=status')
    if job_resp.ok and job_resp.json():
        job_status = job_resp.json()[0].get('status')
        if job_status != 'completed':
            status_labels = {
                'open': 'открыто',
                'cancelled': 'отменено',
            }
            label = status_labels.get(job_status, job_status)
            return jsonify({'status': 'error', 'message': f'Отправка сообщений недоступна — задание {label}'}), 403

    supabase_request('POST', 'messages', json={
        'application_id': application_id,
        'sender_id': sender_id,
        'content': content
    })

    # Уведомить получателя
    recipient = app_data['worker_id'] if sender_id == employer_id else employer_id
    create_notification(recipient, 'new_message', 'Новое сообщение',
                       data['content'][:100], data={'application_id': application_id})

    return jsonify({'status': 'ok'})


@chat_bp.route('/api/messages/<application_id>/poll')
@login_required
def poll_messages(application_id):
    """Polling-эндпоинт: вернуть сообщения новее указанного ID."""
    user_id = session['user_id']

    # Проверить доступ
    # employer_id получаем через join с jobs
    app_resp = supabase_request('GET',
        f'applications?id=eq.{application_id}&select=worker_id,job:jobs(employer_id)')
    if not app_resp.ok or not app_resp.json():
        return jsonify({'messages': [], 'user_id': user_id})
    app_data = app_resp.json()[0]
    employer_id = (app_data.get('job') or {}).get('employer_id')
    if user_id not in (app_data.get('worker_id'), employer_id):
        return jsonify({'messages': [], 'user_id': user_id})

    since_id = request.args.get('since_id', '')
    query = (f'messages?application_id=eq.{application_id}'
             f'&select=id,sender_id,content,created_at&order=created_at.asc')
    if since_id:
        since_resp = supabase_request('GET', f'messages?id=eq.{since_id}&select=created_at')
        if since_resp.ok and since_resp.json():
            since_time = since_resp.json()[0]['created_at']
            query += f'&created_at=gt.{since_time}'
    resp = supabase_request('GET', query)
    messages = resp.json() if resp.ok else []
    return jsonify({'messages': messages, 'user_id': user_id})


@chat_bp.route('/api/delete-chats', methods=['POST'])
@login_required
def delete_chats():
    """Удаление одного или нескольких чатов (application_id). Доступно работодателю и труднику."""
    user_id = session['user_id']
    data = request.get_json()
    application_ids = data.get('application_ids', [])
    if not application_ids:
        return jsonify({'status': 'error', 'message': 'Не указаны чаты для удаления'}), 400

    deleted = 0
    errors = []
    for aid in application_ids:
        # Проверяем, что пользователь — участник заявки
        # employer_id получаем через join с jobs
        resp = supabase_request('GET',
            f'applications?id=eq.{aid}&select=id,worker_id,job:jobs(employer_id)')
        if not resp.ok or not resp.json():
            errors.append(f'Чат {aid} не найден')
            continue
        app_data = resp.json()[0]
        employer_id = (app_data.get('job') or {}).get('employer_id')
        if app_data['worker_id'] != user_id and employer_id != user_id:
            errors.append(f'Нет доступа к чату {aid}')
            continue

        # Удаляем сообщения чата
        supabase_request('DELETE', f'messages?application_id=eq.{aid}')
        deleted += 1

    return jsonify({
        'status': 'ok',
        'deleted': deleted,
        'errors': errors
    })
