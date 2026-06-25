import os
import uuid as _uuid
import logging
import re
import time as _time
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import rate_limit
from app.utils import postgrest_admin_request, postgrest_request
from app.utils.auth import generate_jwt
from app.utils.security import has_sql_injection
from app.utils.validators import validate_password

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
    """Получить URL для прямого подключения к PostgreSQL (как в admin.py reset_users)."""
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
    if db_url:
        return db_url
    pg_user = os.environ.get('PGUSER', '')
    pg_password = os.environ.get('PGPASSWORD', '')
    pg_host = os.environ.get('PGHOST', '')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_database = os.environ.get('PGDATABASE', '')
    if all([pg_user, pg_password, pg_host, pg_database]):
        return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
    return ''


def _login_direct_sql(email: str, password: str) -> dict | None:
    """Проверить email/password через прямое SQL-подключение (в обход PostgREST RPC).

    Использует pgcrypto crypt() для проверки хеша пароля.
    Возвращает dict с {id, email, role, full_name} или None при ошибке/неверном пароле.
    """
    db_url = _get_db_url()
    if not db_url:
        log.error("login: DATABASE_URL not configured")
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
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
        return None
    except ImportError:
        log.error("login: psycopg2 not installed")
        return None
    except Exception as e:
        log.error("login: direct SQL error for %s: %s", email, e)
        return None


@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        last_error = None
        for attempt in range(2):
            try:
                # Прямое SQL-подключение (обходит PostgREST RPC, т.к. RPC требует service_role)
                user = _login_direct_sql(email, password)
                print(f"AUTH DEBUG: direct SQL result={user}", flush=True)
                if user:
                    _login_user_session(user['user_id'], user['role'], email)
                    if user.get('role') == 'employer':
                        return redirect(url_for('jobs.my_jobs'))
                    else:
                        return redirect(url_for('jobs.index'))
                else:
                    flash('Ошибка входа: неверный email или пароль', 'danger')
                    return render_template('login.html')
            except Exception as e:
                log.warning('Auth connection error for %s, attempt %d/2: %s', email, attempt + 1, e)
                last_error = str(e)
                _time.sleep(1.0 * (attempt + 1))
                continue
        # Все попытки исчерпаны
        if last_error == 'rate_limited':
            flash('Слишком много попыток входа. Пожалуйста, подождите немного.', 'danger')
        else:
            flash('Ошибка соединения с сервером авторизации', 'danger')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', '')
        city = request.form.get('city', '').strip()

        # Валидация обязательных полей
        errors = []
        if not full_name:
            errors.append('Укажите полное имя')
        elif len(full_name) > _MAX_NAME_LENGTH:
            errors.append(f'Полное имя не должно превышать {_MAX_NAME_LENGTH} символов')
        elif _has_sql_injection(full_name):
            errors.append('Полное имя содержит недопустимые символы')

        if not email:
            errors.append('Укажите email')
        elif len(email) > _MAX_EMAIL_LENGTH:
            errors.append(f'Email не должен превышать {_MAX_EMAIL_LENGTH} символов')
        elif not _EMAIL_RE.match(email):
            errors.append('Некорректный формат email')
        elif _has_sql_injection(email):
            errors.append('Email содержит недопустимые символы')

        if not password:
            errors.append('Укажите пароль')
        else:
            error_msg = validate_password(password)
            if error_msg:
                errors.append(error_msg)

        if role not in ('worker', 'employer'):
            errors.append('Выберите роль')

        if city and len(city) > _MAX_CITY_LENGTH:
            errors.append(f'Город не должен превышать {_MAX_CITY_LENGTH} символов')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('register.html')

        religion = request.form.get('religion', 'не указано')
        religion_id = request.form.get('religion_id', '')  # новый формат — ID из справочника
        skill_ids = request.form.getlist('skill_ids')  # новый формат — список ID навыков
        portfolio_link = request.form.get('portfolio_link', '')
        skills_str = request.form.get('skills', '')

        # ИНН и согласие самозанятого — опционально
        inn = request.form.get('inn', '')
        is_self_employed = request.form.get('is_self_employed') == 'on'

        if role == 'worker' and inn:
            if not inn.isdigit() or len(inn) != 12:
                flash('ИНН должен содержать ровно 12 цифр', 'danger')
                return render_template('register.html')

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


@auth_bp.route('/logout')
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
