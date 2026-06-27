import os
import uuid as _uuid
import logging
import re
import time as _time
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.config import Config
from app.decorators import rate_limit
from app.utils import postgrest_admin_request, postgrest_public_rpc, postgrest_request, postgrest_rpc
from app.utils.auth import generate_jwt
from app.utils.redis_client import get_redis_client
from app.utils.security import has_sql_injection
from app.utils.validators import validate_password, validate_inn_checksum

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


def _login_user_session(user_id: str, role: str, email: str) -> None:
    """Сохранить данные пользователя в сессии после успешного логина."""
    session.permanent = True
    session['access_token'] = _generate_jwt(user_id, role)
    session['refresh_token'] = 'jwt'  # для совместимости с refresh_access_token
    session['user_id'] = user_id
    session['role'] = role
    session['email'] = email
    session.modified = True

# Максимальные длины полей
_MAX_NAME_LENGTH = 150
_MAX_CITY_LENGTH = 100
_MAX_EMAIL_LENGTH = 254  # RFC 5321


def _get_db_url():
    """Получить URL для прямого подключения к PostgreSQL (как в admin.py reset_users).

    Приоритет:
    1. DATABASE_URL из переменных окружения
    2. PGDATABASE_URL
    3. Config.DATABASE_URL (собранный из PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE)
    4. Отдельные переменные PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE
    """
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
    if db_url:
        log.debug("login: using DATABASE_URL from env: %s",
                  db_url[:db_url.index('@') + 1] + '***' if '@' in db_url else db_url)
        return db_url
    # Fallback на Config.DATABASE_URL (собирается из отдельных PG-переменных)
    config_url = Config.DATABASE_URL
    if config_url:
        log.debug("login: using Config.DATABASE_URL: %s",
                  config_url[:config_url.index('@') + 1] + '***' if '@' in config_url else config_url)
        return config_url
    # Последняя попытка — собрать из отдельных переменных
    pg_user = os.environ.get('PGUSER', '')
    pg_password = os.environ.get('PGPASSWORD', '')
    pg_host = os.environ.get('PGHOST', '')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_database = os.environ.get('PGDATABASE', '')
    if all([pg_user, pg_password, pg_host, pg_database]):
        return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
    log.warning("login: no DATABASE_URL configured (env DATABASE_URL, PGDATABASE_URL, "
                "or PGUSER/PGPASSWORD/PGHOST/PGDATABASE)")
    return ''

def _login_direct_sql(email: str, password: str) -> dict | None:
    """Проверить email/password через прямое SQL-подключение (в обход PostgREST RPC).

    Использует pgcrypto crypt() для проверки хеша пароля.
    Возвращает dict с {user_id, email, role, full_name} или None при ошибке/неверном пароле.

    При ошибке подключения выбрасывает исключение с понятным описанием,
    чтобы вызывающий код мог попробовать fallback (PostgREST).
    """
    db_url = _get_db_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL не задан. Установите переменную окружения DATABASE_URL "
            "или PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE."
        )
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, role, full_name
            FROM profiles
            WHERE email = %s AND password_hash = crypt(%s, password_hash)
        """, (email, password))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {'user_id': str(row[0]), 'email': row[1], 'role': row[2], 'full_name': row[3]}
        log.info("login: invalid credentials for %s (direct SQL)", email)
        return None
    except ImportError:
        log.error("login: psycopg2 not installed — cannot use direct SQL")
        raise RuntimeError(
            "psycopg2 не установлен. Установите: pip install psycopg2-binary"
        )
    except Exception as e:
        log.error("login: direct SQL connection failed for %s: %s", email, e)
        raise RuntimeError(
            f"Не удалось подключиться к БД напрямую: {e}. "
            f"Проверьте DATABASE_URL (порт, хост, пароль). "
            f"PostgreSQL должен быть доступен."
        )


def _login_postgrest(email: str, password: str) -> dict | None:
    """Fallback: проверить email/password через PostgREST RPC login_user.

    Используется если прямой SQL недоступен (например, нет psycopg2 или БД не на локалхосте).
    Возвращает dict с {user_id, email, role, full_name} или None при ошибке/неверном пароле.
    """
    try:
        from app.utils import postgrest_admin_request
        resp = postgrest_admin_request('POST', 'rpc/login_user', data={
            'p_email': email,
            'p_password': password
        })
        if resp and resp.ok:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                user = data[0]
                return {
                    'user_id': str(user.get('id', user.get('user_id', ''))),
                    'email': user.get('email', email),
                    'role': user.get('role', 'worker'),
                    'full_name': user.get('full_name', '')
                }
            elif isinstance(data, dict):
                return {
                    'user_id': str(data.get('id', data.get('user_id', ''))),
                    'email': data.get('email', email),
                    'role': data.get('role', 'worker'),
                    'full_name': data.get('full_name', '')
                }
        log.info("login: invalid credentials for %s (PostgREST fallback)", email)
        return None
    except Exception as e:
        log.error("login: PostgREST fallback also failed for %s: %s", email, e)
        return None

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(fail_open=False)
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # C22: Per-account lockout — проверка блокировки ПЕРЕД проверкой пароля
        lockout_key = f"login_lockout:{email}"
        attempts_key = f"login_attempts:{email}"
        if _is_login_locked_out(lockout_key):
            flash('Аккаунт временно заблокирован. Попробуйте через 15 минут.', 'error')
            return render_template('login.html')

        try:
            # Прямой SQL-запрос к БД через psycopg2 (работает и на проде, и на локале,
            # в отличие от PostgREST RPC, который недоступен на Amvera)
            user = _login_direct_sql(email, password)
            if user:
                # C22: Сброс счётчика попыток при успешном входе
                _clear_login_attempts(lockout_key, attempts_key)
                _login_user_session(user['user_id'], user['role'], email)
                if user.get('role') == 'employer':
                    return redirect(url_for('jobs.my_jobs'))
                else:
                    return redirect(url_for('jobs.index'))
            # Неудачная попытка — инкрементировать счётчик
            _increment_login_attempts(lockout_key, attempts_key, email)
            flash('Неверный email или пароль', 'error')
        except RuntimeError as sql_err:
            # Прямой SQL не сработал — пробуем PostgREST fallback
            log.warning("login: direct SQL unavailable for %s, trying PostgREST fallback: %s",
                        email, sql_err)
            try:
                user = _login_postgrest(email, password)
                if user:
                    _clear_login_attempts(lockout_key, attempts_key)
                    _login_user_session(user['user_id'], user['role'], email)
                    if user.get('role') == 'employer':
                        return redirect(url_for('jobs.my_jobs'))
                    else:
                        return redirect(url_for('jobs.index'))
                _increment_login_attempts(lockout_key, attempts_key, email)
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


def _is_login_locked_out(lockout_key: str) -> bool:
    """Проверить, заблокирован ли аккаунт по ключу блокировки."""
    try:
        client = get_redis_client()
        if client is None:
            return False
        return client.exists(lockout_key) > 0
    except Exception:
        return False


def _increment_login_attempts(lockout_key: str, attempts_key: str, email: str) -> None:
    """Инкрементировать счётчик неудачных попыток входа. При 5 попытках — блокировка на 15 минут."""
    try:
        client = get_redis_client()
        if client is None:
            return
        attempts = client.incr(attempts_key)
        if attempts == 1:
            client.expire(attempts_key, 900)  # TTL для счётчика — 15 минут
        if attempts >= 5:
            client.setex(lockout_key, 900, '1')
            log.warning('Account locked out: %s (5 failed attempts)', email)
    except Exception as e:
        log.warning('Failed to increment login attempts for %s: %s', email, e)


def _clear_login_attempts(lockout_key: str, attempts_key: str) -> None:
    """Сбросить счётчик попыток и блокировку после успешного входа."""
    try:
        client = get_redis_client()
        if client is None:
            return
        client.delete(attempts_key, lockout_key)
    except Exception:
        pass


@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(fail_open=False)
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
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

        religion = request.form.get('religion', 'не указано')
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
                update_data = {
                    'city': city,
                    'religion': religion,
                    'portfolio_link': portfolio_link,
                    'skills': [s.strip() for s in skills_str.split(',') if s.strip()] if skills_str else []
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

                # Автоматический логин после регистрации
                _login_user_session(str(user_id), role, email)

                if role == 'employer':
                    return redirect(url_for('jobs.my_jobs'))
                else:
                    return redirect(url_for('jobs.index'))
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
        email = request.form.get('email', '').strip()

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
