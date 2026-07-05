import uuid as _uuid
import logging
import re
import time as _time
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.config import Config
from app.decorators import rate_limit
from app.utils import postgrest_admin_request, postgrest_request, postgrest_rpc
from app.utils.auth import generate_jwt, login_user_session
from app.utils.redis_client import get_redis_client
from app.utils.security import has_sql_injection
from app.utils.validators import validate_password, validate_inn_checksum
from app.services.auth_service import (
    login_direct_sql,
    login_postgrest,
    get_db_url,
    is_login_locked_out,
    increment_login_attempts,
    clear_login_attempts,
)

auth_bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)

# RFC 5322 упрощённый regex для валидации email
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]*'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

# Устаревший локальный pattern (оставлен для обратной ссылки).
# Используйте has_sql_injection() из app.utils.security.
_SQL_INJECTION_PATTERNS = re.compile(
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC(?:UTE)?|TRUNCATE)"
    r"(?:\s|=|'|\b)",
    re.IGNORECASE
)


def _has_sql_injection(text: str) -> bool:
    """Проверить, содержит ли текст признаки SQL-инъекции.

    Проверяются только ASCII-фрагменты текста, чтобы избежать ложных
    срабатываний на кириллице (например, «Андрей» не должен блокироваться).
    Первичная защита — параметризованные запросы PostgREST.
    Делегирует проверку в has_sql_injection() из app.utils.security.
    """
    # Извлекаем только ASCII-подстроки из текста
    ascii_parts = re.findall(r'[ -~]+', text)
    for part in ascii_parts:
        if has_sql_injection(part, include_and_or=False, include_url_encoded=True):
            return True
    return False


def _generate_jwt(user_id: str, role: str) -> str:
    """Сгенерировать JWT-токен для PostgREST-аутентификации (делегирует в app.utils.auth)."""
    return generate_jwt(user_id, role)


# Максимальные длины полей
_MAX_NAME_LENGTH = 150
_MAX_CITY_LENGTH = 100
_MAX_EMAIL_LENGTH = 254  # RFC 5321

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(fail_open=False)
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')

        # C22: Per-account lockout — проверка блокировки ПЕРЕД проверкой пароля
        # Per-IP rate limit
        ip = request.remote_addr or 'unknown'
        ip_key = f"login_ip:{ip}"
        try:
            redis_client = get_redis_client()
            if redis_client:
                ip_attempts = redis_client.incr(ip_key)
                if ip_attempts == 1:
                    redis_client.expire(ip_key, 3600)  # 1 час
                if ip_attempts > 20:
                    flash('Слишком много попыток с вашего IP. Подождите час.', 'danger')
                    return render_template('login.html')
        except Exception:
            pass  # Redis недоступен — fail-open

        lockout_key = f"login_lockout:{email}"
        attempts_key = f"login_attempts:{email}"
        if is_login_locked_out(lockout_key):
            flash('Аккаунт временно заблокирован. Попробуйте через 15 минут.', 'error')
            return render_template('login.html')
 
        try:
            # Прямой SQL-запрос к БД через psycopg2 (работает и на проде, и на локале,
            # в отличие от PostgREST RPC, который недоступен на Amvera)
            user = login_direct_sql(email, password)
            if user:
                if not user.get('email_verified', True):
                    flash('Подтвердите email перед входом. Проверьте почту.', 'warning')
                    return render_template('login.html')
                # C22: Сброс счётчика попыток при успешном входе
                clear_login_attempts(lockout_key, attempts_key, email)
                login_user_session(user['user_id'], user['role'], email)
                if user.get('role') == 'employer':
                    return redirect(url_for('jobs.my_jobs'))
                else:
                    return redirect(url_for('jobs.index'))
            # Неудачная попытка — инкрементировать счётчик
            increment_login_attempts(lockout_key, attempts_key, email)
            flash('Неверный email или пароль', 'error')
        except RuntimeError as sql_err:
            # Прямой SQL не сработал — пробуем PostgREST fallback
            log.warning("login: direct SQL unavailable for %s, trying PostgREST fallback: %s",
                        email, sql_err)
            try:
                user = login_postgrest(email, password)
                if user:
                    if not user.get('email_verified', True):
                        flash('Подтвердите email перед входом. Проверьте почту.', 'warning')
                        return render_template('login.html')
                    clear_login_attempts(lockout_key, attempts_key, email)
                    login_user_session(user['user_id'], user['role'], email)
                    if user.get('role') == 'employer':
                        return redirect(url_for('jobs.my_jobs'))
                    else:
                        return redirect(url_for('jobs.index'))
                increment_login_attempts(lockout_key, attempts_key, email)
                flash('Неверный email или пароль', 'error')
            except Exception as pgrst_err:
                current_app.logger.error(
                    f"Login error for {email}: direct SQL and PostgREST both failed: {pgrst_err}"
                )
                flash('Ошибка сервера. Попробуйте позже.', 'error')
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash('Ошибка сервера. Попробуйте позже.', 'error')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(fail_open=False)
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '')
        city = request.form.get('city', '').strip()

        # Валидация обязательных полей
        errors = []
        field_errors = {}
        if not full_name:
            errors.append('Укажите полное имя')
            field_errors['full_name'] = 'Укажите полное имя'
        elif len(full_name) > _MAX_NAME_LENGTH:
            msg = f'Полное имя не должно превышать {_MAX_NAME_LENGTH} символов'
            errors.append(msg)
            field_errors['full_name'] = msg
        elif _has_sql_injection(full_name):
            msg = 'Полное имя содержит недопустимые символы'
            errors.append(msg)
            field_errors['full_name'] = msg

        if not email:
            errors.append('Укажите email')
            field_errors['email'] = 'Укажите email'
        elif len(email) > _MAX_EMAIL_LENGTH:
            msg = f'Email не должен превышать {_MAX_EMAIL_LENGTH} символов'
            errors.append(msg)
            field_errors['email'] = msg
        elif not _EMAIL_RE.match(email):
            msg = 'Некорректный формат email'
            errors.append(msg)
            field_errors['email'] = msg
        elif _has_sql_injection(email):
            msg = 'Email содержит недопустимые символы'
            errors.append(msg)
            field_errors['email'] = msg

        if not password:
            errors.append('Укажите пароль')
            field_errors['password'] = 'Укажите пароль'
        else:
            error_msg = validate_password(password)
            if error_msg:
                errors.append(error_msg)
                field_errors['password'] = error_msg

        if role not in ('worker', 'employer'):
            errors.append('Выберите роль')
            field_errors['role'] = 'Выберите роль'

        if city and len(city) > _MAX_CITY_LENGTH:
            msg = f'Город не должен превышать {_MAX_CITY_LENGTH} символов'
            errors.append(msg)
            field_errors['city'] = msg

        inn = request.form.get('inn', '')
        if role == 'worker' and inn:
            if not inn.isdigit() or len(inn) != 12:
                msg = 'ИНН должен содержать ровно 12 цифр'
                errors.append(msg)
                field_errors['inn'] = msg
            elif not validate_inn_checksum(inn):
                msg = 'Некорректный ИНН — проверьте контрольную сумму'
                errors.append(msg)
                field_errors['inn'] = msg

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('register.html', field_errors=field_errors)

        religion_id = request.form.get('religion_id', '')  # новый формат — ID из справочника
        skill_ids = request.form.getlist('skill_ids')  # новый формат — список ID навыков
        portfolio_link = request.form.get('portfolio_link', '')
        skills_str = request.form.get('skills', '')

        # ИНН и согласие самозанятого — опционально (уже провалидированы выше)
        inn = request.form.get('inn', '')
        is_self_employed = request.form.get('is_self_employed') == 'on'

        # Регистрация через RPC (нативная PostgreSQL-аутентификация)
        try:
            resp = postgrest_admin_request('POST', 'rpc/register_user', data={
                'p_email': email,
                'p_password': password,
                'p_full_name': full_name,
                'p_role': role
            })
            if resp.ok:
                # RPC возвращает uuid нового пользователя
                user_id = resp.json()
                if isinstance(user_id, list) and len(user_id) > 0:
                    user_id = user_id[0] if isinstance(user_id[0], str) else user_id[0].get('register_user')

                # Обновить профиль дополнительными данными
                from datetime import datetime, timezone
                update_data = {
                    'city': city,
                    'portfolio_link': portfolio_link,
                    'consented_at': datetime.now(timezone.utc).isoformat(),
                }
                if role == 'worker':
                    if inn:
                        update_data['inn'] = inn
                    if is_self_employed:
                        update_data['is_self_employed'] = is_self_employed
                    desired_payment = request.form.get('desired_payment', '0')
                    try:
                        update_data['desired_payment'] = float(desired_payment) if desired_payment else 0
                    except ValueError:
                        update_data['desired_payment'] = 0
                    update_data['experience'] = request.form.get('experience', '')
                    contact = request.form.get('contact', '').strip()
                    update_data['contact'] = contact if len(contact) >= 3 else None

                patch_resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}', json=update_data)
                if not patch_resp.ok:
                    log.error('Failed to update profile for user %s: %s', user_id, patch_resp.text)

                # Сохраняем навыки через user_skills (с валидацией UUID)
                if role == 'worker' and skill_ids:
                    for sid in skill_ids:
                        sid = sid.strip()
                        if not sid:
                            continue
                        try:
                            _uuid.UUID(sid)
                        except (ValueError, AttributeError):
                            continue
                        postgrest_admin_request('POST', 'user_skills', json={
                            'user_id': user_id, 'skill_id': sid
                        })

                # Email verification — отправка токена вместо авто-логина
                verification_token = _generate_email_verification_token(email)
                verification_url = url_for('auth.verify_email', token=verification_token, _external=True)

                # Асинхронная отправка через Celery
                from app.tasks.email_tasks import send_email_notification
                send_email_notification.delay(
                    user_id=str(user_id),
                    notification_id=0,
                    user_email=email,
                    user_name=full_name,
                    notification_text=f'Для подтверждения email перейдите по ссылке:\n\n{verification_url}\n\nСсылка действительна 24 часа.',
                    notification_type='email_verification',
                    notification_url=verification_url
                )

                flash('Регистрация успешна. Проверьте почту для подтверждения email.', 'info')
                return redirect(url_for('auth.login'))
            else:
                error_msg = 'Ошибка регистрации'
                err_data = {}
                try:
                    err_data = resp.json()
                    if isinstance(err_data, dict):
                        error_msg = err_data.get('message') or err_data.get('msg') or error_msg
                except Exception:
                    pass
                if isinstance(err_data, dict) and 'email_exists' in err_data.get('message', '').lower():
                    error_msg = 'Пользователь с таким email уже зарегистрирован'
                flash(error_msg, 'danger')
        except Exception as e:
            log.error('Registration error: %s', e)
            flash('Ошибка соединения с сервером', 'danger')
    return render_template('register.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    log.info('Logout: user_id=%s, role=%s', session.get('user_id'), session.get('role'))
    if current_app.config.get('TESTING'):
        session.clear()
        flash('Вы вышли из системы', 'success')
        return redirect(url_for('jobs.index'))
    session.clear()
    flash('Вы вышли из системы', 'success')
    resp = redirect(url_for('auth.login'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


# ═══════════════════════════════════════════════════════════════
# C25: Flow «забыл пароль»
# ═══════════════════════════════════════════════════════════════

_PASSWORD_RESET_SALT = 'password-reset'
_PASSWORD_RESET_MAX_AGE = 3600  # 1 час

_EMAIL_VERIFICATION_SALT = 'email-verify'
_EMAIL_VERIFICATION_MAX_AGE = 86400  # 24 часа


def _generate_email_verification_token(email: str) -> str:
    """Сгенерировать токен для подтверждения email (отдельный salt)."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_EMAIL_VERIFICATION_SALT)
    return s.dumps(email)


def _verify_email_verification_token(token: str) -> str | None:
    """Проверить токен подтверждения email. Возвращает email или None."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_EMAIL_VERIFICATION_SALT)
    try:
        return s.loads(token, max_age=_EMAIL_VERIFICATION_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


def _make_serializer() -> URLSafeTimedSerializer:
    """Создать сериализатор для токенов сброса пароля."""
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        salt=_PASSWORD_RESET_SALT
    )


def _generate_reset_token(email: str) -> str:
    """Сгенерировать токен для сброса пароля (срок действия 1 час)."""
    s = _make_serializer()
    return s.dumps(email)


def _verify_reset_token(token: str, max_age: int = _PASSWORD_RESET_MAX_AGE) -> str | None:
    """Проверить токен сброса пароля. Возвращает email или None."""
    s = _make_serializer()
    try:
        return s.loads(token, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None


# Rate-limit на запрос сброса: 1 запрос в 5 минут на email
_RESET_COOLDOWN = 300  # 5 минут


def _check_reset_rate_limit(email: str) -> bool:
    """Проверить rate-limit для запроса сброса пароля.

    Returns:
        True если лимит превышен, False если можно отправить.
    """
    key = f"password_reset:{email}"
    try:
        client = get_redis_client()
        if client is None:
            return False
        return client.exists(key) > 0
    except Exception:
        return False


def _set_reset_rate_limit(email: str) -> None:
    """Установить rate-limit для запроса сброса пароля."""
    key = f"password_reset:{email}"
    try:
        client = get_redis_client()
        if client is not None:
            client.setex(key, _RESET_COOLDOWN, '1')
    except Exception:
        pass


@auth_bp.route('/password-reset/request', methods=['GET', 'POST'])
def password_reset_request():
    """Форма запроса сброса пароля: отправка ссылки с токеном на email."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email or not _EMAIL_RE.match(email):
            flash('Укажите корректный email', 'danger')
            return render_template('password_reset_request.html')

        # Rate-limit: 1 запрос в 5 минут на email
        if _check_reset_rate_limit(email):
            flash('Ссылка для сброса пароля уже была отправлена. Попробуйте через 5 минут.', 'warning')
            return render_template('password_reset_request.html')

        # Проверить, существует ли пользователь с таким email
        check_resp = postgrest_admin_request('GET', f'profiles?email=eq.{email}&select=id')
        if not check_resp.ok or not check_resp.json():
            # Не раскрываем, существует ли email (безопасность)
            flash('Если аккаунт с таким email существует, ссылка для сброса пароля отправлена.', 'success')
            return redirect(url_for('auth.login'))

        # Генерируем токен и ссылку
        token = _generate_reset_token(email)
        reset_url = url_for('auth.password_reset_confirm', token=token, _external=True)

        # Устанавливаем rate-limit
        _set_reset_rate_limit(email)

        # Отправляем email через сервис
        try:
            from app.services.email_service import send_email
            send_email(
                to_email=email,
                subject='Сброс пароля — Trudnik',
                body=f'Для сброса пароля перейдите по ссылке:\n\n{reset_url}\n\n'
                     f'Ссылка действительна в течение 1 часа.\n'
                     f'Если вы не запрашивали сброс пароля, проигнорируйте это письмо.',
                html_body=f'<p>Для сброса пароля перейдите по ссылке:</p>'
                          f'<p><a href="{reset_url}">{reset_url}</a></p>'
                          f'<p>Ссылка действительна в течение 1 часа.</p>'
                          f'<p>Если вы не запрашивали сброс пароля, проигнорируйте это письмо.</p>'
            )
            log.info('Password reset email sent to %s', email)
        except Exception as e:
            log.error('Failed to send password reset email to %s: %s', email, e)

        # Всегда показываем одинаковое сообщение (безопасность)
        flash('Если аккаунт с таким email существует, ссылка для сброса пароля отправлена.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('password_reset_request.html')


@auth_bp.route('/password-reset/confirm/<token>', methods=['GET', 'POST'])
def password_reset_confirm(token):
    """Форма нового пароля после перехода по ссылке из email."""
    email = _verify_reset_token(token)
    if not email:
        flash('Ссылка для сброса пароля недействительна или истекла. Запросите новую.', 'danger')
        return redirect(url_for('auth.password_reset_request'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        error_msg = validate_password(new_password)
        if error_msg:
            flash(error_msg, 'danger')
            return render_template('password_reset_confirm.html', token=token)

        if new_password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return render_template('password_reset_confirm.html', token=token)

        # Обновить пароль через RPC
        try:
            resp = postgrest_admin_request('POST', 'rpc/change_password', json={
                'p_email': email,
                'p_new_password': new_password
            })
            if resp.ok:
                result = resp.json()
                success = False
                if isinstance(result, list) and len(result) > 0:
                    success = result[0] if isinstance(result[0], bool) else result[0].get('change_password', False)
                elif isinstance(result, dict):
                    success = result.get('success', False)

                if success:
                    flash('Пароль успешно изменён. Теперь вы можете войти.', 'success')
                    return redirect(url_for('auth.login'))
                else:
                    flash('Не удалось изменить пароль. Возможно, аккаунт не найден.', 'danger')
            else:
                flash('Ошибка при смене пароля. Попробуйте позже.', 'danger')
        except Exception as e:
            log.error('Password reset confirm error for %s: %s', email, e)
            flash('Ошибка соединения с сервером', 'danger')

    return render_template('password_reset_confirm.html', token=token)


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    """Подтверждение email по токену из письма."""
    email = _verify_email_verification_token(token)
    if not email:
        flash('Ссылка недействительна или истекла', 'danger')
        return redirect(url_for('auth.register'))
    resp = postgrest_admin_request('PATCH',
        f'profiles?email=eq.{email}', json={'email_verified': True})
    if resp.ok:
        flash('Email подтверждён. Теперь вы можете войти.', 'success')
        return redirect(url_for('auth.login'))
    flash('Ошибка подтверждения email', 'danger')
    return redirect(url_for('auth.register'))
