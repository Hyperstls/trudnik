import uuid as _uuid
import logging
import time
import requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.utils import SUPABASE_KEY, SUPABASE_URL, SERVICE_KEY, rate_limit, supabase_request

auth_bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        auth_url = f'{SUPABASE_URL}/auth/v1/token?grant_type=password'
        last_error = None
        for attempt in range(3):
            try:
                resp = requests.post(auth_url, json={'email': email, 'password': password},
                                     headers={'apikey': SUPABASE_KEY}, timeout=10)
                if resp.ok:
                    data = resp.json()
                    session['access_token'] = data['access_token']
                    session['refresh_token'] = data.get('refresh_token', '')
                    session['user_id'] = data['user']['id']
                    role_resp = supabase_request('GET', f'profiles?id=eq.{data["user"]["id"]}&select=role')
                    session['role'] = role_resp.json()[0]['role'] if role_resp.ok and role_resp.json() else 'worker'
                    session.modified = True
                    if session.get('role') == 'employer':
                        return redirect(url_for('jobs.my_jobs'))
                    else:
                        return redirect(url_for('jobs.index'))
                elif resp.status_code == 429:
                    # Rate limit — ждём и пробуем снова
                    log.warning('Auth rate-limited for %s, attempt %d/3', email, attempt + 1)
                    last_error = 'rate_limited'
                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    # Неверный пароль — не повторяем
                    flash('Ошибка входа: неверный email или пароль', 'danger')
                    return render_template('login.html')
            except requests.RequestException as e:
                log.warning('Auth connection error for %s, attempt %d/3: %s', email, attempt + 1, e)
                last_error = str(e)
                time.sleep(1.0 * (attempt + 1))
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
        if not email:
            errors.append('Укажите email')
        if not password:
            errors.append('Укажите пароль')
        if role not in ('worker', 'employer'):
            errors.append('Выберите роль')
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

        signup_url = f'{SUPABASE_URL}/auth/v1/signup'
        try:
            resp = requests.post(signup_url, json={'email': email, 'password': password},
                                 headers={'apikey': SUPABASE_KEY}, timeout=10)
            if resp.ok:
                user = resp.json()['user']
                update_data = {
                    'role': role,
                    'full_name': full_name,
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

                if SERVICE_KEY:
                    patch_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user['id']}"
                    requests.patch(patch_url, json=update_data,
                                   headers={
                                       'apikey': SERVICE_KEY,
                                       'Authorization': f'Bearer {SERVICE_KEY}',
                                       'Content-Type': 'application/json'
                                   }, timeout=10)
                else:
                    supabase_request('PATCH', f'profiles?id=eq.{user["id"]}', json=update_data)

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
                        supabase_request('POST', 'user_skills', json={
                            'user_id': user['id'], 'skill_id': sid
                        })

                flash('Регистрация успешна. Теперь войдите.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Ошибка регистрации', 'danger')
        except requests.RequestException:
            flash('Ошибка соединения с сервером', 'danger')
    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
