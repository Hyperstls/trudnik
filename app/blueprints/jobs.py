from datetime import datetime, timezone, timedelta

from flask import Blueprint, current_app, jsonify, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required, role_required
from app.utils import calculate_distance, copy_job, sanitize_postgrest, supabase_admin_request, supabase_request
from app.services.notification_service import create as notify

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
# Публичные справочники (навыки, вероисповедания)
# ──────────────────────────────────────────────

@jobs_bp.route('/api/skills')
def api_skills():
    resp = supabase_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
    return {'skills': resp.json() if resp.ok else []}

@jobs_bp.route('/api/religions')
def api_religions():
    resp = supabase_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
    return {'religions': resp.json() if resp.ok else []}


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
    skills_filter = request.args.get('skills', '')

    now = datetime.now(timezone.utc).isoformat()

    # Запрос только оплаченных открытых заданий
    query = 'status=eq.open&is_paid=eq.true&select=*,photos:job_photos(*)'
    if city: query += f'&city=ilike.*{sanitize_postgrest(city)}*'
    if payment_min: query += f'&payment_amount=gte.{sanitize_postgrest(payment_min)}'
    if payment_max: query += f'&payment_amount=lte.{sanitize_postgrest(payment_max)}'

    resp = supabase_request('GET', f'jobs?{query}&order=created_at.desc')
    jobs = resp.json() if resp.ok else []

    # Автопереход in_progress → active для каждого задания
    for job in jobs:
        _auto_transition_in_progress_to_active(job)

    # Фильтрация: только открытые, оплаченные, не истёкшие
    jobs = [j for j in jobs if j.get('status') == 'open' and j.get('is_paid')]
    jobs = [j for j in jobs if not j.get('expires_at') or j['expires_at'] > now]

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

    selected_skills_list = [s.strip() for s in skills_filter.split(',') if s.strip()] if skills_filter else []
    return render_template('index.html', jobs=jobs, applied_job_ids=applied_job_ids,
                           lat=lat, lng=lng, radius=radius, sort=sort,
                            selected_skills=selected_skills_list)


# ──────────────────────────────────────────────
# API поиска (полнотекстовый + фильтры + пагинация)
# ──────────────────────────────────────────────

@jobs_bp.route('/api/search/jobs')
def api_search_jobs():
    """Поиск заданий с полнотекстовым поиском, фильтрами и пагинацией."""
    q = request.args.get('q', '')
    status = request.args.get('status', 'open')
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 20, type=float)
    min_pay = request.args.get('min_pay', type=int)
    max_pay = request.args.get('max_pay', type=int)
    skills = request.args.get('skills', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    available_slots = request.args.get('available_slots', 'false').lower() == 'true'
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 20, type=int)))
    sort = request.args.get('sort', '')

    # Базовые поля
    select = '*,photos:job_photos(*)'
    query_parts = [f'select={select}']

    # Статус
    if status:
        query_parts.append(f'status=eq.{sanitize_postgrest(status)}')

    # Полнотекстовый поиск
    if q:
        query_parts.append(f'search_vector=fts.russian.{sanitize_postgrest(q)}')

    # Фильтры
    if min_pay is not None:
        query_parts.append(f'payment_amount=gte.{min_pay}')
    if max_pay is not None:
        query_parts.append(f'payment_amount=lte.{max_pay}')
    if date_from:
        query_parts.append(f'date_time=gte.{sanitize_postgrest(date_from)}')
    if date_to:
        query_parts.append(f'date_time=lte.{sanitize_postgrest(date_to)}')
    if available_slots:
        query_parts.append('current_workers=lt.max_workers')

    # Пагинация
    offset = (page - 1) * per_page
    query_parts.append(f'limit={per_page}')
    query_parts.append(f'offset={offset}')

    # Сортировка
    if sort == 'date_desc':
        query_parts.append('order=date_time.desc')
    elif sort == 'payment_asc':
        query_parts.append('order=payment_amount.asc')
    elif sort == 'payment_desc':
        query_parts.append('order=payment_amount.desc')
    else:
        query_parts.append('order=created_at.desc')

    query = '&'.join(query_parts)

    # Запрос с подсчётом общего количества
    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET', f'jobs?{query}', headers=headers)
    jobs_list = resp.json() if resp.ok else []
    total = int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1]) if resp.ok else 0

    # Гео-фильтрация и расчёт расстояния (клиентская)
    if lat is not None and lng is not None:
        for job in jobs_list:
            if job.get('lat') and job.get('lng'):
                job['distance'] = calculate_distance(lat, lng, job['lat'], job['lng'])
        if radius:
            jobs_list = [j for j in jobs_list if j.get('distance', float('inf')) <= radius]
        if sort == 'distance':
            jobs_list.sort(key=lambda x: x.get('distance', float('inf')))

    # Фильтрация по навыкам (если не использовался FTS)
    if skills and not q:
        selected = [s.strip().lower() for s in skills.split(',') if s.strip()]
        if selected:
            jobs_list = [j for j in jobs_list if any(
                sk in (j.get('work_type', '') + ' ' + j.get('object_description', '') + ' ' + j.get('detailed_description', '')).lower()
                for sk in selected
            )]

    return {
        'results': jobs_list,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1
    }


@jobs_bp.route('/api/search/workers')
def api_search_workers():
    """Поиск трудников с полнотекстовым поиском, фильтрами и пагинацией."""
    q = request.args.get('q', '')
    skills = request.args.get('skills', '')
    rating_min = request.args.get('rating_min', type=float)
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 20, type=float)
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 20, type=int)))
    sort = request.args.get('sort', '')

    query_parts = ['select=*', 'role=eq.worker']

    if q:
        query_parts.append(f'search_vector=fts.russian.{sanitize_postgrest(q)}')
    if rating_min is not None:
        query_parts.append(f'rating=gte.{rating_min}')
    if skills:
        for sk in skills.split(','):
            sk = sk.strip()
            if sk:
                query_parts.append(f'skills=cs.{{{sanitize_postgrest(sk)}}}')

    offset = (page - 1) * per_page
    query_parts.append(f'limit={per_page}')
    query_parts.append(f'offset={offset}')

    if sort == 'rating_desc':
        query_parts.append('order=rating.desc')
    elif sort == 'payment_asc':
        query_parts.append('order=desired_payment.asc')
    else:
        query_parts.append('order=rating.desc')

    query = '&'.join(query_parts)
    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET', f'profiles?{query}', headers=headers)
    workers_list = resp.json() if resp.ok else []
    total = int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1]) if resp.ok else 0

    if lat is not None and lng is not None:
        for w in workers_list:
            if w.get('lat') and w.get('lng'):
                w['distance'] = calculate_distance(lat, lng, w['lat'], w['lng'])
        if radius:
            workers_list = [w for w in workers_list if w.get('distance', float('inf')) <= radius]
        if sort == 'distance':
            workers_list.sort(key=lambda x: x.get('distance', float('inf')))

    return {
        'results': workers_list,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1
    }


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

    resp = supabase_request('GET', f'profiles?{query}&order=rating.desc')
    workers_list = resp.json() if resp.ok else []

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
    return render_template('workers.html', workers=workers_list, selected_skills=selected_skills_list, invited_worker_ids=invited_worker_ids)


@jobs_bp.route('/jobs/<job_id>')
def job_detail(job_id):
    # Используем admin_request для обхода RLS — фильтрация видимости ниже
    resp = supabase_admin_request('GET', f'jobs?id=eq.{job_id}&select=*,photos:job_photos(*)')
    job = resp.json()[0] if resp.ok and resp.json() else None
    if not job:
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.index'))

    # Правила видимости:
    # - Владелец (employer) видит задание в ЛЮБОМ статусе и с любым is_paid
    # - Админ видит все задания
    # - Остальные — только оплаченные (is_paid=true) в статусах open, in_progress, active
    is_owner = session.get('user_id') and job.get('employer_id') == session.get('user_id')
    is_admin = session.get('role') == 'admin'
    if not is_owner and not is_admin:
        if not job.get('is_paid') or job.get('status') not in ('open', 'in_progress', 'active'):
            flash('Задание не найдено', 'danger')
            return redirect(url_for('jobs.index'))

    # Автопереход in_progress → active по date_time
    _auto_transition_in_progress_to_active(job)

    # Резолвим UUID полей work_type и preferred_religion в читаемые названия
    if job.get('work_type') and '-' in str(job['work_type']):
        skill_resp = supabase_request('GET', f'skills?id=eq.{job["work_type"]}&select=name')
        if skill_resp.ok and skill_resp.json():
            job['work_type'] = skill_resp.json()[0]['name']
    if job.get('preferred_religion') and '-' in str(job['preferred_religion']):
        rel_resp = supabase_request('GET', f'religions?id=eq.{job["preferred_religion"]}&select=name')
        if rel_resp.ok and rel_resp.json():
            job['preferred_religion'] = rel_resp.json()[0]['name']

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
            # Проверить, можно ли отозвать отклик (не позднее 12 часов до начала)
            if job.get('date_time'):
                try:
                    job_dt = datetime.fromisoformat(job['date_time'].replace('Z', '+00:00'))
                    can_withdraw = (job_dt - datetime.now(timezone.utc)).total_seconds() > 12 * 3600
                except (ValueError, TypeError):
                    can_withdraw = True

    return render_template('job_detail.html', job=job,
                           yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'],
                           already_applied=already_applied,
                           my_app_status=my_app_status,
                           my_app_id=my_app_id,
                           can_withdraw=can_withdraw,
                           current_user_role=session.get('role'))


# ──────────────────────────────────────────────
# Создание заданий
# ──────────────────────────────────────────────

@jobs_bp.route('/job/new', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def job_new():
    """Создание задания (единственный маршрут, заменяет /create-job)"""
    # Загружаем справочники из БД
    skills_resp = supabase_request('GET', 'skills?select=id,name&order=name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = supabase_request('GET', 'religions?select=id,name&order=name.asc')
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
                'date_time': datetime.now().isoformat(),
                'payment_amount': float(request.form.get('payment') or 0),
                'address': request.form.get('address', ''),
                'city': request.form.get('city', ''),
                'lat': float(request.form.get('latitude') or 55.75),
                'lng': float(request.form.get('longitude') or 37.61),
                'preferred_religion': request.form.get('preferred_religion', ''),
                'max_workers': int(request.form.get('max_workers') or 1),
                'current_workers': 0,
                'status': 'open',
                'is_paid': False,
            }

            resp = supabase_request('POST', 'jobs', json=job_data)

            if not resp.ok:
                current_app.logger.error(f'Failed to create job: {resp.text}')

            if resp.ok:
                created_job = resp.json()
                if isinstance(created_job, list):
                    created_job = created_job[0]
                return redirect(url_for('jobs.publish_job', job_id=created_job['id']))
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
    else:
        resp = supabase_request('GET', f'jobs?employer_id=eq.{user_id}&status=eq.{status_filter}&select=*,photos:job_photos(*),applications:applications(count),current_workers,max_workers')

    jobs = resp.json() if resp.ok else []

    # Автопереход in_progress → active для каждого задания
    for job in jobs:
        _auto_transition_in_progress_to_active(job)

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


def _check_job_owner(job_id, user_id):
    """Проверить, что задание принадлежит пользователю. Возвращает True/False."""
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=employer_id')
    if resp.ok and resp.json():
        return resp.json()[0].get('employer_id') == user_id
    return False


def _auto_transition_in_progress_to_active(job):
    """Если задание в статусе in_progress и его date_time наступило — перевести в active.
    Возвращает новый статус (или исходный, если переход не нужен).
    Альтернатива pg_cron, недоступному на бесплатном Supabase."""
    if job.get('status') != 'in_progress':
        return job.get('status')
    date_time_str = job.get('date_time')
    if not date_time_str:
        return job.get('status')
    try:
        if isinstance(date_time_str, str):
            date_time = datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
        else:
            return job.get('status')
    except (ValueError, TypeError):
        return job.get('status')
    now = datetime.now(timezone.utc)
    if date_time <= now:
        supabase_request('PATCH', f'jobs?id=eq.{job["id"]}', json={'status': 'active'})
        job['status'] = 'active'
        return 'active'
    return 'in_progress'


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
        if not _check_job_owner(job_id, user_id):
            continue
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
    if not _check_job_owner(job_id, session['user_id']):
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
    if not _check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Блокировка: нельзя отозвать задание в статусе active (уже началось)
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status')
    if job_resp.ok and job_resp.json():
        job_status = job_resp.json()[0].get('status')
        if job_status == 'active':
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            msg = 'Нельзя отозвать задание, которое уже началось. Дождитесь завершения.'
            if is_ajax:
                return jsonify({'success': False, 'error': msg}), 409
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
                   f'Задание #{job_id} было отозвано работодателем')

    supabase_admin_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': 'cancelled'})
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Задание отозвано'})
    flash('Задание отозвано', 'success')
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/restore-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def restore_job(job_id):
    if not _check_job_owner(job_id, session['user_id']):
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
            notify(app['worker_id'], 'job_restored', 'Задание восстановлено',
                   f'Задание #{job_id} снова открыто для откликов')

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
    Переводит из active/in_progress → completed.
    Уведомляет всех accepted workers, массово отклоняет pending."""
    if not _check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Получить задание
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,current_workers,max_workers')
    if not job_resp.ok or not job_resp.json():
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

    job = job_resp.json()[0]
    if job['status'] not in ('active', 'in_progress'):
        return jsonify({'success': False, 'error': f'Нельзя завершить задание в статусе «{job["status"]}». Ожидается active или in_progress.'}), 409

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
            notify(app['worker_id'], 'job_completed', 'Задание завершено',
                   f'Работодатель завершил задание #{job_id}')

    return jsonify({
        'success': True,
        'message': 'Задание принудительно завершено',
        'new_status': 'completed'
    })


@jobs_bp.route('/delete-job/<job_id>', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def delete_job(job_id):
    if not _check_job_owner(job_id, session['user_id']):
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

@jobs_bp.route('/api/invite/<job_id>/<worker_id>', methods=['POST'])
@login_required
@role_required('employer')
def invite_worker(job_id, worker_id):
    """Работодатель приглашает трудника на задание."""
    if not _check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Проверить, не приглашён ли уже
    check = supabase_request('GET', f'invitations?job_id=eq.{job_id}&worker_id=eq.{worker_id}&select=id')
    if check.ok and check.json():
        return jsonify({'success': False, 'error': 'Приглашение уже отправлено'}), 409

    # Проверить, есть ли свободные места
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers')
    if job_resp.ok and job_resp.json():
        job = job_resp.json()[0]
        if job['current_workers'] >= job['max_workers']:
            return jsonify({'success': False, 'error': 'Все места заняты'}), 409

    msg = request.get_json(silent=True) or {}
    inv = supabase_request('POST', 'invitations', json={
        'job_id': job_id,
        'employer_id': session['user_id'],
        'worker_id': worker_id,
        'message': msg.get('message', '')
    })
    if not inv.ok:
        return jsonify({'success': False, 'error': 'Ошибка при создании приглашения'}), 500

    # Уведомить трудника
    job_name = job_resp.json()[0].get('organization_name', job_id) if job_resp.ok else job_id
    create_notification(worker_id, 'application_received', 'Вас пригласили на задание',
           f'Работодатель приглашает вас на задание «{job_name}»',
           data={'job_id': job_id, 'type': 'invitation'})

    return jsonify({'success': True, 'message': 'Приглашение отправлено'})


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


@jobs_bp.route('/api/invitations')
@login_required
def list_invitations():
    """JSON API: список приглашений."""
    user_id = session['user_id']
    role = session.get('role', 'worker')
    if role == 'worker':
        resp = supabase_request('GET',
            f'invitations?worker_id=eq.{user_id}&select=*,job:jobs(organization_name,payment_amount)&order=created_at.desc')
    else:
        resp = supabase_request('GET',
            f'invitations?employer_id=eq.{user_id}&select=*,job:jobs(organization_name),worker:profiles!invitations_worker_id_fkey(full_name)&order=created_at.desc')
    return jsonify({'invitations': resp.json() if resp.ok else []})


@jobs_bp.route('/api/invitations/<invitation_id>/respond', methods=['POST'])
@login_required
def respond_invitation(invitation_id):
    """Трудник принимает или отклоняет приглашение."""
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('accept', 'reject'):
        return jsonify({'success': False, 'error': 'Укажите действие: accept или reject'}), 400

    if session.get('role') != 'worker':
        return jsonify({'success': False, 'error': 'Только трудник может отвечать на приглашения'}), 403

    inv_resp = supabase_request('GET', f'invitations?id=eq.{invitation_id}&select=worker_id,job_id,employer_id,status')
    if not inv_resp.ok or not inv_resp.json():
        return jsonify({'success': False, 'error': 'Приглашение не найдено'}), 404

    inv = inv_resp.json()[0]
    if inv['worker_id'] != session['user_id']:
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    if inv['status'] != 'pending':
        return jsonify({'success': False, 'error': f'Приглашение уже {inv["status"]}'}), 409

    new_status = 'accepted' if action == 'accept' else 'rejected'
    supabase_request('PATCH', f'invitations?id=eq.{invitation_id}',
                     json={'status': new_status, 'responded_at': 'now()'})

    if action == 'accept':
        # При принятии приглашения отклик сразу accepted (работодатель уже выбрал трудника)
        supabase_admin_request('POST', 'applications', json={
            'job_id': inv['job_id'],
            'worker_id': inv['worker_id'],
            'status': 'accepted'
        })
        # Обновить счётчик занятых мест (admin_request — worker не может PATCH jobs)
        job_resp = supabase_admin_request('GET', f'jobs?id=eq.{inv["job_id"]}&select=current_workers,max_workers,status')
        if job_resp.ok and job_resp.json():
            job = job_resp.json()[0]
            new_count = job['current_workers'] + 1
            new_status = 'in_progress' if new_count >= job['max_workers'] else job['status']
            supabase_admin_request('PATCH', f'jobs?id=eq.{inv["job_id"]}', json={
                'current_workers': new_count,
                'status': new_status
            })
        # Уведомить работника о принятии
        create_notification(inv['worker_id'], 'application_accepted', 'Приглашение принято',
               f'Ваша заявка на задание #{inv["job_id"]} принята.',
               data={'job_id': inv['job_id']})
        # Уведомить работодателя
        create_notification(inv['employer_id'], 'application_received', 'Приглашение принято',
               f'Трудник принял ваше приглашение на задание',
               data={'job_id': inv['job_id']})

    return jsonify({'success': True, 'new_status': new_status})


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
    skills_resp = supabase_request('GET', 'skills?select=id,name&order=name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = supabase_request('GET', 'religions?select=id,name&order=name.asc')
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
# Публикация и оплата заданий (новая модель)
# ──────────────────────────────────────────────

@jobs_bp.route('/job/<job_id>/publish')
@login_required
@role_required('employer')
def publish_job(job_id):
    """Страница оплаты публикации задания."""
    resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=*')
    job = resp.json()[0] if resp.ok and resp.json() else None
    if not job or job['employer_id'] != session['user_id']:
        flash('Нет доступа', 'danger')
        return redirect(url_for('jobs.my_jobs'))
    if job.get('is_paid'):
        flash('Задание уже опубликовано', 'warning')
        return redirect(url_for('jobs.my_jobs'))
    from app.services.payment_service import PaymentService
    tariffs = PaymentService.get_tariffs()
    tariff = tariffs[0] if tariffs else {'tariff_key': 'standard', 'price': 490, 'duration_days': 30, 'renewal_price': 290}
    return render_template('job_publish.html', job=job, tariffs=tariffs, tariff=tariff)


@jobs_bp.route('/api/jobs/<job_id>/publish', methods=['POST'])
@login_required
@role_required('employer')
def api_publish_job(job_id):
    """API: оплатить и опубликовать задание."""
    from app.services.payment_service import PaymentService
    data = request.get_json() or {}
    tariff = data.get('tariff', 'standard')

    if not _check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    result = PaymentService.create_job_payment(
        employer_id=session['user_id'], job_id=job_id, tariff=tariff
    )
    if not result:
        return jsonify({'success': False, 'error': 'Не удалось создать платёж'}), 500

    # Обработать платёж
    payment_result = PaymentService.process_job_payment(
        payment_id=result['payment_id'], employer_id=session['user_id']
    )
    if payment_result.get('success'):
        return jsonify({
            'success': True,
            'message': 'Задание опубликовано',
            'redirect': url_for('jobs.my_jobs'),
        })
    return jsonify({'success': False, 'error': 'Ошибка оплаты'}), 500


@jobs_bp.route('/api/jobs/<job_id>/renew', methods=['POST'])
@login_required
@role_required('employer')
def api_renew_job(job_id):
    """API: продлить публикацию задания."""
    from app.services.payment_service import PaymentService
    tariffs = PaymentService.get_tariffs()
    renewal_price = tariffs[0].get('renewal_price', 290) if tariffs else 290

    # Создать платёж типа renewal
    resp = supabase_request('POST', 'job_payments', json={
        'job_id': job_id,
        'employer_id': session['user_id'],
        'amount': renewal_price,
        'tariff': 'standard',
        'type': 'renewal',
        'status': 'pending',
    })
    # Эмуляция оплаты
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    payment = resp.json()[0] if resp.ok and resp.json() else None
    if payment:
        supabase_request('PATCH', f'job_payments?id=eq.{payment["id"]}', json={
            'status': 'paid',
            'paid_at': now,
        })
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
        'status': 'open',
        'expires_at': expires_at,
    })
    return jsonify({'success': True, 'message': 'Публикация продлена на 30 дней'})
