import uuid

import requests
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.config import Config
from app.decorators import login_required
from app.utils import SERVICE_KEY, SUPABASE_KEY, SUPABASE_URL, supabase_admin_request, supabase_request, supabase_rpc, upload_to_storage

profile_bp = Blueprint('profile', __name__)

# Допустимые расширения для загрузки фото
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_PHOTO_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB


@profile_bp.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    try:
        resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
        profile_user = resp.json()[0] if resp.ok and resp.json() else None
    except Exception:
        current_app.logger.exception('Error loading profile for user %s', user_id)
        profile_user = None
    return render_template('profile.html', profile_user=profile_user)


@profile_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    bio = request.form.get('bio', '')

    # Серверная валидация длины поля «О себе»
    if len(bio) > 1000:
        flash('Поле «О себе» слишком длинное (максимум 1000 символов)', 'danger')
        return redirect(url_for('profile.profile'))

    data = {
        'full_name': request.form.get('full_name'),
        'phone': request.form.get('phone'),
        'bio': bio,
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

    contact = request.form.get('contact', '').strip()
    data['contact'] = contact if len(contact) >= 3 else None

    photo = request.files.get('photo')
    if photo and photo.filename:
        # Проверка расширения: только изображения
        ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
        if ext not in ALLOWED_PHOTO_EXTENSIONS:
            flash(f'Недопустимый формат файла. Разрешены: {", ".join(sorted(ALLOWED_PHOTO_EXTENSIONS))}', 'danger')
            return redirect(url_for('profile.profile'))

        # Проверка размера файла (до чтения)
        photo_data = photo.read()
        if len(photo_data) > MAX_PHOTO_SIZE:
            flash(f'Файл слишком большой (максимум {Config.MAX_PHOTO_SIZE_MB} МБ)', 'danger')
            return redirect(url_for('profile.profile'))

        # Безопасное имя файла: uuid + secure_filename
        safe_name = secure_filename(photo.filename) or f'{uuid.uuid4().hex}.{ext}'
        file_path = f'{user_id}/{uuid.uuid4().hex}_{safe_name}'
        photo_url = upload_to_storage('avatars', file_path, photo_data, photo.content_type)
        if photo_url:
            data['photo_url'] = photo_url
            flash('Фото загружено', 'success')
        else:
            flash('Ошибка загрузки фото', 'danger')

    try:
        supabase_request('PATCH', f'profiles?id=eq.{user_id}', json=data)
        flash('Профиль обновлён', 'success')
    except Exception:
        current_app.logger.exception('Error updating profile for user %s', user_id)
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

    # Каскадное удаление через RPC (этап 4.4)
    rpc_result = supabase_rpc('delete_user_cascade', {'p_user_id': user_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            "Profile delete account RPC: failed for %s: status=%s text=%s",
            user_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )

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
        user_id = session['user_id']
        data = {'verification_status': 'pending'}

        # Upload document if provided
        file = request.files.get('document')
        if file and file.filename:
            try:
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext not in ('pdf', 'jpg', 'jpeg', 'png'):
                    flash('Недопустимый формат файла. Разрешены PDF, JPG, PNG.', 'danger')
                    return redirect(url_for('profile.verify_employer'))
                path = f'verification/{user_id}/{uuid.uuid4().hex}.{ext}'
                url = upload_to_storage('verification-docs', path, file.read(), file.content_type)
                if url:
                    data['verification_doc_url'] = url
                else:
                    flash('Ошибка загрузки документа', 'danger')
                    return redirect(url_for('profile.verify_employer'))
            except Exception as e:
                flash(f'Ошибка при загрузке: {str(e)}', 'danger')
                return redirect(url_for('profile.verify_employer'))

        supabase_request('PATCH', f'profiles?id=eq.{user_id}', json=data)
        flash('Заявка на верификацию отправлена', 'success')
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
