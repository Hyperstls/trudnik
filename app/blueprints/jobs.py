from datetime import datetime, timezone, timedelta

from flask import Blueprint, current_app, jsonify, flash, redirect, render_template, request, session, url_for, abort

from app.config import Config
from app.decorators import login_required, role_required
from app.utils import (
    calculate_distance, check_withdraw_window, copy_job, rate_limit,
    sanitize_postgrest, supabase_admin_request, supabase_request, supabase_rpc,
)
from app.services.notification_service import create as notify
from app.services.job_service import (
    check_job_owner,
    check_job_visibility,
    enrich_job_with_references,
    get_job_by_id,
)

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





# ──────────────────────────────────────────────
# Публичные маршруты
# ──────────────────────────────────────────────

@jobs_bp.route('/')
def index():
    city = request.args.get('city', '')
    payment_min = request.args.get('payment_min', '')
    payment_max = request.args.get('payment_max', '')
    lat = request.args.get('lat', type=float) or session.get('lat')
    lng = request.args.get('lng', type=float) or session.get('lng')
    radius = request.args.get('radius', 20, type=float)
    sort = request.args.get('sort', 'newest')
    skills_filter = request.args.get('skills', '')
    religion = request.args.get('religion', '')

    now = datetime.now(timezone.utc).isoformat()

    # Запрос только оплаченных открытых заданий (без detailed_description — тяжёлое поле)
    query = 'status=in.(open,completed)&select=id,employer_id,organization_name,org_description,object_description,work_type,date_time,payment_amount,address,city,lat,lng,status,created_at,preferred_religion,max_workers,current_workers,expires_at,tariff,photos:job_photos(*)'
    if city: query += f'&city=ilike.*{sanitize_postgrest(city)}*'
    if payment_min: query += f'&payment_amount=gte.{sanitize_postgrest(payment_min)}'
    if payment_max: query += f'&payment_amount=lte.{sanitize_postgrest(payment_max)}'
    if religion: query += f'&preferred_religion=eq.{sanitize_postgrest(religion)}'

    resp = supabase_request('GET', f'jobs?{query}&order=created_at.desc')
    jobs = resp.json() if resp.ok else []

    # Фильтрация: открытые, не истёкшие
    jobs = [j for j in jobs if j.get('status') in ('open', 'completed')]
    jobs = [j for j in jobs if not j.get('expires_at') or j['expires_at'] > now]

    # Фильтрация: исключаем задания от работодателей, заблокировавших текущего трудника
    if session.get('role') == 'worker' and 'user_id' in session:
        bl_resp = supabase_request('GET',
            f'blacklists?blocked_user_id=eq.{session["user_id"]}&select=user_id')
        if bl_resp.ok and bl_resp.json():
            blocked_employer_ids = {b['user_id'] for b in bl_resp.json()}
            jobs = [j for j in jobs if j.get('employer_id') not in blocked_employer_ids]

    # Фильтрация по навыкам (поиск в work_type, object_description, detailed_description)
    if skills_filter:
        selected_skills = [s.strip().lower() for s in skills_filter.split(',') if s.strip()]
        if selected_skills:
            jobs = [j for j in jobs if any(
                sk in (j.get('work_type', '') + ' ' + j.get('object_description', '') + ' ' + j.get('detailed_description', '')).lower()
                for sk in selected_skills
            )]

    if lat is not None and lng is not None:
        for job in jobs:
            job['distance'] = calculate_distance(lat, lng, job['lat'], job['lng'])
        if radius:
            jobs = [j for j in jobs if j.get('distance', float('inf')) <= radius]

    # Сортировка
    if sort == 'distance' and lat is not None:
        jobs.sort(key=lambda x: x.get('distance', float('inf')))
    elif sort == 'rating':
        # Получаем рейтинги работодателей для сортировки
        if jobs:
            employer_ids = list({j['employer_id'] for j in jobs if j.get('employer_id')})
            if employer_ids:
                ids_filter = ','.join(employer_ids)
                rating_resp = supabase_request('GET',
                    f'profiles?id=in.({ids_filter})&select=id,rating')
                if rating_resp.ok and rating_resp.json():
                    rating_map = {p['id']: p.get('rating', 0) or 0 for p in rating_resp.json()}
                    jobs.sort(key=lambda x: rating_map.get(x.get('employer_id'), 0), reverse=True)
    elif sort in ('payment_asc', 'price_asc'):
        jobs.sort(key=lambda x: x['payment_amount'])
    elif sort in ('payment_desc', 'price_desc'):
        jobs.sort(key=lambda x: x['payment_amount'], reverse=True)
    # sort == 'newest' — уже отсортировано по created_at.desc из запроса

    applied_job_ids = []
    if session.get('role') == 'worker' and 'user_id' in session:
        app_resp = supabase_request('GET',
            f'applications?worker_id=eq.{session["user_id"]}&select=job_id')
        if app_resp.ok and app_resp.json():
            applied_job_ids = [a['job_id'] for a in app_resp.json()]

    selected_skills_list = [s.strip() for s in skills_filter.split(',') if s.strip()] if skills_filter else []
    return render_template('index.html', jobs=jobs, applied_job_ids=applied_job_ids,
                           lat=lat, lng=lng, radius=radius, sort=sort,
                            selected_skills=selected_skills_list)


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
    sort = request.args.get('sort', 'rating')
    lat = request.args.get('lat', type=float) or session.get('lat')
    lng = request.args.get('lng', type=float) or session.get('lng')

    query = 'role=eq.worker'
    if filters['city']: query += f'&city=ilike.*{sanitize_postgrest(filters["city"])}*'
    if filters['experience']: query += f'&experience=ilike.*{sanitize_postgrest(filters["experience"])}*'
    if filters['payment_from']: query += f'&desired_payment=gte.{filters["payment_from"]}'
    if filters['payment_to']: query += f'&desired_payment=lte.{filters["payment_to"]}'
    if filters['rating_min']: query += f'&rating=gte.{filters["rating_min"]}'
    if filters['skills']:
        for skill in filters['skills'].split(','):
            query += f'&skills=cs.{{{sanitize_postgrest(skill.strip())}}}'
    if filters['religion']:
        query += f'&religion=eq.{sanitize_postgrest(filters["religion"])}'

    # Определяем order в зависимости от sort
    order = 'rating.desc'
    if sort == 'name':
        order = 'full_name.asc'
    elif sort in ('price_asc',):
        order = 'desired_payment.asc.nullslast'
    elif sort in ('price_desc',):
        order = 'desired_payment.desc.nullslast'

    resp = supabase_request('GET', f'profiles?{query}&order={order}')
    workers_list = resp.json() if resp.ok else []

    # Сортировка по расстоянию (после загрузки, если есть координаты)
    if sort == 'distance' and lat is not None and lng is not None:
        for w in workers_list:
            w_lat = w.get('lat')
            w_lng = w.get('lng')
            if w_lat is not None and w_lng is not None:
                w['distance'] = calculate_distance(lat, lng, w_lat, w_lng)
            else:
                w['distance'] = float('inf')
        workers_list.sort(key=lambda x: x.get('distance', float('inf')))

    # Определяем, какие трудники уже приглашены работодателем
    invited_worker_ids = set()
    if session.get('role') == 'employer' and workers_list:
        worker_ids = [w['id'] for w in workers_list if w.get('id')]
        if worker_ids:
            ids_filter = ','.join(worker_ids)
            inv_resp = supabase_request('GET',
                f'invitations?employer_id=eq.{session["user_id"]}&worker_id=in.({ids_filter})&status=in.(pending,accepted)&select=worker_id')
            if inv_resp.ok and inv_resp.json():
                invited_worker_ids = {inv['worker_id'] for inv in inv_resp.json()}

    selected_skills_list = [s.strip() for s in filters['skills'].split(',') if s.strip()] if filters['skills'] else []
    return render_template('workers.html', workers=workers_list, selected_skills=selected_skills_list,
                           invited_worker_ids=invited_worker_ids, sort=sort, lat=lat, lng=lng)


@jobs_bp.route('/jobs/<job_id>')
def job_detail(job_id):
    """Детальная страница задания."""
    # Валидация UUID формата перед любыми запросами к БД
    from uuid import UUID
    try:
        UUID(job_id)
    except (ValueError, AttributeError):
        abort(404)
    job = get_job_by_id(job_id)
    if not job:
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.index'))

    # Проверка видимости (вынесена в сервис)
    if not check_job_visibility(job, session.get('user_id'), session.get('role')):
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.index'))

    is_owner = session.get('user_id') and job.get('employer_id') == session.get('user_id')

    # Загружаем профиль работодателя для проверки верификации
    employer = None
    if job.get('employer_id'):
        emp_resp = supabase_request('GET',
            f'profiles?id=eq.{job["employer_id"]}&select=id,full_name,verification_status')
        if emp_resp.ok and emp_resp.json():
            employer = emp_resp.json()[0]

    # Резолвим UUID полей work_type и preferred_religion в читаемые названия
    enrich_job_with_references(job)

    if is_owner:
        app_resp = supabase_request('GET', f'applications?job_id=eq.{job_id}&select=id')
        job['application_count'] = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0
    else:
        job['application_count'] = 0

    already_applied = False
    my_app_status = None
    my_app_id = None
    can_withdraw = True
    if 'user_id' in session:
        app_resp = supabase_request('GET',
            f'applications?job_id=eq.{job_id}&worker_id=eq.{session["user_id"]}&select=id,status')
        if app_resp.ok and app_resp.json():
            already_applied = True
            app_data = app_resp.json()[0]
            my_app_status = app_data.get('status')
            my_app_id = app_data.get('id')
            can_withdraw = check_withdraw_window(job.get('date_time'))

    # Проверка: добавлен ли работодатель в избранное у трудника
    is_employer_favorited = False
    if session.get('role') == 'worker' and session.get('user_id') and job.get('employer_id'):
        fav_check = supabase_request('GET',
            f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{job["employer_id"]}&favorite_type=eq.employer')
        is_employer_favorited = bool(fav_check.json()) if fav_check.ok else False

    return render_template('job_detail.html', job=job,
                           employer=employer,
                           yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'],
                           already_applied=already_applied,
                           my_app_status=my_app_status,
                           my_app_id=my_app_id,
                           can_withdraw=can_withdraw,
                           current_user_role=session.get('role'),
                           is_employer_favorited=is_employer_favorited)


# ──────────────────────────────────────────────
# Создание заданий
# ──────────────────────────────────────────────

@jobs_bp.route('/job/new', methods=['GET', 'POST'])
@login_required
@role_required('employer')
@rate_limit
def job_new():
    """Создание задания (единственный маршрут, заменяет /create-job)"""
    # Загружаем справочники из БД
    skills_resp = supabase_request('GET', 'skills?select=id,name&order=sort_order.asc,name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = supabase_request('GET', 'religions?select=id,name&order=sort_order.asc,name.asc')
    religions_list = religions_resp.json() if religions_resp.ok else []

    template_data = {
        'yandex_api_key': current_app.config['YANDEX_MAPS_API_KEY'],
        'skills_list': skills_list,
        'religions_list': religions_list,
    }

    if request.method == 'POST':
        try:
            title = request.form.get('title') or 'Храм'
            description = request.form.get('description', '')
            address = request.form.get('address', '')

            # Серверная валидация длины полей
            if len(title) > 255:
                flash('Поле «Название» слишком длинное (максимум 255 символов)', 'danger')
                return render_template('job_new.html', **template_data)
            if len(description) > 5000:
                flash('Поле «Описание» слишком длинное (максимум 5000 символов)', 'danger')
                return render_template('job_new.html', **template_data)
            if len(address) > 500:
                flash('Поле «Адрес» слишком длинное (максимум 500 символов)', 'danger')
                return render_template('job_new.html', **template_data)

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
                return render_template('job_new.html', **template_data)

            job_data = {
                'employer_id': session['user_id'],
                'organization_name': title,
                'org_description': '',
                'object_description': '',
                'work_type': request.form.get('work_type', ''),
                'detailed_description': description,
                'date_time': request.form.get('deadline') or datetime.now().isoformat(),
                'payment_amount': float(request.form.get('payment') or 0),
                'address': request.form.get('address', ''),
                'city': request.form.get('city', ''),
                'lat': float(request.form.get('latitude') or Config.DEFAULT_LAT),
                'lng': float(request.form.get('longitude') or Config.DEFAULT_LNG),
                'preferred_religion': request.form.get('preferred_religion', ''),
                'max_workers': int(request.form.get('max_workers') or 1),
                'current_workers': 0,
                'status': 'open',
                'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }

            resp = supabase_request('POST', 'jobs', json=job_data)

            if not resp.ok:
                current_app.logger.error(f'Failed to create job: {resp.text}')

            if resp.ok:
                created_job = resp.json()
                if isinstance(created_job, list):
                    created_job = created_job[0]
                return redirect(url_for('jobs.my_jobs'))
            else:
                flash(f'Ошибка создания задания: {resp.text}', 'danger')
        except Exception as e:
            flash('Ошибка сервера', 'danger')

    return render_template('job_new.html', **template_data)


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
    elif status_filter == 'open':
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&status=eq.open&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')
    else:
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&status=eq.{status_filter}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')

    jobs = resp.json() if resp.ok else []

    # Batch query: получаем количество откликов для всех заданий одним запросом
    if jobs:
        job_ids = [j['id'] for j in jobs]
        ids_filter = ','.join(job_ids)
        app_resp = supabase_request('GET', f'applications?job_id=in.({ids_filter})&select=job_id')
        app_counts = {}
        if app_resp.ok and app_resp.json():
            for a in app_resp.json():
                jid = a['job_id']
                app_counts[jid] = app_counts.get(jid, 0) + 1
        for job in jobs:
            job['application_count'] = app_counts.get(job['id'], 0)

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
        if not check_job_owner(job_id, user_id):
            continue
        if action == 'restore':
            supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'open'})
        elif action == 'cancel':
            supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
        elif action == 'delete':
            supabase_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
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
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if resp.ok and resp.json():
        new_job = copy_job(resp.json()[0])
        supabase_request('POST', 'jobs', json=new_job)
        if is_ajax:
            return jsonify({'success': True, 'message': 'Задание дублировано'})
        flash('Задание дублировано', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Задание не найдено'}), 404
        flash('Задание не найдено', 'danger')

    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/cancel-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def cancel_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Блокировка: нельзя отозвать задание completed с принятыми работниками
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status')
    job_status = None
    if job_resp.ok and job_resp.json():
        job_status = job_resp.json()[0].get('status')

    # Блокировка: нельзя отозвать задание completed с принятыми работниками
    if job_status == 'completed':
        accepted_check = supabase_request('GET',
            f'applications?job_id=eq.{job_id}&status=eq.accepted&select=id')
        if accepted_check.ok and accepted_check.json():
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            msg = 'Невозможно отменить задание с принятыми работниками. Сначала попросите работников отозвать отклики.'
            if is_ajax:
                return jsonify({'success': False, 'error': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('jobs.my_jobs'))

    # Сбросить все pending отклики в rejected
    supabase_request('PATCH', f'applications?job_id=eq.{job_id}&status=eq.pending',
                     json={'status': 'rejected'})

    # Уведомить заявителей, что задание отозвано
    apps_resp = supabase_request('GET',
        f'applications?job_id=eq.{job_id}&status=eq.rejected&select=worker_id')
    if apps_resp.ok and apps_resp.json():
        for app in apps_resp.json():
            notify(app['worker_id'], 'job_cancelled', 'Задание отозвано',
                   f'Задание #{job_id} было отозвано работодателем',
                   data={'job_id': job_id, 'link': url_for('jobs.index', _external=True)})

    supabase_admin_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание отозвано'})
    flash('Задание отозвано', 'success')
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/restore-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def restore_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Получить текущее состояние задания
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,date_time,current_workers')
    if not job_resp.ok or not job_resp.json():
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

    job = job_resp.json()[0]
    if job.get('status') != 'cancelled':
        return jsonify({'success': False, 'error': 'Восстановить можно только отменённое задание'}), 409

    # Определить новый статус: open (если дата в будущем) или сохранить open
    new_status = 'open'

    # Сбросить все pending заявки в rejected (иначе unique constraint помешает переоткликнуться)
    supabase_request('PATCH', f'applications?job_id=eq.{job_id}&status=eq.pending',
                     json={'status': 'rejected'})

    # Сбросить все accepted заявки в rejected (работники должны заново откликнуться)
    supabase_request('PATCH', f'applications?job_id=eq.{job_id}&status=eq.accepted',
                     json={'status': 'rejected'})

    # Обнулить счётчик текущих работников
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
        'status': new_status,
        'current_workers': 0
    })

    # Уведомить всех rejected-заявителей, что задание восстановлено
    apps_resp = supabase_request('GET',
        f'applications?job_id=eq.{job_id}&status=eq.rejected&select=worker_id')
    if apps_resp.ok and apps_resp.json():
        for app in apps_resp.json():
            notify(app['worker_id'], 'status_change', 'Задание восстановлено',
                   f'Задание #{job_id} снова открыто для откликов',
                   data={'job_id': job_id, 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return jsonify({'success': True, 'message': 'Задание восстановлено', 'new_status': new_status})
    flash('Задание восстановлено', 'success')
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/api/jobs/<job_id>/force-complete', methods=['POST'])
@login_required
@role_required('employer')
def api_force_complete_job(job_id):
    """Принудительное завершение задания работодателем.
    Переводит из open → completed.
    Уведомляет всех accepted workers, массово отклоняет pending."""
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Получить задание
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,current_workers,max_workers')
    if not job_resp.ok or not job_resp.json():
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

    job = job_resp.json()[0]
    if job['status'] != 'open':
        return jsonify({'success': False, 'error': f'Нельзя завершить задание в статусе «{job["status"]}». Ожидается open.'}), 409

    # Массово отклонить все pending отклики
    supabase_request('PATCH', f'applications?job_id=eq.{job_id}&status=eq.pending',
                     json={'status': 'rejected'})

    # Перевести задание в completed
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'completed'})

    # Уведомить всех accepted работников
    apps_resp = supabase_request('GET',
        f'applications?job_id=eq.{job_id}&status=eq.accepted&select=worker_id')
    if apps_resp.ok and apps_resp.json():
        for app in apps_resp.json():
            notify(app['worker_id'], 'force_complete', 'Задание завершено',
                   f'Работодатель завершил задание #{job_id}',
                   data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})

    return jsonify({
        'success': True,
        'message': 'Задание принудительно завершено',
        'new_status': 'completed'
    })


@jobs_bp.route('/delete-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def delete_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Блокировка: предупреждение при наличии принятых откликов (матрица секция 6.1)
    apps_resp = supabase_request('GET', f'applications?job_id=eq.{job_id}&status=eq.accepted&select=id')
    has_accepted = apps_resp.ok and apps_resp.json()

    if has_accepted:
        # Требуем явный параметр подтверждения через AJAX
        data = request.get_json(silent=True) or {}
        if not data.get('confirm'):
            return jsonify({'success': False, 'error': 'У задания есть принятые отклики. Подтвердите удаление.', 'needs_confirm': True}), 409

    # Каскадное удаление связанных записей (через service_role для обхода RLS)
    cascade_tables = [
        ('applications', f'job_id=eq.{job_id}'),
        ('job_skills', f'job_id=eq.{job_id}'),
        ('job_photos', f'job_id=eq.{job_id}'),
        ('job_favorites', f'job_id=eq.{job_id}'),
        ('_archive_contact_payments', f'job_id=eq.{job_id}'),
        ('job_payments', f'job_id=eq.{job_id}'),
        ('invitations', f'job_id=eq.{job_id}'),
    ]
    for table, condition in cascade_tables:
        supabase_admin_request('DELETE', f'{table}?{condition}')
    # Уведомления — ищем job_id в тексте (колонки job_id нет в production)
    supabase_admin_request('DELETE', f'notifications?message=ilike.*{job_id}*')

    supabase_admin_request('DELETE', f'jobs?id=eq.{job_id}')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание удалено'})
    flash('Задание удалено', 'success')
    return redirect(url_for('jobs.my_jobs'))


# ──────────────────────────────────────────────
# Приглашения (employer → worker)
# ──────────────────────────────────────────────

@jobs_bp.route('/invitations')
@login_required
def invitations_page():
    """HTML-страница приглашений."""
    user_id = session['user_id']
    role = session.get('role', 'worker')
    if role == 'worker':
        resp = supabase_request('GET',
            f'invitations?worker_id=eq.{user_id}&select=*,job:jobs(organization_name,payment_amount)&order=created_at.desc')
    else:
        resp = supabase_request('GET',
            f'invitations?employer_id=eq.{user_id}&select=*,job:jobs(organization_name),worker:profiles!invitations_worker_id_fkey(full_name)&order=created_at.desc')
    invitations = resp.json() if resp.ok else []
    return render_template('invitations.html', invitations=invitations)


@jobs_bp.route('/api/invitations/reject-all', methods=['POST'])
@login_required
def reject_all_invitations():
    """Отклонить все ожидающие приглашения текущего пользователя."""
    user_id = session['user_id']
    supabase_admin_request('PATCH',
        f'invitations?worker_id=eq.{user_id}&status=eq.pending',
        json={'status': 'rejected', 'responded_at': 'now()'})
    return jsonify({'success': True})


@jobs_bp.route('/jobs/<job_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('employer')
@rate_limit
def edit_job(job_id):
    # Используем admin_request для обхода RLS — работодатель должен видеть
    # своё задание в любом статусе (включая неоплаченные)
    job_resp = supabase_admin_request('GET', f'jobs?id=eq.{job_id}&select=*')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.my_jobs'))
    job = job_resp.json()[0]
    if job['employer_id'] != session['user_id']:
        flash('Нет доступа', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    # Проверить наличие accepted-откликов (P1: блокировка редактирования)
    apps_check = supabase_request('GET',
        f'applications?job_id=eq.{job_id}&status=eq.accepted&select=id')
    has_accepted = apps_check.ok and apps_check.json()

    # Загружаем справочники
    skills_resp = supabase_request('GET', 'skills?select=id,name&order=sort_order.asc,name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = supabase_request('GET', 'religions?select=id,name&order=sort_order.asc,name.asc')
    religions_list = religions_resp.json() if religions_resp.ok else []

    if request.method == 'POST':
        # Если есть accepted-отклики, разрешить редактировать только description и contact_phone
        if has_accepted:
            allowed_fields = {'detailed_description', 'contact_phone'}
            submitted_fields = set(request.form.keys())
            # Разрешены только description, contact_phone, csrf_token
            forbidden = submitted_fields - allowed_fields - {'_csrf_token', 'csrf_token'}
            if forbidden:
                is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                msg = 'Нельзя редактировать задание, на которое уже есть принятые отклики. Разрешено изменять только описание и контактный телефон.'
                if is_ajax:
                    return jsonify({'success': False, 'error': msg}), 409
                flash(msg, 'danger')
                return redirect(url_for('jobs.job_detail', job_id=job_id))

        data = {
            'organization_name': request.form.get('title', job['organization_name']),
            'detailed_description': request.form.get('description', job.get('detailed_description', '')),
            'work_type': request.form.get('work_type', job.get('work_type', '')),
            'payment_amount': float(request.form.get('payment') or job.get('payment_amount', 0)),
            'city': request.form.get('city', job.get('city', '')),
            'address': request.form.get('address', job.get('address', '')),
            'max_workers': int(request.form.get('max_workers', job.get('max_workers', 1))),
            'preferred_religion': request.form.get('preferred_religion', job.get('preferred_religion', '')),
            'date_time': request.form.get('deadline') or job.get('date_time', ''),
        }
        resp = supabase_request('PATCH', f'jobs?id=eq.{job_id}', json=data)
        if resp.ok:
            flash('Задание обновлено', 'success')
            return redirect(url_for('jobs.job_detail', job_id=job_id))
        else:
            flash('Ошибка обновления', 'danger')

    return render_template('job_new.html',
        job=job,
        is_edit=True,
        skills_list=skills_list,
        religions_list=religions_list,
        yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'])


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


# ──────────────────────────────────────────────
