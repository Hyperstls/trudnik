import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.config import Config
from app.decorators import login_required, rate_limit, validate_uuid
from app.services.storage_service import upload_photo
from app.utils import is_circuit_open, postgrest_admin_request, postgrest_request, postgrest_rpc, upload_to_storage
from app.utils.helpers import assert_postgrest_ok
from app.utils.redis_client import get_redis_client
from app.utils.validators import validate_password, validate_inn_checksum

profile_bp = Blueprint('profile', __name__)

# Публичные поля профиля (C27, C28)
PUBLIC_PROFILE_FIELDS = 'id,role,created_at,updated_at,is_self_employed,email_public,rating,full_name,photo_url,age,bio,city,experience,desired_payment,verification_status,total_reviews,religion_id,portfolio_link'

# Допустимые расширения для загрузки фото
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_PHOTO_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB

# Сигнатуры для MIME-валидации документов верификации
_DOCUMENT_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'%PDF-': 'application/pdf',
}


def _check_document_mime(data: bytes) -> str | None:
    """Проверить MIME-тип документа по magic bytes (PDF, JPEG, PNG).

    Args:
        data: бинарные данные файла.

    Returns:
        MIME-тип (напр. 'image/jpeg') или None если формат недопустим.
    """
    if not data:
        return None
    for sig, mime in _DOCUMENT_SIGNATURES.items():
        if data[:len(sig)] == sig:
            return mime
    return None


@profile_bp.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    try:
        resp = postgrest_request('GET', f'profiles?id=eq.{user_id}&select={PUBLIC_PROFILE_FIELDS}')
        if is_circuit_open(resp):
            flash('Сервис временно недоступен. Пожалуйста, попробуйте позже.', 'warning')
            profile_user = None
        elif resp.ok and resp.json():
            try:
                profile_user = resp.json()[0]
            except (IndexError, TypeError):
                profile_user = None
        else:
            current_app.logger.error('Error loading profile for user %s: status=%s', user_id, resp.status_code)
            profile_user = None
    except Exception:
        current_app.logger.exception('Error loading profile for user %s', user_id)
        profile_user = None

    # Текущие навыки пользователя (из user_skills) — для предвыбора в форме
    current_skill_ids: list[str] = []
    if profile_user:
        try:
            sk_resp = postgrest_request('GET', f'user_skills?user_id=eq.{user_id}&select=skill_id')
            if sk_resp.ok and sk_resp.json():
                current_skill_ids = [s.get('skill_id') for s in sk_resp.json() if s.get('skill_id')]
        except Exception:
            pass
    return render_template('profile.html', profile_user=profile_user, current_skill_ids=current_skill_ids)


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
        'portfolio_link': request.form.get('portfolio_link', ''),
    }
    skills_str = request.form.get('skills', '')
    # skill_ids может прийти как несколько полей (getlist) либо как одно поле
    # со списком ID через запятую (страница профиля) — поддерживаем оба варианта.
    skill_ids: list[str] = []
    for _v in request.form.getlist('skill_ids'):
        for _part in str(_v).split(','):
            _part = _part.strip()
            if _part:
                skill_ids.append(_part)

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
        if not validate_inn_checksum(inn):
            flash('Некорректный ИНН (ошибка контрольной суммы)', 'danger')
            return redirect(url_for('profile.profile'))
        data['inn'] = inn
    is_self_employed = request.form.get('is_self_employed')
    if is_self_employed is not None:
        data['is_self_employed'] = is_self_employed == 'on'

    contact = request.form.get('contact', '').strip()
    if contact:
        import re
        if len(contact) < 3:
            flash('Контакт должен содержать минимум 3 символа', 'danger')
            return redirect(url_for('profile.profile'))
        if not any([
            bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', contact)),
            bool(re.match(r'^\+?\d[\d\-\s\(\)]{4,}$', contact)),
            bool(re.match(r'^@?\w{3,}$', contact)),
            len(contact) >= 5,
        ]):
            flash('Введите корректный контакт: email, телефон или никнейм', 'danger')
            return redirect(url_for('profile.profile'))
    data['contact'] = contact if len(contact) >= 3 else None

    # Вероисповедание (справочник religions)
    religion_id = request.form.get('religion_id', '').strip()
    if religion_id:
        try:
            uuid.UUID(religion_id)
            data['religion_id'] = religion_id
        except (ValueError, AttributeError):
            flash('Некорректное вероисповедание', 'danger')
            return redirect(url_for('profile.profile'))
    else:
        # Пустое значение — сбросить вероисповедание
        data['religion_id'] = None

    photo = request.files.get('photo')
    if photo and photo.filename:
        # C29: MIME-валидация через upload_photo (magic bytes для JPEG, PNG, WebP)
        # + проверка размера (max 5MB)
        photo_data = photo.read()
        if len(photo_data) > MAX_PHOTO_SIZE:
            flash(f'Файл слишком большой (максимум {Config.MAX_PHOTO_SIZE_MB} МБ)', 'danger')
            return redirect(url_for('profile.profile'))

        photo_url = upload_photo(photo_data, bucket='avatars', folder=user_id)
        if photo_url:
            data['photo_url'] = photo_url
            flash('Фото загружено', 'success')
        else:
            flash('Ошибка загрузки фото. Проверьте формат (JPEG, PNG, WebP) и размер файла.', 'danger')

    try:
        update_resp = postgrest_request('PATCH', f'profiles?id=eq.{user_id}', json=data)
        if assert_postgrest_ok(update_resp, 'обновление профиля'):
            flash('Профиль обновлён', 'success')

        # Синхронизация навыков через user_skills (вместо profiles.skills)
        if skill_ids:
            # Удаляем старые связи
            postgrest_request('DELETE', f'user_skills?user_id=eq.{user_id}')
            # Вставляем новые
            for sid in skill_ids:
                sid = sid.strip()
                if not sid:
                    continue
                try:
                    uuid.UUID(sid)
                except (ValueError, AttributeError):
                    continue
                postgrest_request('POST', 'user_skills', json={
                    'user_id': user_id, 'skill_id': sid
                })
    except Exception:
        current_app.logger.exception('Error updating profile for user %s', user_id)
        flash('Не удалось обновить профиль', 'danger')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/delete-photo', methods=['POST'])
@login_required
def delete_photo():
    user_id = session['user_id']
    # Получаем старый photo_url до удаления
    old_photo_url = None
    get_resp = postgrest_request('GET', f'profiles?id=eq.{user_id}&select=photo_url')
    if get_resp.ok and get_resp.json():
        data = get_resp.json()
        if isinstance(data, list) and data:
            old_photo_url = data[0].get('photo_url')

    del_resp = postgrest_request('PATCH', f'profiles?id=eq.{user_id}', json={'photo_url': None})
    if assert_postgrest_ok(del_resp, 'удаление фото профиля'):
        # Удаление файла с диска
        if old_photo_url:
            from app.services.storage_service import delete_from_storage
            # Извлечь путь из URL: /uploads/avatars/... → avatars/...
            photo_path = old_photo_url.replace('/uploads/', '', 1) if old_photo_url.startswith('/uploads/') else None
            if photo_path:
                # Разделить на bucket и file_path (первый сегмент — bucket)
                parts = photo_path.split('/', 1)
                if len(parts) == 2:
                    bucket, file_path = parts
                    # Удалить query-параметры из file_path
                    file_path = file_path.split('?')[0]
                    delete_from_storage(bucket, file_path)
        flash('Фото удалено', 'success')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']

    # Rate-limit: 1 запрос в час (B29: atomic SET NX EX вместо exists+setex)
    key = f'delete_account:{user_id}'
    try:
        redis_client = get_redis_client()
        if redis_client:
            if not redis_client.set(key, '1', nx=True, ex=3600):
                flash('Попробуйте позже (не чаще раза в час)', 'warning')
                return redirect(url_for('profile.profile'))
    except Exception as e:
        current_app.logger.warning('delete_account rate-limit check failed: %s', e, exc_info=True)

    # Каскадное удаление через RPC (этап 4.4)
    try:
        rpc_result = postgrest_rpc('delete_user_cascade', {'p_user_id': user_id}, use_admin=True)
        if not rpc_result.ok:
            current_app.logger.error(
                "Profile delete account RPC: failed for %s: status=%s text=%s",
                user_id, rpc_result.status_code, (rpc_result.text or '')[:200]
            )
            flash('Ошибка удаления аккаунта. Пожалуйста, попробуйте позже.', 'danger')
            return redirect(url_for('profile.profile'))
    except Exception as e:
        current_app.logger.exception(
            "Profile delete account RPC: exception for %s: %s",
            user_id, e
        )
        flash('Ошибка удаления аккаунта. Сервис временно недоступен.', 'danger')
        return redirect(url_for('profile.profile'))

    session.clear()
    flash('Ваш аккаунт полностью удалён.', 'success')
    return redirect(url_for('auth.login'))


@profile_bp.route('/profile/change-password', methods=['POST'])
@login_required
@rate_limit
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_password:
        flash('Укажите текущий пароль', 'danger')
        return redirect(url_for('profile.profile'))
    if not new_password:
        flash('Укажите новый пароль', 'danger')
        return redirect(url_for('profile.profile'))
    error_msg = validate_password(new_password)
    if error_msg:
        flash(error_msg, 'danger')
        return redirect(url_for('profile.profile'))
    if new_password != confirm_password:
        flash('Новые пароли не совпадают', 'danger')
        return redirect(url_for('profile.profile'))

    user_id = session['user_id']
    try:
        resp = postgrest_request('POST', 'rpc/change_password', json={
            'p_user_id': user_id,
            'p_old_password': current_password,
            'p_new_password': new_password
        })
        if resp.ok:
            result = resp.json()
            if isinstance(result, list) and len(result) > 0:
                success = result[0] if isinstance(result[0], bool) else result[0].get('change_password', False)
            else:
                success = False
            if success:
                # Инвалидируем текущий jti перед выпуском нового токена
                old_jti = session.get('jti')
                if old_jti:
                    from app.utils.auth import blacklist_jti
                    blacklist_jti(old_jti)
                
                # Обновляем password_changed_at в профиле
                from datetime import datetime, timezone
                postgrest_request('PATCH', f'profiles?id=eq.{user_id}', 
                    json={'password_changed_at': datetime.now(timezone.utc).isoformat()})
                
                # Инвалидация старой сессии и выпуск нового JWT
                from app.utils.auth import login_user_session
                email = session.get('email', '')
                role = session.get('role', 'authenticated')
                login_user_session(user_id, role, email)
                flash('Пароль успешно изменён', 'success')
            else:
                flash('Неверный текущий пароль', 'danger')
        else:
            flash('Ошибка смены пароля', 'danger')
    except Exception:
        current_app.logger.exception('Error changing password for user %s', user_id)
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
                file_data = file.read()
                # C30: MIME-валидация через magic bytes (PDF, JPEG, PNG)
                allowed_mime = _check_document_mime(file_data)
                if not allowed_mime:
                    flash('Недопустимый формат файла. Разрешены PDF, JPG, PNG.', 'danger')
                    return redirect(url_for('profile.verify_employer'))

                ext = allowed_mime.split('/')[-1] if '/' in allowed_mime else 'pdf'
                if ext == 'jpeg':
                    ext = 'jpg'
                path = f'verification/{user_id}/{uuid.uuid4().hex}.{ext}'
                url = upload_to_storage('verification-docs', path, file_data, allowed_mime)
                if url:
                    data['verification_doc_url'] = url
                else:
                    flash('Ошибка загрузки документа', 'danger')
                    return redirect(url_for('profile.verify_employer'))
            except Exception as e:
                flash(f'Ошибка при загрузке: {str(e)}', 'danger')
                return redirect(url_for('profile.verify_employer'))

        verify_resp = postgrest_request('PATCH', f'profiles?id=eq.{user_id}', json=data)
        if assert_postgrest_ok(verify_resp, 'отправка заявки на верификацию'):
            flash('Заявка на верификацию отправлена', 'success')
        return redirect(url_for('profile.profile'))
    return render_template('verify_employer.html')


@profile_bp.route('/profile/<user_id>')
@validate_uuid('user_id')
def public_profile(user_id):
    resp = postgrest_request('GET', f'profiles?id=eq.{user_id}&select={PUBLIC_PROFILE_FIELDS}')
    profile_user = resp.json()[0] if resp.ok and resp.json() else None
    if not profile_user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('jobs.index'))
    return render_template('profile_worker.html', profile_user=profile_user)
