import uuid

import requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required
from app.utils import SERVICE_KEY, SUPABASE_KEY, SUPABASE_URL, supabase_request, upload_to_storage

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    try:
        resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
        profile_user = resp.json()[0] if resp.ok and resp.json() else None
    except:
        profile_user = None
    return render_template('profile.html', profile_user=profile_user)


@profile_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    data = {
        'full_name': request.form.get('full_name'),
        'phone': request.form.get('phone'),
        'bio': request.form.get('bio'),
        'city': request.form.get('city'),
        'religion': request.form.get('religion', 'не указано'),
        'portfolio_link': request.form.get('portfolio_link', ''),
    }
    skills_str = request.form.get('skills', '')
    data['skills'] = [s.strip() for s in skills_str.split(',') if s.strip()] if skills_str else []

    if request.form.get('experience') is not None:
        data['experience'] = request.form.get('experience')
    desired_payment = request.form.get('desired_payment')
    if desired_payment and desired_payment.lower() != 'none':
        try:
            data['desired_payment'] = float(desired_payment)
        except ValueError:
            pass

    # Поля ИНН и самозанятого (юридически значимые данные)
    inn = request.form.get('inn', '')
    if inn:
        if not inn.isdigit() or len(inn) != 12:
            flash('ИНН должен содержать ровно 12 цифр', 'danger')
            return redirect(url_for('profile.profile'))
        data['inn'] = inn
    is_self_employed = request.form.get('is_self_employed')
    if is_self_employed is not None:
        data['is_self_employed'] = is_self_employed == 'on'

    photo = request.files.get('photo')
    if photo and photo.filename:
        safe_name = photo.filename.replace(' ', '_')
        file_path = f'{user_id}/{uuid.uuid4()}_{safe_name}'
        photo_url = upload_to_storage('avatars', file_path, photo.read(), photo.content_type)
        if photo_url:
            data['photo_url'] = photo_url
            flash('Фото загружено', 'success')
        else:
            flash('Ошибка загрузки фото', 'danger')

    try:
        supabase_request('PATCH', f'profiles?id=eq.{user_id}', json=data)
        flash('Профиль обновлён', 'success')
    except:
        flash('Не удалось обновить профиль', 'danger')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/delete-photo', methods=['POST'])
@login_required
def delete_photo():
    user_id = session['user_id']
    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'photo_url': None})
    flash('Фото удалено', 'success')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    if not SERVICE_KEY:
        flash('Сервисный ключ не настроен. Удаление невозможно.', 'danger')
        return redirect(url_for('profile.profile'))
    delete_url = f'{SUPABASE_URL}/auth/v1/admin/users/{user_id}'
    resp = requests.delete(delete_url, headers={
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Content-Type': 'application/json'
    }, timeout=10)
    if resp.ok:
        session.clear()
        flash('Ваш аккаунт полностью удалён.', 'success')
        return redirect(url_for('auth.login'))
    else:
        flash(f'Ошибка удаления аккаунта: {resp.text}', 'danger')
        return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not new_password or len(new_password) < 6:
        flash('Пароль должен содержать минимум 6 символов', 'danger')
        return redirect(url_for('profile.profile'))
    if new_password != confirm_password:
        flash('Новые пароли не совпадают', 'danger')
        return redirect(url_for('profile.profile'))

    auth_update_url = f'{SUPABASE_URL}/auth/v1/user'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {session["access_token"]}',
        'Content-Type': 'application/json'
    }
    try:
        resp = requests.put(auth_update_url, headers=headers,
                            json={'password': new_password}, timeout=10)
        if resp.ok:
            flash('Пароль успешно изменён', 'success')
        else:
            error_data = resp.json()
            flash(f'Ошибка смены пароля: {error_data.get("msg", "попробуйте позже")}', 'danger')
    except requests.RequestException:
        flash('Ошибка соединения с сервером', 'danger')

    return redirect(url_for('profile.profile'))


@profile_bp.route('/verify-employer', methods=['GET', 'POST'])
@login_required
def verify_employer():
    if request.method == 'POST':
        supabase_request('PATCH', f'profiles?id=eq.{session["user_id"]}',
                         json={'verification_status': 'pending'})
        flash('Документ отправлен на проверку', 'success')
        return redirect(url_for('profile.profile'))
    return render_template('verify_employer.html')


@profile_bp.route('/profile/<user_id>')
def public_profile(user_id):
    resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
    profile_user = resp.json()[0] if resp.ok and resp.json() else None
    if not profile_user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('jobs.index'))
    return render_template('profile_worker.html', profile_user=profile_user)
