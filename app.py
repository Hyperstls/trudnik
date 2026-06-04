import math
import time
import uuid
import os
import subprocess
import traceback
from datetime import datetime
from functools import wraps

import requests
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)

import config

app = Flask(__name__)
app.config.from_object(config.Config)
app.secret_key = app.config['SECRET_KEY']

SUPABASE_URL = app.config['SUPABASE_URL']
SUPABASE_KEY = app.config['SUPABASE_ANON_KEY']
SERVICE_KEY = app.config.get('SUPABASE_SERVICE_ROLE_KEY', '')

# ──────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def refresh_access_token():
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return False
    url = f'{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token'
    try:
        resp = requests.post(url, json={'refresh_token': refresh_token},
                             headers={'apikey': SUPABASE_KEY, 'Content-Type': 'application/json'},
                             timeout=10)
        if resp.ok:
            data = resp.json()
            session['access_token'] = data['access_token']
            session['refresh_token'] = data.get('refresh_token', refresh_token)
            session.modified = True
            return True
        else:
            session.clear()
            return False
    except requests.RequestException:
        return False


def supabase_request(method, endpoint, **kwargs):
    def _make_request():
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {session.get("access_token", SUPABASE_KEY)}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation',
        }
        if 'headers' in kwargs:
            extra = kwargs.pop('headers')
            headers.update(extra)
        url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
        return requests.request(method, url, headers=headers, timeout=15, **kwargs)

    try:
        resp = _make_request()
        if resp.status_code == 401 and session.get('refresh_token'):
            if refresh_access_token():
                resp = _make_request()
        return resp
    except requests.RequestException as e:
        app.logger.error(f"Supabase request error: {e}")
        return type('obj', (object,), {'ok': False, 'status_code': 0, 'text': str(e)})()


def upload_to_storage(bucket, file_path, file_data, content_type):
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {session["access_token"]}',
    }
    try:
        resp = requests.post(url, headers=headers,
                             files={'file': (file_path, file_data, content_type)},
                             timeout=30)
        if resp.status_code in (200, 201):
            return f'{SUPABASE_URL}/storage/v1/object/public/{bucket}/{file_path}?t={int(time.time())}'
    except requests.RequestException:
        pass
    return None


def copy_job(original_job):
    return {
        'employer_id': original_job['employer_id'],
        'organization_name': original_job.get('organization_name', ''),
        'org_description': original_job.get('org_description', ''),
        'object_description': original_job.get('object_description', ''),
        'work_type': original_job.get('work_type', ''),
        'detailed_description': original_job.get('detailed_description', ''),
        'date_time': original_job.get('date_time', ''),
        'payment_amount': original_job.get('payment_amount', 0),
        'address': original_job.get('address', ''),
        'city': original_job.get('city', ''),
        'lat': original_job.get('lat', 55.75),
        'lng': original_job.get('lng', 37.61),
        'status': 'open',
        'max_workers': original_job.get('max_workers', 1),
        'current_workers': 0,
    }


# ──────────────────────────────────────────────
# Декораторы
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'access_token' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'access_token' not in session:
                return redirect(url_for('login'))
            resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
            data = resp.json()
            if not data or data[0]['role'] != role:
                flash('Доступ запрещён', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ──────────────────────────────────────────────
# Контекстный процессор (счётчик откликов)
# ──────────────────────────────────────────────

@app.context_processor
def inject_application_count():
    count = 0
    if session.get('role') == 'employer' and 'user_id' in session:
        resp = supabase_request('GET',
            f'applications?job.employer_id=eq.{session["user_id"]}&status=eq.pending&select=id')
        if resp.ok and resp.json():
            count = len(resp.json())
    return {'pending_app_count': count}


# ──────────────────────────────────────────────
# Контекстный процессор (текущая роль пользователя)
# ──────────────────────────────────────────────

@app.context_processor
def inject_user_role():
    return {'current_user_role': session.get('role')}


# ──────────────────────────────────────────────
# Контекстный процессор (текущий ID пользователя)
# ──────────────────────────────────────────────

@app.context_processor
def inject_user_id():
    return {'current_user_id': session.get('user_id')}


# ──────────────────────────────────────────────
# Публичные маршруты
# ──────────────────────────────────────────────

@app.route('/')
def index():
    city = request.args.get('city', '')
    payment_min = request.args.get('payment_min', '')
    payment_max = request.args.get('payment_max', '')
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 20, type=float)
    sort = request.args.get('sort', '')

    query = 'status=eq.open&select=*,photos:job_photos(*)'
    if city: query += f'&city=ilike.*{city}*'
    if payment_min: query += f'&payment_amount=gte.{payment_min}'
    if payment_max: query += f'&payment_amount=lte.{payment_max}'

    resp = supabase_request('GET', f'jobs?{query}&order=created_at.desc')
    jobs = resp.json() if resp.ok else []

    if lat is not None and lng is not None:
        for job in jobs:
            job['distance'] = calculate_distance(lat, lng, job['lat'], job['lng'])
        if radius:
            jobs = [j for j in jobs if j.get('distance', float('inf')) <= radius]

    if sort == 'distance' and lat is not None:
        jobs.sort(key=lambda x: x.get('distance', float('inf')))
    elif sort == 'payment_asc':
        jobs.sort(key=lambda x: x['payment_amount'])
    elif sort == 'payment_desc':
        jobs.sort(key=lambda x: x['payment_amount'], reverse=True)

    applied_job_ids = []
    if session.get('role') == 'worker' and 'user_id' in session:
        app_resp = supabase_request('GET',
            f'applications?worker_id=eq.{session["user_id"]}&select=job_id')
        if app_resp.ok and app_resp.json():
            applied_job_ids = [a['job_id'] for a in app_resp.json()]

    return render_template('index.html', jobs=jobs, applied_job_ids=applied_job_ids,
                           lat=lat, lng=lng, radius=radius, sort=sort)


@app.route('/workers')
def workers():
    filters = {
        'city': request.args.get('city', ''),
        'experience': request.args.get('experience', ''),
        'payment_from': request.args.get('payment_from', ''),
        'payment_to': request.args.get('payment_to', ''),
        'rating_min': request.args.get('rating_min', ''),
        'skills': request.args.get('skills', ''),
        'religion': request.args.get('religion', ''),
    }
    query = 'role=eq.worker'
    if filters['city']: query += f'&city=ilike.*{filters["city"]}*'
    if filters['experience']: query += f'&experience=ilike.*{filters["experience"]}*'
    if filters['payment_from']: query += f'&desired_payment=gte.{filters["payment_from"]}'
    if filters['payment_to']: query += f'&desired_payment=lte.{filters["payment_to"]}'
    if filters['rating_min']: query += f'&rating=gte.{filters["rating_min"]}'
    if filters['skills']:
        for skill in filters['skills'].split(','):
            query += f'&skills=cs.{{{skill.strip()}}}'
    if filters['religion']:
        query += f'&religion=eq.{filters["religion"]}'

    resp = supabase_request('GET', f'profiles?{query}&order=rating.desc')
    return render_template('workers.html', workers=resp.json() if resp.ok else [])


@app.route('/jobs/<job_id>')
def job_detail(job_id):
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*,photos:job_photos(*)')
    job = resp.json()[0] if resp.ok and resp.json() else None
    if not job:
        flash('Задание не найдено', 'danger')
        return redirect(url_for('index'))

    if session.get('role') == 'employer' and job['employer_id'] == session.get('user_id'):
        app_resp = supabase_request('GET', f'applications?job_id=eq.{job_id}&select=id')
        job['application_count'] = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0
    else:
        job['application_count'] = 0

    already_applied = False
    if 'user_id' in session:
        app_resp = supabase_request('GET',
            f'applications?job_id=eq.{job_id}&worker_id=eq.{session["user_id"]}')
        already_applied = app_resp.ok and len(app_resp.json()) > 0

    return render_template('job_detail.html', job=job,
                           yandex_api_key=app.config['YANDEX_MAPS_API_KEY'],
                           already_applied=already_applied,
                           current_user_role=session.get('role'))


@app.route('/profile/<user_id>')
def public_profile(user_id):
    resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
    profile_user = resp.json()[0] if resp.ok and resp.json() else None
    if not profile_user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('index'))
    return render_template('profile_worker.html', profile_user=profile_user)


# ──────────────────────────────────────────────
# Аутентификация
# ──────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        auth_url = f'{SUPABASE_URL}/auth/v1/token?grant_type=password'
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
                # Для тестирования: если роль не установлена, присваиваем employer
                email_lower = data['user']['email'].lower()
                if 'test' in email_lower:
                    session['role'] = 'employer'
                    flash('Тестовый аккаунт работодателя активирован', 'info')
                    # Обновляем роль в базе данных для постоянного сохранения
                    if SERVICE_KEY:
                        supabase_request('PATCH', f'profiles?id=eq.{data["user"]["id"]}',
                                        json={'role': 'employer'})
                session.modified = True
                if session.get('role') == 'employer':
                    return redirect(url_for('my_jobs'))
                else:
                    return redirect(url_for('index'))
            else:
                flash('Ошибка входа: неверный email или пароль', 'danger')
        except requests.RequestException:
            flash('Ошибка соединения с сервером авторизации', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        city = request.form.get('city', '')
        religion = request.form.get('religion', 'не указано')
        portfolio_link = request.form.get('portfolio_link', '')
        skills_str = request.form.get('skills', '')

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
                    desired_payment = request.form.get('desired_payment', '0')
                    try:
                        update_data['desired_payment'] = float(desired_payment) if desired_payment else 0
                    except ValueError:
                        update_data['desired_payment'] = 0
                    update_data['experience'] = request.form.get('experience', '')

                # Для тестовых аккаунтов работодателя обновляем роль через анонимный ключ
                if 'test' in email.lower() and role == 'employer':
                    update_data['role'] = 'employer'
                    # Если SERVICE_KEY недоступен, используем анонимный ключ с RLS off
                    if not SERVICE_KEY:
                        # Попытка обновить через анонимный ключ (возможно с включенным RLS)
                        try:
                            rls_headers = {
                                'apikey': SUPABASE_KEY,
                                'Authorization': f'Bearer {SUPABASE_KEY}',
                                'Content-Type': 'application/json',
                                'Prefer': 'return=representation',
                                'Accept-Profile': 'public'
                            }
                            resp_rls = requests.patch(f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user['id']}",
                                                      json={'role': 'employer'}, headers=rls_headers, timeout=10)
                            if resp_rls.status_code != 200:
                                flash('Не удалось установить роль работодателя (RLS активен). Обратитесь к администратору.', 'warning')
                        except:
                            pass

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

                flash('Регистрация успешна. Теперь войдите.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Ошибка регистрации', 'danger')
        except requests.RequestException:
            flash('Ошибка соединения с сервером', 'danger')
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ──────────────────────────────────────────────
# Профиль
# ──────────────────────────────────────────────

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    try:
        resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
        profile_user = resp.json()[0] if resp.ok and resp.json() else None
    except:
        profile_user = None
    return render_template('profile.html', profile_user=profile_user)


@app.route('/profile/update', methods=['POST'])
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
    return redirect(url_for('profile'))


@app.route('/profile/delete-photo', methods=['POST'])
@login_required
def delete_photo():
    user_id = session['user_id']
    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'photo_url': None})
    flash('Фото удалено', 'success')
    return redirect(url_for('profile'))


@app.route('/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    if not SERVICE_KEY:
        flash('Сервисный ключ не настроен. Удаление невозможно.', 'danger')
        return redirect(url_for('profile'))
    delete_url = f'{SUPABASE_URL}/auth/v1/admin/users/{user_id}'
    resp = requests.delete(delete_url, headers={
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Content-Type': 'application/json'
    }, timeout=10)
    if resp.ok:
        session.clear()
        flash('Ваш аккаунт полностью удалён.', 'success')
        return redirect(url_for('login'))
    else:
        flash(f'Ошибка удаления аккаунта: {resp.text}', 'danger')
        return redirect(url_for('profile'))


@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not new_password or len(new_password) < 6:
        flash('Пароль должен содержать минимум 6 символов', 'danger')
        return redirect(url_for('profile'))

    if new_password != confirm_password:
        flash('Новые пароли не совпадают', 'danger')
        return redirect(url_for('profile'))

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

    return redirect(url_for('profile'))


@app.route('/verify-employer', methods=['GET', 'POST'])
@login_required
def verify_employer():
    if request.method == 'POST':
        supabase_request('PATCH', f'profiles?id=eq.{session["user_id"]}',
                         json={'verification_status': 'pending'})
        flash('Документ отправлен на проверку', 'success')
        return redirect(url_for('profile'))
    return render_template('verify_employer.html')


@app.route('/job/new', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def job_new():
    """Маршрут для создания задания через шаблон job_new.html"""
    if request.method == 'POST':
        try:
            job_data = {
                'employer_id': session['user_id'],
                'organization_name': request.form.get('title') or 'Храм',
                'org_description': '',
                'object_description': '',
                'work_type': '',
                'detailed_description': request.form.get('description', ''),
                'date_time': datetime.now().isoformat(),
                'payment_amount': float(request.form.get('payment') or 0),
                'address': request.form.get('address', ''),
                'city': request.form.get('city', ''),
                'lat': float(request.form.get('latitude') or 55.75),
                'lng': float(request.form.get('longitude') or 37.61),
                'preferred_religion': 'не важно',
                'max_workers': int(request.form.get('max_workers', 1)),
                'current_workers': 0,
            }
            
            app.logger.info(f"Creating job from job_new: {job_data}")
            
            resp = supabase_request('POST', 'jobs', json=job_data)
            
            app.logger.info(f"Response status: {resp.status_code}, ok: {resp.ok}")
            if not resp.ok:
                app.logger.error(f"Response text: {resp.text}")
            
            if resp.ok:
                flash('Задание опубликовано', 'success')
                return redirect(url_for('my_jobs'))
            else:
                flash(f'Ошибка создания задания: {resp.text}', 'danger')
        except Exception as e:
            flash('Ошибка сервера', 'danger')
    
    return render_template('job_new.html', yandex_api_key=app.config['YANDEX_MAPS_API_KEY'])


# ──────────────────────────────────────────────
# Задания
# ──────────────────────────────────────────────

@app.route('/create-job', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def create_job():
    if request.method == 'POST':
        job_data = {
            'employer_id': session['user_id'],
            'organization_name': request.form.get('organization_name') or 'Храм',
            'org_description': request.form.get('org_description', ''),
            'object_description': request.form.get('object_description', ''),
            'work_type': request.form.get('work_type', ''),
            'detailed_description': request.form.get('detailed_description', ''),
            'date_time': f"{request.form['date']}T{request.form['time']}:00",
            'payment_amount': float(request.form.get('payment') or 0),
            'address': request.form.get('address', ''),
            'city': request.form.get('city', ''),
            'lat': float(request.form.get('lat', 55.75)),
            'lng': float(request.form.get('lng', 37.61)),
            'preferred_religion': request.form.get('preferred_religion', 'не важно'),
            'max_workers': int(request.form.get('max_workers', 1)),
            'current_workers': 0,
        }
        resp = supabase_request('POST', 'jobs', json=job_data)
        if resp.ok:
            flash('Задание опубликовано', 'success')
            return redirect(url_for('my_jobs'))
        flash('Ошибка создания задания', 'danger')
    return render_template('create_job.html', yandex_api_key=app.config['YANDEX_MAPS_API_KEY'])

@app.route('/apply/<job_id>', methods=['GET', 'POST'])
@login_required
def apply_job(job_id):
    user_id = session['user_id']
    check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if check.ok and check.json():
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('index'))

    # Проверить статус задания
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,current_workers,max_workers,employer_id')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('index'))
    
    job = job_resp.json()[0]
    
    # Проверить, что задание не собственное
    if job['employer_id'] == user_id:
        flash('Вы не можете откликаться на собственное задание', 'danger')
        return redirect(url_for('index'))
    
    # Проверить статус задания
    if job['status'] != 'open':
        flash('На это задание нельзя откликаться (не open)', 'danger')
        return redirect(url_for('index'))
    
    # Проверить количество мест
    current_workers = job.get('current_workers', 0)
    max_workers = job.get('max_workers', 1)
    
    if current_workers >= max_workers:
        flash(f'Места в задании заполнены (максимум {max_workers})', 'info')
        return redirect(url_for('index'))
    
    supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})
    flash('Отклик отправлен', 'success')
    return redirect(url_for('index'))


@app.route('/apply-selected', methods=['POST'])
@login_required
def apply_selected():
    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('index'))

    user_id = session['user_id']
    applied = 0
    for job_id in job_ids:
        check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
        if not (check.ok and check.json()):
            supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})
            applied += 1

    if applied > 0:
        flash(f'Отклик отправлен на {applied} заданий', 'success')
    else:
        flash('Вы уже откликались на все выбранные задания', 'info')
    return redirect(url_for('index'))


@app.route('/unapply/<job_id>', methods=['POST'])
@login_required
def unapply_job(job_id):
    user_id = session['user_id']
    resp = supabase_request('DELETE', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if resp is not None and resp.ok:
        flash('Отклик отозван', 'success')
    else:
        flash('Не удалось отозвать отклик (возможно, он уже удалён)', 'danger')
    return redirect(url_for('index'))


@app.route('/unapply-selected', methods=['POST'])
@login_required
def unapply_selected():
    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('index'))
    user_id = session['user_id']
    removed = 0
    for job_id in job_ids:
        resp = supabase_request('DELETE', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
        if resp is not None and resp.ok:
            removed += 1
    if removed > 0:
        flash(f'Отклики отозваны ({removed} заданий)', 'success')
    else:
        flash('Ни один отклик не был удалён', 'info')
    return redirect(url_for('index'))


@app.route('/favorite-job/<job_id>', methods=['POST'])
@login_required
def add_favorite_job(job_id):
    supabase_request('POST', 'job_favorites', json={'user_id': session['user_id'], 'job_id': job_id})
    flash('Задание добавлено в избранное', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/unfavorite-job/<job_id>', methods=['POST'])
@login_required
def remove_favorite_job(job_id):
    supabase_request('DELETE', f'job_favorites?user_id=eq.{session["user_id"]}&job_id=eq.{job_id}')
    flash('Задание удалено из избранного', 'success')
    return redirect(request.referrer or url_for('favorites'))


@app.route('/applications/<app_id>/<action>', methods=['POST'])
@login_required
def handle_application(app_id, action):
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('index'))

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']

    if action == 'accept':
        # Проверить количество мест
        job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers')
        if not job_resp.ok or not job_resp.json():
            flash('Ошибка: задание не найдено', 'danger')
            return redirect(url_for('my_applications'))
        
        job = job_resp.json()[0]
        current_workers = job.get('current_workers', 0)
        max_workers = job.get('max_workers', 1)
        
        if current_workers >= max_workers:
            flash(f'Ошибка: все места в задании уже заняты (максимум {max_workers})', 'danger')
            return redirect(url_for('my_applications'))
        
        # Принять отклик и увеличить счетчик
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'accepted'})
        supabase_request('PATCH', f'applications?job_id=eq.{job_id}&id=neq.{app_id}',
                         json={'status': 'rejected'})
        supabase_request('POST', 'shifts', json={
            'job_id': job_id, 'worker_id': worker_id, 'employer_id': session['user_id']
        })
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'status': 'in_progress',
            'current_workers': current_workers + 1
        })
        flash('Работник принят', 'success')
    else:
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'rejected'})
        flash('Отклик отклонён', 'info')
    return redirect(url_for('my_applications'))


@app.route('/application/<app_id>/cancel', methods=['POST'])
@login_required
def cancel_application(app_id):
    """Отмена принятого работника"""
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,shift_id')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('my_applications'))
    
    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']
    shift_id = app_data.get('shift_id')
    
    # Получить информацию о задании
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,start_time')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('my_applications'))
    
    job = job_resp.json()[0]
    
    # Проверить статус задания (можно отменить только до начала)
    if job['status'] in ['active', 'payment_pending', 'paid', 'completed']:
        flash('Нельзя отменить работника после начала смены', 'danger')
        return redirect(url_for('my_applications'))
    
    # Проверить время (если статус in_progress - проверить 12 часов)
    if job['status'] == 'in_progress' and shift_id:
        shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=start_time')
        if shift_resp.ok and shift_resp.json():
            start_time = datetime.fromisoformat(shift_resp.json()[0]['start_time'].replace('Z', '+00:00'))
            now = datetime.now(start_time.tzinfo)
            hours_before = (start_time - now).total_seconds() / 3600
            if hours_before < 12:
                flash(f'Нельзя отменить работника менее чем за 12 часов до начала (осталось {hours_before:.1f} ч)', 'danger')
                return redirect(url_for('my_applications'))
    
    # Уменьшить счетчик работников
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers')
    if job_resp.ok and job_resp.json():
        job_data = job_resp.json()[0]
        current_workers = max(0, job_data.get('current_workers', 1) - 1)
        
        # Вернуть статус в open если все ушли
        new_status = 'open' if current_workers == 0 else 'in_progress'
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'status': new_status,
            'current_workers': current_workers
        })
    
    # Отклонить отклик и удалить смену
    supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'rejected'})
    if shift_id:
        supabase_request('DELETE', f'shifts?id=eq.{shift_id}')
    
    # Отправить уведомления
    add_notification(worker_id, 'application_rejected', 'Отклик отменен', f'Ваш отклик на задание {job.get("organization_name", "#" + job_id)} был отменен')
    
    flash('Работник отменен', 'success')
    return redirect(url_for('my_applications'))


@app.route('/shift/<shift_id>/checkin', methods=['POST'])
@login_required
def shift_checkin(shift_id):
    """Чек-ин работника"""
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=worker_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('shifts'))
    
    shift = shift_resp.json()[0]
    
    # Проверить, что пользователь - работник
    if session.get('user_id') != shift['worker_id']:
        flash('Нет прав для чек-ина', 'danger')
        return redirect(url_for('shifts'))
    
    # Обновить статус и записать время
    supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
        'worker_checkin': True,
        'start_time': datetime.now().isoformat(),
        'status': 'active'
    })
    
    # Обновить статус задания на active
    job_resp = supabase_request('GET', f'jobs?id=eq.{shift["job_id"]}&select=status')
    if job_resp.ok and job_resp.json():
        job = job_resp.json()[0]
        if job['status'] == 'in_progress':
            supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'active'})
    
    flash('Чек-ин успешно выполнен', 'success')
    return redirect(url_for('shifts'))


@app.route('/shift/<shift_id>/complete', methods=['POST'])
@login_required
def shift_complete(shift_id):
    """Завершение смены работником"""
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=worker_id,employer_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('shifts'))
    
    shift = shift_resp.json()[0]
    
    # Проверить, что пользователь - работник
    if session.get('user_id') != shift['worker_id']:
        flash('Нет прав для завершения', 'danger')
        return redirect(url_for('shifts'))
    
    # Проверить, что смена активна
    if shift['status'] != 'active':
        flash('Только активные смены можно завершить', 'danger')
        return redirect(url_for('shifts'))
    
    # Обновить статус и записать время
    supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
        'worker_complete': True,
        'complete_time': datetime.now().isoformat(),
        'status': 'payment_pending'
    })
    
    # Обновить статус задания на payment_pending
    supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'payment_pending'})
    
    flash('Смена завершена, ожидание подтверждения оплаты', 'success')
    return redirect(url_for('shifts'))


@app.route('/shift/<shift_id>/confirm-payment', methods=['POST'])
@login_required
def confirm_payment(shift_id):
    """Подтверждение оплаты (работодателем или работником)"""
    action = request.form.get('action', '')
    
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=employer_id,worker_id,job_id,employer_payment_confirmed,worker_payment_confirmed,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('shifts'))
    
    shift = shift_resp.json()[0]
    
    # Проверить права доступа
    is_employer = session.get('user_id') == shift['employer_id']
    is_worker = session.get('user_id') == shift['worker_id']
    
    if action == 'confirm_employer' and not is_employer:
        flash('Только работодатель может подтвердить оплату', 'danger')
        return redirect(url_for('shifts'))
    
    if action == 'confirm_worker' and not is_worker:
        flash('Только работник может подтвердить получение оплаты', 'danger')
        return redirect(url_for('shifts'))
    
    # Обновить статус подтверждения
    if action == 'confirm_employer':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'employer_payment_confirmed': True})
        flash('Оплата подтверждена работодателем', 'success')
    elif action == 'confirm_worker':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'worker_payment_confirmed': True})
        flash('Оплата подтверждена работником', 'success')
    
    # Проверить, подтвердили ли обе стороны
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=employer_payment_confirmed,worker_payment_confirmed')
    if shift_resp.ok and shift_resp.json():
        shift = shift_resp.json()[0]
        if shift.get('employer_payment_confirmed') and shift.get('worker_payment_confirmed'):
            # Обе стороны подтвердили - установить статус paid
            supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'status': 'paid'})
            supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'paid'})
            
            # Отправить уведомления
            add_notification(shift['employer_id'], 'payment_sent', 'Оплата подтверждена', f'Оплата по смене #{shift_id} подтверждена обеими сторонами')
            add_notification(shift['worker_id'], 'payment_received', 'Оплата подтверждена', f'Оплата по смене #{shift_id} подтверждена обеими сторонами')
    
    return redirect(url_for('shifts'))


@app.route('/my-applications')
@login_required
def my_applications():
    """Отображение откликов на задания работодателя"""
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    # Получить все отклики на задания работодателя
    resp = supabase_request('GET',
        f'applications?job.employer_id=eq.{user_id}&select=*,worker:profiles!inner(id,full_name,photo_url,rating,skills,desired_payment),job:jobs(organization_name,date_time,payment_amount,status,current_workers,max_workers)')
    applications = resp.json() if resp.ok else []
    
    # Получить список работников для каждого отклика
    worker_ids = [app.get('worker', {}).get('id') for app in applications if app.get('worker', {}).get('id')]
    jobs = {}
    if worker_ids:
        job_ids = list(set([app.get('job_id') for app in applications]))
        if job_ids:
            job_resp = supabase_request('GET', f'jobs?id=in.({",".join(job_ids)})&select=id,organization_name,date_time,payment_amount,status,application_count,current_workers,max_workers')
            if job_resp.ok and job_resp.json():
                jobs = {job['id']: job for job in job_resp.json()}
    
    return render_template('my_applications.html', applications=applications, jobs=jobs)


@app.route('/my-jobs')
@login_required
def my_jobs():
    """Отображение заданий работодателя"""
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'all':
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')
    else:
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&status=eq.{status_filter}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')
    
    jobs = resp.json() if resp.ok else []
    
    # Подсчитать количество откликов для каждого задания
    for job in jobs:
        app_resp = supabase_request('GET', f'applications?job_id=eq.{job["id"]}&select=id')
        job['application_count'] = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0
    
    return render_template('my_jobs.html', jobs=jobs, current_status=status_filter)


@app.route('/my-jobs/action', methods=['POST'])
@login_required
def my_jobs_action():
    """Массовое действие с заданиями"""
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    action = request.form.get('action')
    job_ids = request.form.getlist('job_ids')
    
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('my_jobs'))
    
    for job_id in job_ids:
        if action == 'restore':
            supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'open'})
        elif action == 'cancel':
            supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
        elif action == 'delete':
            supabase_request('DELETE', f'jobs?id=eq.{job_id}')
        elif action == 'duplicate':
            resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*')
            if resp.ok and resp.json():
                new_job = copy_job(resp.json()[0])
                supabase_request('POST', 'jobs', json=new_job)
    
    flash(f'Операция выполнена для {len(job_ids)} заданий', 'success')
    return redirect(url_for('my_jobs'))


@app.route('/repost-job/<job_id>', methods=['POST'])
@login_required
@role_required('employer')
def repost_job(job_id):
    """Дублирование задания"""
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*')
    if resp.ok and resp.json():
        new_job = copy_job(resp.json()[0])
        supabase_request('POST', 'jobs', json=new_job)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Задание дублировано'})
        flash('Задание дублировано', 'success')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Задание не найдено'}), 404
        flash('Задание не найдено', 'danger')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('my_jobs'))


@app.route('/cancel-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def cancel_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание отозвано'})
    flash('Задание отозвано', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('my_jobs'))


@app.route('/restore-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def restore_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'open'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание восстановлено'})
    flash('Задание восстановлено', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('my_jobs'))


@app.route('/delete-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def delete_job(job_id):
    supabase_request('DELETE', f'jobs?id=eq.{job_id}')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание удалено'})
    flash('Задание удалено', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('my_jobs'))


# ──────────────────────────────────────────────
# Смены
# ──────────────────────────────────────────────

@app.route('/shifts')
@login_required
def shifts():
    user_id = session['user_id']
    role_resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=role')
    role = role_resp.json()[0]['role'] if role_resp.ok and role_resp.json() else 'worker'
    if role == 'worker':
        resp = supabase_request('GET', f'shifts?worker_id=eq.{user_id}&select=*,job:jobs(*)')
    else:
        resp = supabase_request('GET', f'shifts?employer_id=eq.{user_id}&select=*,job:jobs(*)')
    return render_template('shifts.html', shifts=resp.json() if resp.ok else [])


@app.route('/shift/<shift_id>/action', methods=['POST'])
@login_required
def shift_action(shift_id):
    action = request.form.get('action')
    if action == 'checkin':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
            'worker_checkin': True, 'start_time': datetime.now().isoformat(), 'status': 'active'
        })
    elif action == 'complete':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
            'worker_complete': True, 'status': 'payment_pending'
        })
    elif action == 'confirm_payment_employer':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'employer_payment_confirmed': True})
    elif action == 'confirm_payment_worker':
        supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'worker_payment_confirmed': True})
    return redirect(url_for('shifts'))


# ──────────────────────────────────────────────
# Чат
# ──────────────────────────────────────────────

@app.route('/chats')
@login_required
def chats_list():
    user_id = session['user_id']
    resp = supabase_request('GET',
        f'shifts?or=(worker_id.eq.{user_id},employer_id.eq.{user_id})&select=id,job:jobs(organization_name)')
    return render_template('chats_list.html', chats=resp.json() if resp.ok else [])


@app.route('/chat/<shift_id>')
@login_required
def chat(shift_id):
    resp = supabase_request('GET', f'messages?shift_id=eq.{shift_id}&select=*&order=created_at.asc')
    return render_template('chat.html', shift_id=shift_id,
                           messages=resp.json() if resp.ok else [], user_id=session['user_id'])


@app.route('/chat/new/<worker_id>', methods=['GET'])
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


@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    supabase_request('POST', 'messages', json={
        'shift_id': data['shift_id'], 'sender_id': session['user_id'], 'content': data['content']
    })
    return jsonify({'status': 'ok'})


# ──────────────────────────────────────────────
# Избранное и чёрный список
# ──────────────────────────────────────────────

@app.route('/favorites')
@login_required
def favorites():
    resp = supabase_request('GET',
        f'favorites?user_id=eq.{session["user_id"]}&select=target:profiles!favorites_target_id_fkey(id,full_name,photo_url,rating)')
    items = resp.json() if resp.ok else []

    favorite_jobs = []
    if session.get('role') == 'worker':
        job_resp = supabase_request('GET',
            f'job_favorites?user_id=eq.{session["user_id"]}&select=job:jobs(*)')
        if job_resp.ok and job_resp.json():
            favorite_jobs = [j['job'] for j in job_resp.json() if j.get('job')]

    return render_template('favorites.html', items=items, favorite_jobs=favorite_jobs)


@app.route('/favorite/<target_id>', methods=['POST'])
@login_required
def add_favorite(target_id):
    supabase_request('POST', 'favorites', json={'user_id': session['user_id'], 'target_id': target_id})
    return redirect(request.referrer or url_for('index'))


@app.route('/unfavorite/<target_id>', methods=['POST'])
@login_required
def remove_favorite(target_id):
    supabase_request('DELETE', f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{target_id}')
    return redirect(url_for('favorites'))


@app.route('/blacklist')
@login_required
def blacklist():
    resp = supabase_request('GET',
        f'blacklists?user_id=eq.{session["user_id"]}&select=blocked:profiles!blacklists_blocked_user_id_fkey(id,full_name,photo_url)')
    return render_template('blacklist.html', items=resp.json() if resp.ok else [])


@app.route('/blacklist/<user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    supabase_request('POST', 'blacklists', json={'user_id': session['user_id'], 'blocked_user_id': user_id})
    return redirect(request.referrer or url_for('index'))


@app.route('/unblock/<user_id>', methods=['POST'])
@login_required
def unblock_user(user_id):
    supabase_request('DELETE', f'blacklists?user_id=eq.{session["user_id"]}&blocked_user_id=eq.{user_id}')
    return redirect(url_for('blacklist'))


# ──────────────────────────────────────────────
# Админка
# ──────────────────────────────────────────────

@app.route('/admin')
@login_required
@role_required('admin')
def admin():
    resp = supabase_request('GET', 'profiles?verification_status=eq.pending&select=*')
    return render_template('admin.html', pending=resp.json() if resp.ok else [])


@app.route('/admin/approve/<user_id>')
@login_required
@role_required('admin')
def admin_approve(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'verification_status': 'approved'})
    return redirect(url_for('admin'))


@app.route('/admin/reject/<user_id>')
@login_required
@role_required('admin')
def admin_reject(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'verification_status': 'rejected'})
    return redirect(url_for('admin'))


# ──────────────────────────────────────────────
# Оценки и споры
# ──────────────────────────────────────────────

@app.route('/rate-worker/<worker_id>/<job_id>', methods=['POST'])
@login_required
def rate_worker(worker_id, job_id):
    """Оценка работника после завершения смены"""
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '')
    
    # Получить информацию о смене
    shift_resp = supabase_request('GET', f'shifts?worker_id=eq.{worker_id}&job_id=eq.{job_id}&select=id,employer_id,worker_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('index'))
    
    shift = shift_resp.json()[0]
    
    # Проверить статус (только для-paid-)
    if shift['status'] != 'paid':
        flash('Оценить можно только после завершения оплаты', 'danger')
        return redirect(url_for('shifts'))
    
    # Проверить, что оценка оставляется только один раз
    existing = supabase_request('GET', f'ratings?rated_user_id=eq.{worker_id}&rater_user_id=eq.{session["user_id"]}&job_id=eq.{job_id}')
    if existing.ok and existing.json():
        flash('Вы уже оценили этого работника', 'info')
        return redirect(url_for('shifts'))
    
    # Создать запись оценки
    rating_data = {
        'rated_user_id': worker_id,
        'rater_user_id': session['user_id'],
        'rating_type': 'worker',
        'target_type': 'worker',
        'rating': rating,
        'comment': comment,
        'shift_id': shift['id']
    }
    supabase_request('POST', 'ratings', json=rating_data)
    
    # Обновить средний рейтинг в профиле
    update_rating(worker_id, rating)
    
    flash(f'Оценка работника: {rating}⭐', 'success')
    return redirect(url_for('shifts'))


def update_rating(user_id, new_rating):
    """Обновить средний рейтинг пользователя"""
    ratings_resp = supabase_request('GET', f'ratings?rated_user_id=eq.{user_id}&select=rating')
    if not ratings_resp.ok or not ratings_resp.json():
        return
    
    ratings_list = ratings_resp.json()
    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)
    
    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'rating': avg})


@app.route('/shift/<shift_id>/dispute', methods=['POST'])
@login_required
def dispute_shift(shift_id):
    """Запрос спора по смене"""
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=employer_id,worker_id')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('index'))
    
    shift = shift_resp.json()[0]
    
    # Проверить, что пользователь имеет отношение к смене
    if session['user_id'] not in [shift['employer_id'], shift['worker_id']]:
        flash('Нет прав на спор по этой смене', 'danger')
        return redirect(url_for('index'))
    
    # Обновить статус на 'disputed'
    supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'status': 'disputed'})
    
    # Отправить уведомление администратору
    admin_resp = supabase_request('GET', f'profiles?role=eq.admin&select=id')
    if admin_resp.ok and admin_resp.json():
        admin_id = admin_resp.json()[0]['id']
        add_notification(admin_id, 'dispute_started', 'Новый спор', f'Пользователь запросил спор по смене #{shift_id}')
    
    # Добавить уведомления участникам
    add_notification(shift['employer_id'], 'dispute_started', 'Спор открыт', f'Ваш спор по смене #{shift_id} открыт на рассмотрении')
    add_notification(shift['worker_id'], 'dispute_started', 'Спор открыт', f'Ваш спор по смене #{shift_id} открыт на рассмотрении')
    
    flash('Спор открыт на рассмотрение', 'warning')
    return redirect(url_for('shifts'))


def add_notification(user_id, notification_type, title, message):
    """Добавить уведомление пользователю"""
    notification_data = {
        'user_id': user_id,
        'type': notification_type,
        'title': title,
        'message': message,
        'is_read': False
    }
    supabase_request('POST', 'notifications', json=notification_data)


# ──────────────────────────────────────────────
# Уведомления
# ──────────────────────────────────────────────

@app.route('/notifications')
@login_required
def notifications_list():
    """Список уведомлений пользователя"""
    user_id = session['user_id']
    resp = supabase_request('GET', f'notifications?user_id=eq.{user_id}&order=created_at.desc')
    notifications = resp.json() if resp.ok else []
    
    # Пометить все как прочитанные
    unread_ids = [n['id'] for n in notifications if not n.get('is_read')]
    if unread_ids:
        supabase_request('PATCH', f'notifications?id=in.({",".join(unread_ids)})', json={'is_read': True})
    
    return render_template('notifications.html', notifications=notifications)


@app.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Пометить уведомление как прочитанное"""
    supabase_request('PATCH', f'notifications?id=eq.{notification_id}', json={'is_read': True})
    return jsonify({'status': 'ok'})


# ──────────────────────────────────────────────
# Работодатель: мои задания и отклики
# ──────────────────────────────────────────────

