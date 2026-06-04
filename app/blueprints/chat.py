from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request

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
    resp = supabase_request('GET', f'messages?shift_id=eq.{shift_id}&select=*&order=created_at.asc')
    return render_template('chat.html', shift_id=shift_id,
                           messages=resp.json() if resp.ok else [], user_id=session['user_id'])


@chat_bp.route('/chat/new/<worker_id>', methods=['GET'])
@login_required
def chat_new(worker_id):
    """Создание нового чата с работником"""
    user_id = session['user_id']
    if session.get('role') != 'employer':
        flash('Только работодатели могут создавать чаты', 'danger')
        return redirect(url_for('index'))

    resp = supabase_request('GET', f'shifts?employer_id=eq.{user_id}&worker_id=eq.{worker_id}&select=id')
    if resp.ok and resp.json():
        shift_id = resp.json()[0]['id']
        return redirect(url_for('chat', shift_id=shift_id))

    shift_data = {
        'employer_id': user_id,
        'worker_id': worker_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }
    resp = supabase_request('POST', 'shifts', json=shift_data)
    if resp.ok:
        shift_id = resp.json()[0]['id'] if isinstance(resp.json(), list) else resp.json().get('id')
        return redirect(url_for('chat', shift_id=shift_id))

    flash('Не удалось создать чат', 'danger')
    return redirect(url_for('index'))


@chat_bp.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    supabase_request('POST', 'messages', json={
        'shift_id': data['shift_id'], 'sender_id': session['user_id'], 'content': data['content']
    })
    return jsonify({'status': 'ok'})
