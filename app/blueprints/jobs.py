from datetime import datetime

from flask import Blueprint, current_app, jsonify, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required, role_required
from app.utils import calculate_distance, copy_job, supabase_request

jobs_bp = Blueprint('jobs', __name__)

# Юридически значимое: стоп-слова для предотвращения переквалификации
# в трудовые отношения (ст. 15 ТК РФ)
STOP_WORDS = ["ставка", "зарплата", "штат", "трудовая", "график", "постоянная работа", "вахта"]


def check_stop_words(text):
    """Проверить текст на наличие стоп-слов. Возвращает список найденных."""
    if not text:
        return []
    text_lower = text.lower()
    return [word for word in STOP_WORDS if word in text_lower]


# ──────────────────────────────────────────────
# Контекстные процессоры
# ──────────────────────────────────────────────

@jobs_bp.app_context_processor
def inject_application_count():
    count = 0
    if session.get('role') == 'employer' and 'user_id' in session:
        resp = supabase_request('GET',
            f'applications?job.employer_id=eq.{session["user_id"]}&status=eq.pending&select=id')
        if resp.ok and resp.json():
            count = len(resp.json())
    return {'pending_app_count': count}


@jobs_bp.app_context_processor
def inject_user_role():
    return {'current_user_role': session.get('role')}


# @jobs_bp.app_context_processor
# def inject_user_id():
#     return {'current_user_id': session.get('user_id')}


# ──────────────────────────────────────────────
# Публичные маршруты
# ──────────────────────────────────────────────

@jobs_bp.route('/')
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


@jobs_bp.route('/workers')
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


@jobs_bp.route('/jobs/<job_id>')
def job_detail(job_id):
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*,photos:job_photos(*)')
    job = resp.json()[0] if resp.ok and resp.json() else None
    if not job:
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.index'))

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
                           yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'],
                           already_applied=already_applied,
                           current_user_role=session.get('role'))


# ──────────────────────────────────────────────
# Создание заданий
# ──────────────────────────────────────────────

@jobs_bp.route('/job/new', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def job_new():
    """Создание задания (единственный маршрут, заменяет /create-job)"""
    if request.method == 'POST':
        try:
            title = request.form.get('title') or 'Храм'
            description = request.form.get('description', '')

            # Юридически значимое действие: проверка стоп-слов для предотвращения
            # переквалификации в трудовые отношения (ст. 15 ТК РФ)
            found_in_title = check_stop_words(title)
            found_in_desc = check_stop_words(description)
            stop_words_found = found_in_title + found_in_desc
            if stop_words_found:
                flash(
                    f'Обнаружены слова, характерные для трудовых отношений: '
                    f'{", ".join(stop_words_found)}. '
                    f'Пожалуйста, опишите разовую услугу.',
                    'danger'
                )
                return render_template('job_new.html', yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'])

            job_data = {
                'employer_id': session['user_id'],
                'organization_name': title,
                'org_description': '',
                'object_description': '',
                'work_type': '',
                'detailed_description': description,
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

            resp = supabase_request('POST', 'jobs', json=job_data)

            if not resp.ok:
                pass  # log handled in utils

            if resp.ok:
                flash('Задание опубликовано', 'success')
                return redirect(url_for('jobs.my_jobs'))
            else:
                flash(f'Ошибка создания задания: {resp.text}', 'danger')
        except Exception as e:
            flash('Ошибка сервера', 'danger')

    return render_template('job_new.html', yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'])


# ──────────────────────────────────────────────
# Мои задания (работодатель)
# ──────────────────────────────────────────────

@jobs_bp.route('/my-jobs')
@login_required
def my_jobs():
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('jobs.index'))

    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')

    if status_filter == 'all':
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')
    else:
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&status=eq.{status_filter}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')

    jobs = resp.json() if resp.ok else []

    for job in jobs:
        app_resp = supabase_request('GET', f'applications?job_id=eq.{job["id"]}&select=id')
        job['application_count'] = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0

    return render_template('my_jobs.html', jobs=jobs, current_status=status_filter)


@jobs_bp.route('/my-jobs/action', methods=['POST'])
@login_required
def my_jobs_action():
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('jobs.index'))

    user_id = session['user_id']
    action = request.form.get('action')
    job_ids = request.form.getlist('job_ids')

    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.my_jobs'))

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
    return redirect(url_for('jobs.my_jobs'))


# ──────────────────────────────────────────────
# Отдельные действия над заданиями
# ──────────────────────────────────────────────

@jobs_bp.route('/repost-job/<job_id>', methods=['POST'])
@login_required
@role_required('employer')
def repost_job(job_id):
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
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/cancel-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def cancel_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание отозвано'})
    flash('Задание отозвано', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/restore-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def restore_job(job_id):
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'open'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание восстановлено'})
    flash('Задание восстановлено', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/delete-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def delete_job(job_id):
    supabase_request('DELETE', f'jobs?id=eq.{job_id}')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание удалено'})
    flash('Задание удалено', 'success')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('jobs.my_jobs'))


# ──────────────────────────────────────────────
# Избранные задания
# ──────────────────────────────────────────────

@jobs_bp.route('/favorite-job/<job_id>', methods=['POST'])
@login_required
def add_favorite_job(job_id):
    supabase_request('POST', 'job_favorites', json={'user_id': session['user_id'], 'job_id': job_id})
    flash('Задание добавлено в избранное', 'success')
    return redirect(request.referrer or url_for('jobs.index'))


@jobs_bp.route('/unfavorite-job/<job_id>', methods=['POST'])
@login_required
def remove_favorite_job(job_id):
    supabase_request('DELETE', f'job_favorites?user_id=eq.{session["user_id"]}&job_id=eq.{job_id}')
    flash('Задание удалено из избранного', 'success')
    return redirect(request.referrer or url_for('favorites.favorites'))
