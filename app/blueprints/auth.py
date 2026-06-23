import uuid as _uuid
import logging
import re
import time as _time
import jwt as _pyjwt
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import rate_limit
from app.utils import postgrest_admin_request, postgrest_request
from app.utils.validators import validate_password

auth_bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)

# RFC 5322 упрощённый regex для валидации email
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]*'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

# Запрещённые SQL-паттерны в пользовательском вводе (дополнительная защита).
# Проверяет ТОЛЬКО ASCII-фрагменты ввода — кириллица с \b работает некорректно
# и даёт ложные срабатывания (например, «Андрей» содержит «AND»).
# AND/OR исключены — они наиболее вероятны в легитимных именах и названиях.
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
    """
    # Извлекаем только ASCII-подстроки из текста
    ascii_parts = re.findall(r'[ -~]+', text)
    for part in ascii_parts:
        if _SQL_INJECTION_PATTERNS.search(part):
            return True
    return False


def _generate_jwt(user_id: str, role: str) -> str:
    """Сгенерировать JWT-токен для PostgREST-аутентификации."""
    payload = {
        'role': role,
        'user_id': str(user_id),
        'exp': int(_time.time()) + 3600,  # 1 час
        'iat': int(_time.time()),
    }
    return _pyjwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')


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


@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        last_error = None
        for attempt in range(2):
            try:
                resp = postgrest_admin_request('POST', 'rpc/login_user',
                    json={'p_email': email, 'p_password': password})
                if resp.ok:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        user = data[0]
                        _login_user_session(user['user_id'], user['role'], email)
                        if user.get('role') == 'employer':
                            return redirect(url_for('jobs.my_jobs'))
                        else:
                            return redirect(url_for('jobs.index'))
                    else:
                        flash('Ошибка входа: неверный email или пароль', 'danger')
                        return render_template('login.html')
                elif resp.status_code == 429:
                    log.warning('Auth rate-limited for %s, attempt %d/2', email, attempt + 1)
                    last_error = 'rate_limited'
                    _time.sleep(1.5 * (attempt + 1))
                    continue
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
            resp = postgrest_admin_request('POST', 'rpc/register_user', json={
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
    session.clear()
    return redirect(url_for('auth.login'))
