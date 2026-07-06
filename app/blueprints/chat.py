import html as _html
import logging

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, rate_limit, role_required, validate_uuid
from app.utils import postgrest_request
from app.utils.redis_client import get_redis_client
from app.services.notification_service import create as create_notification, enqueue_notification

logger = logging.getLogger(__name__)

# A3: Lua-скрипт для атомарного rate limiting
# INCR + EXPIRE в одной атомарной операции предотвращает race condition
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, ttl)
end
return count
"""


def _check_chat_rate_limit(redis_client, user_id: str, application_id: str,
                           limit: int = 5, window: int = 60) -> bool:
    """Проверить rate limit для чата через атомарный Lua-скрипт.
    
    Args:
        redis_client: Redis клиент
        user_id: ID отправителя
        application_id: ID заявки (чата)
        limit: максимальное количество сообщений в окне
        window: размер окна в секундах
        
    Returns:
        True если в пределах лимита, False если превышен
    """
    key = f'chat_rate:{user_id}:{application_id}'
    try:
        count = redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, limit, window)
        return count <= limit
    except Exception as e:
        logger.warning('chat rate limit check failed: %s', e, exc_info=True)
        # Fail-open: если Redis недоступен, разрешаем отправку
        return True

try:
    from app.services.redis_publisher import redis_publisher
except ImportError:
    redis_publisher = None

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
        resp = postgrest_request('GET',
            f'applications?or=(worker_id.eq.{user_id},job.employer_id.eq.{user_id})'
            f'&status=eq.accepted&select=id,job:jobs(organization_name,employer_id)')
    else:
        # Заявки, где пользователь — принятый работник
        resp = postgrest_request('GET',
            f'applications?worker_id=eq.{user_id}&status=eq.accepted'
            f'&select=id,job:jobs(organization_name)')
    return render_template('chats_list.html', chats=resp.json() if resp.ok else [])


@chat_bp.route('/chat/<application_id>')
@login_required
@validate_uuid('application_id')
def chat(application_id):
    """Чат по заявке (application_id)."""
    user_id = session['user_id']

    # Проверить, что пользователь — участник заявки
    # employer_id получаем через join с jobs
    app_resp = postgrest_request('GET',
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
        resp = postgrest_request('GET',
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
@role_required('employer')
@validate_uuid('worker_id')
def chat_new(worker_id):
    """Поиск существующего чата с работником (по accepted-заявке) или редирект на список чатов."""
    user_id = session['user_id']

    # Ищем accepted-заявку от этого работодателя этому работнику
    # employer_id фильтруется через join с jobs (нет колонки employer_id в applications)
    resp = postgrest_request('GET',
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

    # A3: Per-chat rate limit через атомарный Lua-скрипт
    redis_client = get_redis_client()
    if redis_client:
        if not _check_chat_rate_limit(redis_client, sender_id, application_id, limit=5, window=60):
            return jsonify({'error': 'Слишком много сообщений'}), 429

    # Серверная валидация длины сообщения
    if len(content) > 2000:
        return jsonify({'status': 'error', 'message': 'Сообщение слишком длинное (максимум 2000 символов)'}), 400

    # Проверить, что пользователь — участник заявки
    # employer_id получаем через join с jobs
    app_resp = postgrest_request('GET',
        f'applications?id=eq.{application_id}&select=worker_id,job_id,status,job:jobs(employer_id)')
    if not app_resp.ok or not app_resp.json():
        return jsonify({'status': 'error', 'message': 'Заявка не найдена'}), 404

    app_data = app_resp.json()[0]
    employer_id = (app_data.get('job') or {}).get('employer_id')
    if sender_id not in (app_data.get('worker_id'), employer_id):
        return jsonify({'status': 'error', 'message': 'Нет доступа к этому чату'}), 403

    # Чат доступен только для принятых заявок (общение разрешено после accept, не дожидаясь completed)
    if app_data.get('status') != 'accepted':
        return jsonify({'status': 'error', 'message': 'Чат доступен только после принятия отклика'}), 403

    # XSS-санитизация: экранируем HTML-теги в сообщении
    sanitized_content = _html.escape(content, quote=True)

    # Сохраняем сообщение и получаем его ID из ответа
    headers = {'Prefer': 'return=representation'}
    msg_resp = postgrest_request('POST', 'messages', json={
        'application_id': application_id,
        'sender_id': sender_id,
        'content': sanitized_content
    }, headers=headers)

    if not msg_resp.ok:
        logger.warning('chat.send_message failed: %s', msg_resp.text)
        return jsonify({'status': 'error', 'message': 'Не удалось отправить сообщение'}), 503

    message_id = None
    try:
        msg_data = msg_resp.json()
        if isinstance(msg_data, list) and len(msg_data) > 0:
            message_id = msg_data[0].get('id')
    except Exception:
        pass

    # Уведомить получателя (transactional outbox)
    recipient = app_data['worker_id'] if sender_id == employer_id else employer_id
    enqueue_notification(recipient, 'new_message', 'Новое сообщение',
                       sanitized_content[:100],
                       data={'application_id': application_id,
                              'link': url_for('chat.chat', application_id=application_id, _external=True)})

    # Публикуем событие в Redis для мгновенной доставки через WebSocket
    if redis_publisher is not None:
        try:
            redis_publisher.publish_chat_message(
                sender_id=sender_id,
                recipient_id=recipient,
                message_data={
                    'message_id': message_id,
                    'text': sanitized_content,
                    'sender_id': sender_id,
                    'sender_name': session.get('username', 'Пользователь'),
                    'application_id': application_id,
                    'job_id': app_data.get('job_id')
                }
            )
        except Exception as e:
            from flask import current_app
            current_app.logger.warning("Не удалось опубликовать сообщение чата в Redis: %s", e)

    return jsonify({'status': 'ok'})


@chat_bp.route('/api/messages/<application_id>/poll')
@login_required
@validate_uuid('application_id')
def poll_messages(application_id):
    """Polling-эндпоинт: вернуть сообщения новее указанного ID."""
    user_id = session['user_id']

    # Проверить доступ
    # employer_id получаем через join с jobs
    app_resp = postgrest_request('GET',
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
        since_resp = postgrest_request('GET', f'messages?id=eq.{since_id}&select=created_at')
        if since_resp.ok and since_resp.json():
            since_time = since_resp.json()[0]['created_at']
            query += f'&created_at=gt.{since_time}'
    resp = postgrest_request('GET', query)
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
        resp = postgrest_request('GET',
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
        postgrest_request('DELETE', f'messages?application_id=eq.{aid}')
        deleted += 1

    return jsonify({
        'status': 'ok',
        'deleted': deleted,
        'errors': errors
    })
