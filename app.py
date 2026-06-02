import os
import sys
import subprocess
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-secret-key')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def get_current_user_id():
    return session.get('user_id')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_git_version():
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-1'],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return result.stdout.strip() if result.stdout else "Версия не определена"
    except:
        return "Версия не определена"

# ===================== ГЛАВНАЯ =====================

@app.route('/')
def index():
    user_id = get_current_user_id()
    user_role = session.get('role')
    git_version = get_git_version()
    jobs = supabase.table('jobs').select('*').order('created_at', desc=True).limit(20).execute().data
    workers = supabase.table('profiles').select('*').eq('role', 'worker').limit(20).execute().data
    return render_template('index.html', jobs=jobs, workers=workers, user_id=user_id, user_role=user_role, git_version=git_version)

# ===================== АВТОРИЗАЦИЯ =====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        role = request.form.get('role')
        phone = request.form.get('phone')
        try:
            auth_response = supabase.auth.sign_up({'email': email, 'password': password})
            user = auth_response.user
            user_id = user.id
            profile_data = {
                'id': user_id,
                'email': email,
                'name': name,
                'role': role,
                'phone': phone,
                'created_at': datetime.utcnow().isoformat()
            }
            supabase.table('profiles').insert(profile_data).execute()
            session['user_id'] = user_id
            session['role'] = role
            session['email'] = email
            session['name'] = name
            flash('Регистрация успешна!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Ошибка регистрации: {str(e)}', 'error')
            return render_template('register.html')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
            user = auth_response.user
            user_id = user.id
            profile = supabase.table('profiles').select('*').eq('id', user_id).execute()
            if profile.data:
                profile_data = profile.data[0]
                session['user_id'] = user_id
                session['role'] = profile_data.get('role')
                session['email'] = email
                session['name'] = profile_data.get('name')
                flash('Вход выполнен!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Профиль не найден', 'error')
        except Exception as e:
            flash(f'Ошибка входа: {str(e)}', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# ===================== ЗАДАНИЯ =====================

@app.route('/jobs')
def jobs_list():
    city = request.args.get('city')
    min_payment = request.args.get('min_payment')
    max_payment = request.args.get('max_payment')
    sort_by = request.args.get('sort_by', 'created_at')
    query = supabase.table('jobs').select('*')
    if city:
        query = query.eq('city', city)
    if min_payment:
        query = query.gte('payment', float(min_payment))
    if max_payment:
        query = query.lte('payment', float(max_payment))
    if sort_by == 'payment':
        query = query.order('payment', desc=True)
    elif sort_by == 'rating':
        query = query.order('employer_rating', desc=True)
    else:
        query = query.order('created_at', desc=True)
    jobs = query.execute().data
    return render_template('jobs.html', jobs=jobs)

@app.route('/job/new', methods=['GET', 'POST'])
@login_required
def job_new():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        payment = request.form.get('payment')
        city = request.form.get('city')
        address = request.form.get('address')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        required_workers = request.form.get('required_workers', 1)
        user_id = get_current_user_id()
        job_data = {
            'employer_id': user_id,
            'organization_name': title,
            'object_description': description,
            'payment_amount': float(payment) if payment else 0,
            'city': city,
            'address': address,
            'lat': float(latitude) if latitude else None,
            'lng': float(longitude) if longitude else None,
            'status': 'active',
            'created_at': datetime.utcnow().isoformat()
        }
        supabase.table('jobs').insert(job_data).execute()
        flash('Задание создано!', 'success')
        return redirect(url_for('my_jobs'))
    return render_template('job_new.html')

@app.route('/job/<job_id>')
def job_detail(job_id):
    job = supabase.table('jobs').select('*').eq('id', job_id).execute()
    if not job.data:
        flash('Задание не найдено', 'error')
        return redirect(url_for('index'))
    job_data = job.data[0]
    employer = supabase.table('profiles').select('full_name, rating, photo_url').eq('id', job_data['employer_id']).execute()
    return render_template('job_detail.html', job=job_data, employer=employer.data[0] if employer.data else None, already_applied=False, yandex_api_key=os.getenv('YANDEX_MAPS_API_KEY', ''), current_user_role=session.get('role'))

@app.route('/my-jobs')
@login_required
def my_jobs():
    user_id = get_current_user_id()
    jobs = supabase.table('jobs').select('*').eq('employer_id', user_id).order('created_at', desc=True).execute().data
    return render_template('my_jobs.html', jobs=jobs)


@app.route('/my-jobs/action', methods=['POST'])
@login_required
def my_jobs_action():
    user_id = get_current_user_id()
    action = request.form.get('action')
    job_ids = request.form.getlist('job_ids')

    if not job_ids:
        flash('Выберите задания', 'error')
        return redirect(url_for('my_jobs'))

    for job_id in job_ids:
        if action == 'delete':
            supabase.table('jobs').delete().eq('id', job_id).eq('employer_id', user_id).execute()
        elif action == 'cancel':
            supabase.table('jobs').update({'status': 'cancelled'}).eq('id', job_id).eq('employer_id', user_id).execute()
        elif action == 'restore':
            supabase.table('jobs').update({'status': 'open'}).eq('id', job_id).eq('employer_id', user_id).execute()
        elif action == 'duplicate':
            job = supabase.table('jobs').select('*').eq('id', job_id).execute().data
            if job:
                j = job[0]
                new_job = {k: v for k, v in j.items() if k not in ['id', 'created_at']}
                new_job['status'] = 'open'
                supabase.table('jobs').insert(new_job).execute()

    flash(f'Действие "{action}" выполнено для {len(job_ids)} заданий', 'success')
    return redirect(url_for('my_jobs'))


@app.route('/delete-job/<job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    user_id = get_current_user_id()
    supabase.table('jobs').delete().eq('id', job_id).eq('employer_id', user_id).execute()
    flash('Задание удалено', 'success')
    return redirect(url_for('my_jobs'))


@app.route('/cancel-job/<job_id>', methods=['POST'])
@login_required
def cancel_job(job_id):
    user_id = get_current_user_id()
    supabase.table('jobs').update({'status': 'cancelled'}).eq('id', job_id).eq('employer_id', user_id).execute()
    flash('Задание отозвано', 'info')
    return redirect(url_for('my_jobs'))


@app.route('/restore-job/<job_id>', methods=['POST'])
@login_required
def restore_job(job_id):
    user_id = get_current_user_id()
    supabase.table('jobs').update({'status': 'open'}).eq('id', job_id).eq('employer_id', user_id).execute()
    flash('Задание восстановлено', 'success')
    return redirect(url_for('my_jobs'))


@app.route('/repost-job/<job_id>', methods=['POST'])
@login_required
def repost_job(job_id):
    user_id = get_current_user_id()
    job = supabase.table('jobs').select('*').eq('id', job_id).execute().data
    if job:
        j = job[0]
        new_job = {k: v for k, v in j.items() if k not in ['id', 'created_at']}
        new_job['status'] = 'open'
        supabase.table('jobs').insert(new_job).execute()
        flash('Задание продублировано', 'success')
    return redirect(url_for('my_jobs'))

# ===================== ОТКЛИКИ =====================

@app.route('/my-applications')
@login_required
def my_applications():
    user_id = session['user_id']
    # Сначала получаем все задания текущего работодателя
    my_jobs = supabase.table('jobs').select('id, organization_name, payment_amount, city, status').eq('employer_id', user_id).execute().data
    my_job_ids = [j['id'] for j in my_jobs]

    applications = []
    jobs_dict = {j['id']: j for j in my_jobs}

    if my_job_ids:
        applications = supabase.table('applications').select(
            '*, worker:worker_id(id, full_name, rating, skills, desired_payment, photo_url)'
        ).in_('job_id', my_job_ids).execute().data

    return render_template('my_applications.html', applications=applications, jobs=jobs_dict, user_id=user_id)

@app.route('/api/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    data = request.get_json()
    action = data.get('action')
    application_ids = data.get('application_ids', [])
    user_id = session['user_id']

    # Получаем задания работодателя, чтобы проверить права
    my_jobs = supabase.table('jobs').select('id').eq('employer_id', user_id).execute().data
    my_job_ids = [j['id'] for j in my_jobs]

    if action == 'accept':
        for app_id in application_ids:
            supabase.table('applications').update({'status': 'accepted'}).eq('id', app_id).in_('job_id', my_job_ids).execute()
    elif action == 'reject':
        for app_id in application_ids:
            supabase.table('applications').update({'status': 'rejected'}).eq('id', app_id).in_('job_id', my_job_ids).execute()
    return jsonify({'success': True})

# ===================== ЧАТ =====================

@app.route('/chat/<shift_id>')
@login_required
def chat(shift_id):
    user_id = get_current_user_id()
    shift = supabase.table('shifts').select('*').eq('id', shift_id).execute()
    if not shift.data:
        flash('Чат не найден', 'error')
        return redirect(url_for('index'))
    shift_data = shift.data[0]
    messages = supabase.table('messages').select('*').eq('shift_id', shift_id).order('created_at').execute().data
    return render_template('chat.html', shift=shift_data, messages=messages, user_id=user_id)

@app.route('/chat/new/<worker_id>')
@login_required
def chat_new(worker_id):
    user_id = session['user_id']
    # Создаём чат (job_id берётся из query string, если есть)
    job_id = request.args.get('job_id')
    shift_data = {
        'employer_id': user_id,
        'worker_id': worker_id,
        'status': 'pending',
        'created_at': 'now()'
    }
    if job_id:
        shift_data['job_id'] = job_id
    result = supabase.table('shifts').insert(shift_data).execute()
    shift_id = result.data[0]['id']
    return redirect(url_for('chat', shift_id=shift_id))

# ===================== ПРОФИЛЬ =====================

@app.route('/profile/<user_id>')
def profile(user_id):
    profile = supabase.table('profiles').select('*').eq('id', user_id).execute()
    if not profile.data:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))
    profile_data = profile.data[0]
    current_user_id = get_current_user_id()
    current_user_role = session.get('role')
    return render_template('profile.html', profile_user=profile_data, current_user_id=current_user_id, current_user_role=current_user_role)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    user_id = get_current_user_id()
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        skills = request.form.get('skills')
        religion = request.form.get('religion')
        desired_payment = request.form.get('desired_payment')
        update_data = {}
        if name: update_data['name'] = name
        if phone: update_data['phone'] = phone
        if skills: update_data['skills'] = skills.split(',')
        if religion: update_data['religion'] = religion
        if desired_payment: update_data['desired_payment'] = float(desired_payment)
        supabase.table('profiles').update(update_data).eq('id', user_id).execute()
        flash('Профиль обновлён!', 'success')
        return redirect(url_for('profile', user_id=user_id))
    profile = supabase.table('profiles').select('*').eq('id', user_id).execute()
    return render_template('profile_edit.html', profile=profile.data[0] if profile.data else {})

# ===================== ТРУДНИКИ =====================

@app.route('/workers')
def workers():
    city = request.args.get('city')
    skill = request.args.get('skill')
    min_rating = request.args.get('min_rating')
    query = supabase.table('profiles').select('*').eq('role', 'worker')
    if city:
        query = query.eq('city', city)
    if min_rating:
        query = query.gte('rating', float(min_rating))
    workers = query.execute().data
    return render_template('workers.html', workers=workers)

# ===================== ПРОФИЛЬ (РЕДИРЕКТ) =====================

@app.route('/profile')
@login_required
def profile_redirect():
    user_id = get_current_user_id()
    return redirect(url_for('profile', user_id=user_id))


# ===================== УПРАВЛЕНИЕ ПРОФИЛЕМ =====================

@app.route('/profile/update', methods=['POST'])
@login_required
def profile_update():
    user_id = get_current_user_id()
    full_name = request.form.get('full_name')
    phone = request.form.get('phone')
    bio = request.form.get('bio')
    city = request.form.get('city')
    religion = request.form.get('religion')
    skills = request.form.get('skills')
    portfolio_link = request.form.get('portfolio_link')
    experience = request.form.get('experience')
    desired_payment = request.form.get('desired_payment')

    update_data = {}
    if full_name: update_data['full_name'] = full_name
    if phone: update_data['phone'] = phone
    if bio: update_data['bio'] = bio
    if city: update_data['city'] = city
    if religion: update_data['religion'] = religion
    if skills: update_data['skills'] = [s.strip() for s in skills.split(',') if s.strip()]
    if portfolio_link: update_data['portfolio_link'] = portfolio_link
    if experience: update_data['experience'] = experience
    if desired_payment: update_data['desired_payment'] = float(desired_payment)

    supabase.table('profiles').update(update_data).eq('id', user_id).execute()

    if 'photo' in request.files:
        photo = request.files['photo']
        if photo.filename:
            pass  # TODO: загрузка в Supabase Storage

    flash('Профиль обновлён!', 'success')
    return redirect(url_for('profile', user_id=user_id))


@app.route('/profile/delete-photo', methods=['POST'])
@login_required
def profile_delete_photo():
    user_id = get_current_user_id()
    supabase.table('profiles').update({'photo_url': None}).eq('id', user_id).execute()
    flash('Фото удалено', 'success')
    return redirect(url_for('profile', user_id=user_id))


@app.route('/profile/change-password', methods=['POST'])
@login_required
def profile_change_password():
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if new_password != confirm_password:
        flash('Пароли не совпадают', 'error')
        return redirect(url_for('profile', user_id=get_current_user_id()))

    if len(new_password) < 6:
        flash('Пароль должен быть минимум 6 символов', 'error')
        return redirect(url_for('profile', user_id=get_current_user_id()))

    try:
        supabase.auth.update_user({'password': new_password})
        flash('Пароль изменён!', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('profile', user_id=get_current_user_id()))


@app.route('/profile/delete-account', methods=['POST'])
@login_required
def profile_delete_account():
    user_id = get_current_user_id()
    try:
        supabase.table('profiles').delete().eq('id', user_id).execute()
        supabase.auth.admin.delete_user(user_id)
        session.clear()
        flash('Аккаунт удалён', 'info')
    except Exception as e:
        flash(f'Ошибка удаления: {str(e)}', 'error')
    return redirect(url_for('index'))


# ===================== ИЗБРАННОЕ =====================

@app.route('/api/favorites/add', methods=['POST'])
@login_required
def api_favorites_add():
    user_id = get_current_user_id()
    data = request.get_json()
    worker_id = data.get('worker_id')

    if not worker_id:
        return jsonify({'success': False, 'error': 'Не указан worker_id'}), 400

    try:
        existing = supabase.table('favorites').select('*').eq('user_id', user_id).eq('target_id', worker_id).execute()
        if existing.data:
            return jsonify({'success': True, 'message': 'Уже в избранном'})

        supabase.table('favorites').insert({
            'user_id': user_id,
            'target_id': worker_id,
            'created_at': 'now()'
        }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/favorites')
@login_required
def favorites():
    user_id = get_current_user_id()
    role = session.get('role')

    favs = supabase.table('favorites').select('*, target:target_id(*)').eq('user_id', user_id).execute().data
    items = []
    for fav in favs:
        target = fav.get('target', {})
        if target:
            items.append({'id': fav['id'], 'target': target})

    favorite_jobs = []
    if role == 'worker':
        try:
            fav_jobs = supabase.table('favorite_jobs').select('*, job:job_id(*)').eq('user_id', user_id).execute().data
            for fj in fav_jobs:
                job = fj.get('job', {})
                if job:
                    favorite_jobs.append(job)
        except Exception:
            pass  # Таблица favorite_jobs может отсутствовать

    return render_template('favorites.html', items=items, favorite_jobs=favorite_jobs)


@app.route('/unfavorite/<target_id>', methods=['POST'])
@login_required
def unfavorite(target_id):
    user_id = get_current_user_id()
    supabase.table('favorites').delete().eq('user_id', user_id).eq('target_id', target_id).execute()
    flash('Удалено из избранного', 'info')
    return redirect(url_for('favorites'))


@app.route('/unfavorite-job/<job_id>', methods=['POST'])
@login_required
def unfavorite_job(job_id):
    user_id = get_current_user_id()
    try:
        supabase.table('favorite_jobs').delete().eq('user_id', user_id).eq('job_id', job_id).execute()
        flash('Удалено из избранного', 'info')
    except Exception:
        flash('Функция избранных заданий временно недоступна', 'info')
    return redirect(url_for('favorites'))


# ===================== ОТКЛИКИ НА ЗАДАНИЯ =====================

@app.route('/apply/<job_id>', methods=['POST'])
@login_required
def apply_job(job_id):
    user_id = get_current_user_id()

    existing = supabase.table('applications').select('*').eq('job_id', job_id).eq('worker_id', user_id).execute()
    if existing.data:
        flash('Вы уже откликнулись на это задание', 'info')
        return redirect(url_for('job_detail', job_id=job_id))

    supabase.table('applications').insert({
        'job_id': job_id,
        'worker_id': user_id,
        'status': 'pending',
        'created_at': 'now()'
    }).execute()

    flash('Отклик отправлен!', 'success')
    return redirect(url_for('job_detail', job_id=job_id))


@app.route('/unapply/<job_id>', methods=['POST'])
@login_required
def unapply_job(job_id):
    user_id = get_current_user_id()
    supabase.table('applications').delete().eq('job_id', job_id).eq('worker_id', user_id).execute()
    flash('Отклик отозван', 'info')
    return redirect(url_for('job_detail', job_id=job_id))


@app.route('/favorite-job/<job_id>', methods=['POST'])
@login_required
def favorite_job(job_id):
    user_id = get_current_user_id()
    try:
        existing = supabase.table('favorite_jobs').select('*').eq('user_id', user_id).eq('job_id', job_id).execute()
        if not existing.data:
            supabase.table('favorite_jobs').insert({
                'user_id': user_id,
                'job_id': job_id,
                'created_at': 'now()'
            }).execute()
        flash('Добавлено в избранное!', 'success')
    except Exception:
        flash('Функция временно недоступна', 'info')
    return redirect(url_for('job_detail', job_id=job_id))


# ===================== СМЕНЫ =====================

@app.route('/shifts')
@login_required
def shifts():
    user_id = get_current_user_id()
    role = session.get('role')

    if role == 'employer':
        data = supabase.table('shifts').select('*, job:job_id(*), worker:worker_id(*)').eq('employer_id', user_id).order('created_at', desc=True).execute().data
    else:
        data = supabase.table('shifts').select('*, job:job_id(*), worker:worker_id(*)').eq('worker_id', user_id).order('created_at', desc=True).execute().data

    return render_template('shifts.html', shifts=data)


@app.route('/shift/<shift_id>/action', methods=['POST'])
@login_required
def shift_action(shift_id):
    user_id = get_current_user_id()
    action = request.form.get('action')

    if action == 'checkin':
        supabase.table('shifts').update({'status': 'active', 'worker_checkin': True, 'start_time': 'now()'}).eq('id', shift_id).execute()
    elif action == 'complete':
        supabase.table('shifts').update({'status': 'completed', 'worker_complete': True}).eq('id', shift_id).execute()
    elif action == 'confirm_payment_employer':
        supabase.table('shifts').update({'employer_payment_confirmed': True, 'employer_confirm': True}).eq('id', shift_id).execute()
    elif action == 'confirm_payment_worker':
        supabase.table('shifts').update({'worker_payment_confirmed': True}).eq('id', shift_id).execute()

    flash('Статус обновлён!', 'success')
    return redirect(url_for('shifts'))


# ===================== ЧАТЫ (СПИСОК) =====================

@app.route('/chats')
@login_required
def chats_list():
    user_id = get_current_user_id()
    role = session.get('role')

    if role == 'employer':
        data = supabase.table('shifts').select('*, job:job_id(*), worker:worker_id(*)').eq('employer_id', user_id).order('created_at', desc=True).execute().data
    else:
        data = supabase.table('shifts').select('*, job:job_id(*), worker:worker_id(*)').eq('worker_id', user_id).order('created_at', desc=True).execute().data

    return render_template('chats_list.html', chats=data)


# ===================== ВЕРИФИКАЦИЯ РАБОТОДАТЕЛЯ =====================

@app.route('/verify-employer')
@login_required
def verify_employer():
    return render_template('verify_employer.html')


# ===================== АДМИНКА =====================

@app.route('/admin')
@login_required
def admin():
    users = supabase.table('profiles').select('*').execute().data
    return render_template('admin.html', users=users)


@app.route('/admin/approve/<user_id>')
@login_required
def admin_approve(user_id):
    supabase.table('profiles').update({'verification_status': 'approved'}).eq('id', user_id).execute()
    flash('Пользователь одобрен', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/reject/<user_id>')
@login_required
def admin_reject(user_id):
    supabase.table('profiles').update({'verification_status': 'rejected'}).eq('id', user_id).execute()
    flash('Пользователь отклонён', 'info')
    return redirect(url_for('admin'))


# ===================== ЗАПУСК =====================

if __name__ == '__main__':
    app.run(debug=True)