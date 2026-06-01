import math
import time
import uuid
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

    resp = _make_request()
    if resp.status_code == 401 and session.get('refresh_token'):
        if refresh_access_token():
            resp = _make_request()
    return resp


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
    }
    query = 'role=eq.worker'
    if filters['city']: query += f'&city=ilike.*{filters["city"]}*'
    if filters['experience']: query += f'&experience=ilike.*{filters["experience"]}*'
    if filters['payment_from']: query += f'&desired_payment=gte.{filters["payment_from"]}'
    if filters['payment_to']: query += f'&desired_payment=lte.{filters["payment_to"]}'
    if filters['rating_min']: query += f'&rating=gte.{filters["rating_min"]}'

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
                           already_applied=already_applied)


@app.route('/profile/<user_id>')
def public_profile(user_id):
    resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=*')
    profile = resp.json()[0] if resp.ok and resp.json() else None
    if not profile:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('index'))
    return render_template('profile_worker.html', profile=profile)


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
                session.modified = True
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

        signup_url = f'{SUPABASE_URL}/auth/v1/signup'
        try:
            resp = requests.post(signup_url, json={'email': email, 'password': password},
                                 headers={'apikey': SUPABASE_KEY}, timeout=10)
            if resp.ok:
                user = resp.json()['user']
                update_data = {'role': role, 'full_name': full_name, 'city': city}
                if role == 'worker':
                    desired_payment = request.form.get('desired_payment', '0')
                    try:
                        update_data['desired_payment'] = float(desired_payment) if desired_payment else 0
                    except ValueError:
                        update_data['desired_payment'] = 0
                    update_data['experience'] = request.form.get('experience', '')

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
        profile_data = resp.json()[0] if resp.ok and resp.json() else None
    except:
        profile_data = None
    return render_template('profile.html', profile=profile_data)


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    data = {
        'full_name': request.form.get('full_name'),
        'phone': request.form.get('phone'),
        'bio': request.form.get('bio'),
        'city': request.form.get('city'),
    }
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
            'payment_amount': float(request.form['payment']),
            'address': request.form.get('address', ''),
            'city': request.form.get('city', ''),
            'lat': float(request.form.get('lat', 55.75)),
            'lng': float(request.form.get('lng', 37.61)),
        }
        resp = supabase_request('POST', 'jobs', json=job_data)
        if resp.ok:
            flash('Задание опубликовано', 'success')
            return redirect(url_for('my_jobs'))
        flash('Ошибка создания задания', 'danger')
    return render_template('create_job.html', yandex_api_key=app.config['YANDEX_MAPS_API_KEY'])


@app.route('/apply/<job_id>', methods=['POST'])
@login_required
def apply_job(job_id):
    user_id = session['user_id']
    check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if check.ok and check.json():
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('job_detail', job_id=job_id))

    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=employer_id')
    if job_resp.ok and job_resp.json() and job_resp.json()[0]['employer_id'] == user_id:
        flash('Вы не можете откликаться на собственное задание', 'danger')
        return redirect(url_for('job_detail', job_id=job_id))

    supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})
    flash('Отклик отправлен', 'success')
    return redirect(url_for('job_detail', job_id=job_id))


@app.route('/applications/<app_id>/<action>')
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
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'accepted'})
        supabase_request('PATCH', f'applications?job_id=eq.{job_id}&id=neq.{app_id}',
                         json={'status': 'rejected'})
        supabase_request('POST', 'shifts', json={
            'job_id': job_id, 'worker_id': worker_id, 'employer_id': session['user_id']
        })
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'in_progress'})
        flash('Работник принят', 'success')
    else:
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'rejected'})
        flash('Отклик отклонён', 'info')
    return redirect(url_for('my_applications'))


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
    return render_template('favorites.html', items=resp.json() if resp.ok else [])


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
# Работодатель: мои задания и отклики
# ──────────────────────────────────────────────

@app.route('/my-applications')
@login_required
@role_required('employer')
def my_applications():
    resp = supabase_request('GET',
        f'applications?job.employer_id=eq.{session["user_id"]}&select=*,job:jobs(*),worker:profiles(*)')
    return render_template('my_applications.html', applications=resp.json() if resp.ok else [])


@app.route('/my-jobs')
@login_required
@role_required('employer')
def my_jobs():
    status_filter = request.args.get('status', 'all')
    query = f'employer_id=eq.{session["user_id"]}&select=*'
    if status_filter != 'all':
        query += f'&status=eq.{status_filter}'
    resp = supabase_request('GET', f'jobs?{query}&order=created_at.desc')
    return render_template('my_jobs.html', jobs=resp.json() if resp.ok else [],
                           current_status=status_filter)


@app.route('/repost-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def repost_job(job_id):
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*')
    if resp.ok and resp.json():
        new_job = copy_job(resp.json()[0])
        new_job['employer_id'] = session['user_id']
        supabase_request('POST', 'jobs', json=new_job)
        flash('Задание переопубликовано!', 'success')
    else:
        flash('Задание не найдено', 'danger')
    return redirect(url_for('my_jobs'))


@app.route('/my-jobs/action', methods=['POST'])
@login_required
@role_required('employer')
def my_jobs_action():
    job_ids = request.form.getlist('job_ids')
    action = request.form.get('action')
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


@app.route('/cancel-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def cancel_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
    flash('Задание отозвано', 'success')
    return redirect(url_for('my_jobs'))
@app.route('/restore-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def restore_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'open'})
    flash('Задание восстановлено', 'success')
    return redirect(url_for('my_jobs'))


@app.route('/delete-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def delete_job(job_id):
    supabase_request('DELETE', f'jobs?id=eq.{job_id}')
    flash('Задание удалено', 'success')
    return redirect(url_for('my_jobs'))


# ──────────────────────────────────────────────
# Запуск
# ──────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=False, port=5000)