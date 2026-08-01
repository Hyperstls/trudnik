import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, current_app, g, jsonify, flash, redirect, render_template, request, session, url_for, abort

logger = logging.getLogger(__name__)

from app.config import Config
from app.decorators import login_required, rate_limit, role_required, validate_uuid
from app.utils import (
    calculate_distance, check_withdraw_window, copy_job, is_circuit_open,
    sanitize_postgrest, postgrest_admin_request, postgrest_request, postgrest_rpc,
)
from app.utils.helpers import assert_postgrest_ok
from app.utils.security import safe_redirect
from app.utils.errors import safe_error_message
from app.utils.validators import parse_float
from app.services.notification_service import create as notify, enqueue_notification
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


def validate_deadline_not_past(deadline_str: str) -> str | None:
    """Проверить, что дата выполнения не в прошлом.
    
    Returns:
        Сообщение об ошибке или None если дата валидна.
    """
    if not deadline_str:
        return None  # Без даты — ок, поставится дефолт
    
    try:
        # Пробуем разные форматы: ISO с временем и без
        deadline_str = deadline_str.strip()
        if 'T' in deadline_str:
            deadline_dt = datetime.fromisoformat(deadline_str)
        else:
            # Формат YYYY-MM-DD
            deadline_dt = datetime.strptime(deadline_str, '%Y-%m-%d')
        
        # Приводим к date для сравнения (дата выполнения может быть сегодня)
        deadline_date = deadline_dt.date()
        
        # Если deadline не содержит времени, считаем что конец дня
        now = datetime.now(timezone.utc)
        today = now.date()
        
        if deadline_date < today:
            return 'Дата выполнения не может быть в прошлом'
    except (ValueError, TypeError):
        return 'Некорректный формат даты'
    
    return None


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
        user_id = session['user_id']
        cache_key = f'app_count:{user_id}'
        from app.utils.redis_cache import redis_cache_get, redis_cache_set
        count = redis_cache_get(cache_key)
        if count is not None:
            return {'pending_app_count': count}
        # Используем count=exact с limit=0 для точного подсчёта без загрузки данных
        resp = postgrest_request('GET',
            f'applications?job.employer_id=eq.{user_id}&status=eq.pending&select=id&limit=0',
            headers={'Prefer': 'count=exact'})
        if resp.ok:
            content_range = resp.headers.get('Content-Range', '')
            if '/' in content_range:
                count = int(content_range.split('/')[-1])
            else:
                count = 0
        else:
            count = 0
        redis_cache_set(cache_key, count, ttl=30)
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
    payment_min = parse_float(request.args.get('payment_min', ''), 'payment_min', min_val=0)
    payment_max = parse_float(request.args.get('payment_max', ''), 'payment_max', min_val=0)
    # Гео-поиск — opt-in: только явные параметры. По умолчанию — ВСЕ открытые задания,
    # без какой-либо автоматической фильтрации по расстоянию.
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)  # км; None = без ограничения (любое расстояние)
    sort = request.args.get('sort', 'newest')
    skills_filter = request.args.get('skills', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    # Все открытые/завершённые задания без исключения по сроку (истёкшие переводит
    # в не-open cron expire_old_jobs). detailed_description опущен — тяжёлое поле.
    query = 'status=in.(open,completed)&select=id,employer_id,organization_name,org_description,object_description,work_type,date_time,payment_amount,address,city,lat,lng,status,created_at,preferred_religion,max_workers,current_workers,expires_at'

    # C38: Если монетизация включена — показываем только оплаченные задания
    if current_app.config.get('MONETIZATION_ENABLED', False):
        query += '&is_paid=eq.true'

    # ── Гео-поиск (opt-in) через RPC nearby_jobs ──
    # Включается ТОЛЬКО когда пользователь явно указал локацию и радиус.
    # Если в радиусе ничего нет или RPC недоступен — показываем ВСЕ задания (без бланка страницы),
    # т.к. труднику всегда должны быть доступны все открытые задания.
    geo_job_distances = {}  # {job_id: distance_km}
    use_rpc_geo = False

    if lat is not None and lng is not None and radius is not None:
        try:
            rpc_resp = postgrest_rpc('nearby_jobs', {
                'p_lat': lat,
                'p_lng': lng,
                'p_radius_meters': radius * 1000,
            }, use_admin=True)
            if rpc_resp.ok and rpc_resp.json() is not None:
                rpc_jobs = rpc_resp.json()
                if isinstance(rpc_jobs, list) and rpc_jobs:
                    for job in rpc_jobs:
                        if not isinstance(job, dict):
                            continue
                        job_id = job.get('id')
                        if job_id:
                            if job.get('lat') is not None and job.get('lng') is not None:
                                geo_job_distances[job_id] = calculate_distance(lat, lng, job['lat'], job['lng'])
                            else:
                                geo_job_distances[job_id] = float('inf')
                    use_rpc_geo = True
            else:
                current_app.logger.warning(
                    'nearby_jobs RPC unavailable (status=%s), showing all jobs',
                    rpc_resp.status_code)
        except Exception as e:
            current_app.logger.warning('nearby_jobs RPC failed, showing all jobs: %s', str(e))

    # Если RPC сработал — ограничиваем выборку только заданиями в радиусе
    if use_rpc_geo and geo_job_distances:
        job_ids_str = ','.join(str(jid) for jid in geo_job_distances.keys())
        query += f'&id=in.({job_ids_str})'

    # Остальные фильтры
    if city: query += f'&city=ilike.*{sanitize_postgrest(city)}*'
    if payment_min: query += f'&payment_amount=gte.{sanitize_postgrest(payment_min)}'
    if payment_max: query += f'&payment_amount=lte.{sanitize_postgrest(payment_max)}'
    # Фильтр по вероисповеданию (preferred_religion) убран: дискриминация при найме (ТК РФ ст.3).

    # Фильтрация blacklist ДО пагинации: исключаем задания от работодателей, заблокировавших текущего трудника
    blocked_employer_ids = set()
    if session.get('role') == 'worker' and 'user_id' in session:
        bl_resp = postgrest_request('GET',
            f'blacklists?blocked_user_id=eq.{session["user_id"]}&select=user_id')
        if bl_resp.ok and bl_resp.json():
            blocked_employer_ids = {b['user_id'] for b in bl_resp.json()}
            if blocked_employer_ids:
                blocked_ids_str = ','.join(blocked_employer_ids)
                query += f'&employer_id=not.in.({blocked_ids_str})'

    # Фильтрация по навыкам на стороне БД (ilike по work_type и object_description)
    if skills_filter:
        selected_skills = [s.strip().lower() for s in skills_filter.split(',') if s.strip()]
        if selected_skills:
            or_parts = []
            for sk in selected_skills:
                sk_safe = sanitize_postgrest(sk)
                or_parts.append(f'work_type.ilike.*{sk_safe}*,object_description.ilike.*{sk_safe}*')
            query += f'&or=({",".join(or_parts)})'

    # Определяем порядок сортировки на стороне БД
    # Boost продвигаемых заданий отключён (monetization off; колонка promoted_until
    # может отсутствовать в проде — убираем, чтобы order не падал с 400).
    base_order = ''
    if sort in ('payment_asc', 'price_asc'):
        order_clause = f'{base_order}payment_amount.asc'
    elif sort in ('payment_desc', 'price_desc'):
        order_clause = f'{base_order}payment_amount.desc'
    else:
        # newest, rating, distance — все используют created_at.desc, точная сортировка в Python
        order_clause = f'{base_order}created_at.desc'

    # Пагинация: limit + offset. Запрашиваем +1 чтобы определить has_next
    resp = postgrest_request('GET', f'jobs?{query}&order={order_clause}&limit={per_page + 1}&offset={offset}')
    jobs = resp.json() if resp.ok else []

    # Гео: фильтрация — только через RPC (use_rpc_geo). В fallback лишь считаем расстояние
    # для сортировки, но НЕ отсекаем задания по радиусу — трудник видит все открытые задания.
    if not use_rpc_geo and lat is not None and lng is not None:
        for job in jobs:
            job['distance'] = calculate_distance(lat, lng, job['lat'], job['lng'])
    elif use_rpc_geo and geo_job_distances:
        # Проставляем расстояния из словаря, полученного от RPC
        for job in jobs:
            job['distance'] = geo_job_distances.get(job['id'], float('inf'))

    # Сортировка
    if sort == 'distance' and lat is not None:
        jobs.sort(key=lambda x: x.get('distance', float('inf')))
    elif sort == 'rating':
        # Получаем рейтинги работодателей для сортировки
        if jobs:
            employer_ids = list({j['employer_id'] for j in jobs if j.get('employer_id')})
            if employer_ids:
                ids_filter = ','.join(employer_ids)
                rating_resp = postgrest_request('GET',
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
        app_resp = postgrest_request('GET',
            f'applications?worker_id=eq.{session["user_id"]}&select=job_id')
        if app_resp.ok and app_resp.json():
            applied_job_ids = [a['job_id'] for a in app_resp.json()]

    # Определяем, есть ли следующая страница (запросили per_page+1)
    has_next = len(jobs) > per_page
    jobs = jobs[:per_page]

    selected_skills_list = [s.strip() for s in skills_filter.split(',') if s.strip()] if skills_filter else []
    return render_template('index.html', jobs=jobs, applied_job_ids=applied_job_ids,
                           lat=lat, lng=lng, radius=radius, sort=sort,
                           selected_skills=selected_skills_list,
                           page=page, has_next=has_next)


@jobs_bp.route('/workers')
def workers():
    try:
        filters = {
            'city': request.args.get('city', ''),
            'experience': request.args.get('experience', ''),
            'payment_from': request.args.get('payment_from', ''),
            'payment_to': request.args.get('payment_to', ''),
            'rating_min': request.args.get('rating_min', ''),
            'skills': request.args.get('skills', ''),
        }
        sort = request.args.get('sort', 'rating')
        lat = request.args.get('lat', type=float) or session.get('lat')
        lng = request.args.get('lng', type=float) or session.get('lng')

        query = 'role=eq.worker'
        if filters['city']: query += f'&city=ilike.*{sanitize_postgrest(filters["city"])}*'
        if filters['experience']: query += f'&experience=ilike.*{sanitize_postgrest(filters["experience"])}*'
        if filters['payment_from']: query += f'&desired_payment=gte.{sanitize_postgrest(filters["payment_from"])}'
        if filters['payment_to']: query += f'&desired_payment=lte.{sanitize_postgrest(filters["payment_to"])}'
        if filters['rating_min']: query += f'&rating=gte.{sanitize_postgrest(filters["rating_min"])}'
        if filters['skills']:
            # Новый подход: фильтрация через таблицу user_skills (вместо profiles.skills text[])
            skill_names = [s.strip() for s in filters['skills'].split(',') if s.strip()]
            if skill_names:
                # Шаг 1: найти skill_id по именам
                skill_filters = []
                for sn in skill_names:
                    skill_filters.append(f'name.ilike.*{sanitize_postgrest(sn)}*')
                skill_query = ','.join(skill_filters)  # PostgREST or() использует запятые
                skill_resp = postgrest_request('GET', f'skills?or=({skill_query})&select=id')
                matched_skill_ids = []
                if skill_resp.ok and skill_resp.json():
                    matched_skill_ids = [s['id'] for s in skill_resp.json() if s.get('id')]
                # Шаг 2: найти user_id по skill_id через user_skills
                if matched_skill_ids:
                    ids_filter = ','.join(matched_skill_ids)
                    us_resp = postgrest_request('GET',
                        f'user_skills?skill_id=in.({ids_filter})&select=user_id')
                    if us_resp.ok and us_resp.json():
                        worker_ids = list(set(us['user_id'] for us in us_resp.json() if us.get('user_id')))
                        if worker_ids:
                            wids_filter = ','.join(worker_ids)
                            query += f'&id=in.({wids_filter})'
                        else:
                            query += '&id=eq.00000000-0000-0000-0000-000000000000'  # нет совпадений — пустой результат

        # Определяем order в зависимости от sort
        order = 'rating.desc'
        if sort == 'name':
            order = 'full_name.asc'
        elif sort in ('price_asc',):
            order = 'desired_payment.asc.nullslast'
        elif sort in ('price_desc',):
            order = 'desired_payment.desc.nullslast'

        resp = postgrest_request('GET', f'profiles?{query}&select=id,role,created_at,rating,full_name,photo_url,age,bio,city,experience,desired_payment,verification_status,total_reviews,portfolio_link&order={order}')
        if not resp.ok:
            current_app.logger.error(
                '[WORKERS] Failed to fetch profiles: status=%s text=%s',
                resp.status_code, (resp.text or '')[:300]
            )
            if is_circuit_open(resp):
                flash('Сервис временно недоступен. Результаты поиска могут быть неполными.', 'warning')
            else:
                flash('Не удалось загрузить список трудников. Пожалуйста, попробуйте позже.', 'warning')
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
                inv_resp = postgrest_request('GET',
                    f'invitations?employer_id=eq.{session["user_id"]}&worker_id=in.({ids_filter})&status=in.(pending,accepted)&select=worker_id')
                if inv_resp.ok and inv_resp.json():
                    invited_worker_ids = {inv['worker_id'] for inv in inv_resp.json()}

        selected_skills_list = [s.strip() for s in filters['skills'].split(',') if s.strip()] if filters['skills'] else []
        return render_template('workers.html', workers=workers_list, selected_skills=selected_skills_list,
                               invited_worker_ids=invited_worker_ids, sort=sort, lat=lat, lng=lng)
    except Exception as e:
        current_app.logger.exception('[WORKERS] Unexpected error rendering /workers: %s', e)
        flash('Произошла ошибка при загрузке страницы. Попробуйте позже.', 'danger')
        return render_template('workers.html', workers=[], selected_skills=[],
                               invited_worker_ids=set(), sort='rating', lat=None, lng=None)


@jobs_bp.route('/jobs/<job_id>')
@validate_uuid('job_id')
def job_detail(job_id):
    """Детальная страница задания."""
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
        emp_resp = postgrest_request('GET',
            f'profiles?id=eq.{job["employer_id"]}&select=id,full_name,verification_status')
        if emp_resp.ok and emp_resp.json():
            employer = emp_resp.json()[0]

    # Резолвим UUID полей work_type и preferred_religion в читаемые названия
    enrich_job_with_references(job)

    if is_owner:
        app_resp = postgrest_request('GET', f'applications?job_id=eq.{job_id}&select=id')
        job['application_count'] = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0
    else:
        job['application_count'] = 0

    already_applied = False
    my_app_status = None
    my_app_id = None
    can_withdraw = True
    if 'user_id' in session:
        app_resp = postgrest_request('GET',
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
        fav_check = postgrest_request('GET',
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
# Тарифы (монетизация)
# ──────────────────────────────────────────────

@jobs_bp.route('/pricing')
def pricing():
    """Страница с тарифами для работодателей."""
    return render_template('pricing.html')


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
    skills_resp = postgrest_request('GET', 'skills?select=id,name&order=sort_order.asc,name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = postgrest_request('GET', 'religions?select=id,name&order=sort_order.asc,name.asc')
    religions_list = religions_resp.json() if religions_resp.ok else []

    template_data = {
        'yandex_api_key': current_app.config['YANDEX_MAPS_API_KEY'],
        'skills_list': skills_list,
        'religions_list': religions_list,
    }

    if request.method == 'POST':
        # C38: Проверка квоты для монетизации
        if current_app.config.get('MONETIZATION_ENABLED', False):
            user_id = session.get('user_id')
            if user_id:
                sub_resp = postgrest_request(
                    'GET',
                    f'employer_subscriptions?employer_id=eq.{user_id}&select=tariff,jobs_remaining&limit=1'
                )
                if sub_resp.ok:
                    sub_data = sub_resp.json()
                    if isinstance(sub_data, list) and len(sub_data) > 0:
                        remaining = sub_data[0].get('jobs_remaining', 0)
                        if remaining <= 0:
                            flash(
                                'Лимит заданий исчерпан. Перейдите на тариф Pro или Бизнес, чтобы '
                                'разместить больше заданий. <a href="/pricing">Смотреть тарифы</a>',
                                'danger'
                            )
                            return render_template('job_new.html', **template_data)

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

            # Валидация: дата выполнения не должна быть в прошлом
            deadline = request.form.get('deadline', '')
            deadline_error = validate_deadline_not_past(deadline)
            if deadline_error:
                flash(deadline_error, 'danger')
                return render_template('job_new.html', **template_data)

            # C35: Валидация диапазонов
            payment_amount = float(request.form.get('payment') or 0)
            max_workers = int(request.form.get('max_workers') or 1)
            lat = float(request.form.get('latitude') or Config.DEFAULT_LAT)
            lng = float(request.form.get('longitude') or Config.DEFAULT_LNG)

            validation_errors = []
            if not (0 <= payment_amount <= 1_000_000):
                validation_errors.append('Оплата должна быть от 0 до 1 000 000 ₽')
            if not (1 <= max_workers <= 100):
                validation_errors.append('Количество работников должно быть от 1 до 100')
            if not (-90 <= lat <= 90):
                validation_errors.append('Некорректная широта (должна быть от -90 до 90)')
            if not (-180 <= lng <= 180):
                validation_errors.append('Некорректная долгота (должна быть от -180 до 180)')

            if validation_errors:
                for err in validation_errors:
                    flash(err, 'danger')
                return render_template('job_new.html', **template_data)

            job_data = {
                'employer_id': session['user_id'],
                'organization_name': title,
                'org_description': '',
                'object_description': '',
                'work_type': request.form.get('work_type', ''),
                'detailed_description': description,
                'date_time': request.form.get('deadline') or datetime.now(timezone.utc).isoformat(),
                'payment_amount': payment_amount,
                'address': request.form.get('address', ''),
                'city': request.form.get('city', ''),
                'lat': lat,
                'lng': lng,
                # preferred_religion убран: дискриминация при найме (ТК РФ ст.3).
                'max_workers': max_workers,
                'current_workers': 0,
                'status': 'open',
                'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }

            resp = postgrest_request('POST', 'jobs', json=job_data)

            if not resp.ok:
                current_app.logger.error('Failed to create job: status=%s body=%s', resp.status_code, resp.text[:500])

            if resp.ok:
                created_job = resp.json()
                if isinstance(created_job, list):
                    created_job = created_job[0]
                flash('Задание успешно создано', 'success')
                return redirect(url_for('jobs.my_jobs'))
            else:
                flash(safe_error_message(resp, 'Ошибка при создании задания'), 'danger')
        except Exception as e:
            flash('Ошибка сервера', 'danger')

    return render_template('job_new.html', **template_data)


# ──────────────────────────────────────────────
# Мои задания (работодатель)
# ──────────────────────────────────────────────

@jobs_bp.route('/my-jobs')
@login_required
@role_required('employer')
def my_jobs():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')

    # Единый запрос с or-фильтром вместо двух раздельных запросов
    base_query = f'jobs?employer_id=eq.{user_id}&select=*,applications:applications(count),current_workers,max_workers'
    if status_filter == 'open':
        base_query += '&status=eq.open'
    elif status_filter not in ('all', 'open'):
        base_query += f'&status=eq.{status_filter}'

    resp = postgrest_request('GET', base_query, headers={'Prefer': 'count=exact'})
    jobs = resp.json() if resp.ok else []

    # Используем встроенный счётчик applications(count) из PostgREST embedded resource — Supabase не используется (устарело)
    # (включён в base_query как applications:applications(count))
    # Убираем дублирующий batch-запрос на отдельное получение количества откликов
    for job in jobs:
        apps_data = job.get('applications', [])
        if isinstance(apps_data, list) and len(apps_data) > 0:
            job['application_count'] = apps_data[0].get('count', 0) if isinstance(apps_data[0], dict) else 0
        else:
            job['application_count'] = 0

    return render_template('my_jobs.html', jobs=jobs, current_status=status_filter)


@jobs_bp.route('/my-jobs/action', methods=['POST'])
@login_required
@role_required('employer')
def my_jobs_action():
    """Bulk-операции над заданиями (cancel/restore/delete/duplicate).
    
    A1: Все state-changing операции используют атомарные RPC для предотвращения
    частичных обновлений и race conditions.
    """
    user_id = session['user_id']
    action = request.form.get('action')
    job_ids = request.form.getlist('job_ids')

    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    success_count = 0
    error_count = 0
    
    for job_id in job_ids:
        if not check_job_owner(job_id, user_id):
            error_count += 1
            continue
            
        if action == 'restore':
            # A1: Используем атомарный RPC вместо прямого PATCH
            rpc_result = postgrest_rpc('restore_job_atomic', {
                'p_job_id': job_id,
                'p_user_id': user_id
            })
            if rpc_result.ok:
                result_data = rpc_result.json()
                if result_data.get('success'):
                    success_count += 1
                else:
                    error_msg = result_data.get('error', 'неизвестная ошибка')
                    logger.warning('restore_job_atomic failed for job %s: %s', job_id, error_msg)
                    flash('Ошибка восстановления: %s' % error_msg, 'warning')
                    error_count += 1
            else:
                logger.warning('restore_job_atomic HTTP error for job %s: status=%s', job_id, rpc_result.status_code)
                flash('Ошибка восстановления задания', 'warning')
                error_count += 1
                
        elif action == 'cancel':
            # A1: Используем атомарный RPC вместо прямого PATCH
            # RPC проверяет наличие accepted workers и возвращает 409 если есть
            rpc_result = postgrest_rpc('cancel_job_atomic', {
                'p_job_id': job_id,
                'p_user_id': user_id
            })
            if rpc_result.ok:
                result_data = rpc_result.json()
                if result_data.get('success'):
                    success_count += 1
                else:
                    error_code = result_data.get('code', '')
                    error_msg = result_data.get('error', 'неизвестная ошибка')
                    if error_code == 'has_accepted_workers':
                        # 409 Conflict: нельзя отменить задание с принятыми работниками
                        logger.warning('cancel_job_atomic conflict for job %s: %s', job_id, error_msg)
                        flash('Невозможно отменить: есть принятые работники', 'danger')
                    else:
                        logger.warning('cancel_job_atomic failed for job %s: %s', job_id, error_msg)
                        flash('Ошибка отмены: %s' % error_msg, 'warning')
                    error_count += 1
            else:
                logger.warning('cancel_job_atomic HTTP error for job %s: status=%s', job_id, rpc_result.status_code)
                flash('Ошибка отмены задания', 'warning')
                error_count += 1
                
        elif action == 'delete':
            # delete_job_cascade уже использует RPC - оставляем как есть
            rpc_result = postgrest_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
            if rpc_result.ok:
                result_data = rpc_result.json()
                if result_data.get('success'):
                    success_count += 1
                else:
                    error_msg = result_data.get('error', 'неизвестная ошибка')
                    logger.warning('delete_job_cascade failed for job %s: %s', job_id, error_msg)
                    flash('Ошибка удаления: %s' % error_msg, 'warning')
                    error_count += 1
            else:
                logger.warning('delete_job_cascade HTTP error for job %s: status=%s', job_id, rpc_result.status_code)
                flash('Ошибка удаления задания', 'warning')
                error_count += 1
                
        elif action == 'duplicate':
            # Дублирование не требует атомарного RPC - это просто копирование
            resp = postgrest_request('GET', f'jobs?id=eq.{job_id}&select=*')
            if resp.ok and resp.json():
                new_job = copy_job(resp.json()[0])
                dup_resp = postgrest_request('POST', 'jobs', json=new_job)
                if dup_resp.ok:
                    success_count += 1
                else:
                    logger.warning('duplicate job failed for job %s: status=%s', job_id, dup_resp.status_code)
                    flash('Ошибка дублирования задания', 'warning')
                    error_count += 1
            else:
                error_count += 1

    # Итоговое сообщение
    if success_count > 0 and error_count == 0:
        flash('Операция выполнена для %d заданий' % success_count, 'success')
    elif success_count > 0 and error_count > 0:
        flash('Выполнено: %d, ошибок: %d' % (success_count, error_count), 'warning')
    elif error_count > 0:
        flash('Операция не выполнена: %d ошибок' % error_count, 'danger')
        
    return redirect(url_for('jobs.my_jobs'))


# ──────────────────────────────────────────────
# Отдельные действия над заданиями
# ──────────────────────────────────────────────

@jobs_bp.route('/repost-job/<job_id>', methods=['POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id')
def repost_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403
    resp = postgrest_request('GET', f'jobs?id=eq.{job_id}&select=*')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if resp.ok and resp.json():
        new_job = copy_job(resp.json()[0])
        repost_resp = postgrest_request('POST', 'jobs', json=new_job)
        if assert_postgrest_ok(repost_resp, 'пересоздание задания'):
            if is_ajax:
                return jsonify({'success': True, 'message': 'Задание дублировано'})
            flash('Задание дублировано', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Задание не найдено'}), 404
        flash('Задание не найдено', 'danger')

    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/cancel-job/<job_id>', methods=['POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id')
def cancel_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Атомарная RPC: проверка статуса + проверка accepted-откликов + отмена задания + reject pending
    # Заменяет 5 неатомарных HTTP-запросов (GET статуса → GET accepted → PATCH job → PATCH apps → GET rejected)
    rpc_result = postgrest_rpc('cancel_job_atomic', {
        'p_job_id': job_id,
        'p_user_id': session['user_id'],
    }, use_admin=True)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Сервис не настроен'}), 503
            flash('Не удалось отозвать задание (сервис недоступен)', 'danger')
            return redirect(url_for('jobs.my_jobs'))
        if is_ajax:
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500
        flash('Не удалось отозвать задание', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    result = rpc_result.json()
    if not result or not result.get('success'):
        error_msg = (result or {}).get('error', 'Не удалось отозвать задание')
        error_code = (result or {}).get('code', '')
        # C7: Обработка race condition — 409 для has_accepted_workers
        status_code = 409 if error_code == 'has_accepted_workers' else 400
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), status_code
        flash(error_msg, 'danger')
        return redirect(url_for('jobs.my_jobs'))

    # Уведомить заявителей, что задание отозвано (worker_id получены из RPC, transactional outbox)
    rejected_worker_ids = result.get('rejected_worker_ids', [])
    if rejected_worker_ids:
        for worker_id in rejected_worker_ids:
            if worker_id:  # защита от NULL в массиве
                enqueue_notification(worker_id, 'job_cancelled', 'Задание отозвано',
                       f'Задание #{job_id} было отозвано работодателем',
                       data={'job_id': job_id, 'link': url_for('jobs.index', _external=True)})

    if is_ajax:
        return jsonify({'success': True, 'message': 'Задание отозвано'})
    flash('Задание отозвано', 'success')
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/restore-job/<job_id>', methods=['POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id')
def restore_job(job_id):
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # C37: Атомарное восстановление через RPC restore_job_atomic
    # Заменяет 4 отдельных PATCH-запроса одной транзакцией PostgreSQL
    rpc_result = postgrest_rpc('restore_job_atomic', {
        'p_job_id': job_id,
    }, use_admin=True)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Сервис не настроен'}), 503
            flash('Не удалось восстановить задание (сервис недоступен)', 'danger')
            return redirect(url_for('jobs.my_jobs'))
        if is_ajax:
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500
        flash('Не удалось восстановить задание', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    result = rpc_result.json()
    if not result or not result.get('success'):
        error_msg = (result or {}).get('error', 'Не удалось восстановить задание')
        status_code = 409 if (result or {}).get('code') == 'not_cancelled' else 400
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), status_code
        flash(error_msg, 'danger')
        return redirect(url_for('jobs.my_jobs'))

    new_status = result.get('new_status', 'open')

    # Уведомить всех восстановленных заявителей, что задание восстановлено (transactional outbox)
    restored_worker_ids = result.get('restored_worker_ids', [])
    if restored_worker_ids:
        for worker_id in restored_worker_ids:
            if worker_id:
                enqueue_notification(worker_id, 'status_change', 'Задание восстановлено',
                       f'Задание #{job_id} снова открыто для откликов',
                       data={'job_id': job_id, 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

    if is_ajax:
        return jsonify({'success': True, 'message': 'Задание восстановлено', 'new_status': new_status})
    flash('Задание восстановлено', 'success')
    return redirect(url_for('jobs.my_jobs'))


@jobs_bp.route('/api/jobs/<job_id>/force-complete', methods=['POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id')
def api_force_complete_job(job_id):
    """Принудительное завершение задания работодателем.
    Использует атомарную RPC force_complete_job:
    проверка владельца + проверка статуса open + массовый reject pending + установка completed
    в одной транзакции PostgreSQL."""
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Атомарная RPC: reject всех pending + установка completed (заменяет 4 неатомарных запроса)
    rpc_result = postgrest_rpc('force_complete_job', {
        'p_job_id': job_id,
        'p_user_id': session['user_id'],
    }, use_admin=True)

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            return jsonify({'success': False, 'error': 'Сервис не настроен'}), 503
        return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

    result = rpc_result.json()
    if not result or not result.get('success'):
        error_msg = (result or {}).get('error', 'Не удалось завершить задание')
        status_code = 409 if (result or {}).get('code') == 'invalid_status' else 400
        return jsonify({'success': False, 'error': error_msg}), status_code

    # Уведомить всех accepted работников (worker_id получены из RPC, transactional outbox)
    accepted_worker_ids = result.get('accepted_worker_ids', [])
    if accepted_worker_ids:
        for worker_id in accepted_worker_ids:
            if worker_id:
                enqueue_notification(worker_id, 'force_complete', 'Задание завершено',
                       f'Работодатель завершил задание #{job_id}',
                       data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})

    return jsonify({
        'success': True,
        'message': 'Задание принудительно завершено',
        'new_status': 'completed'
    })


@jobs_bp.route('/delete-job/<job_id>', methods=['POST'])
@login_required
@validate_uuid('job_id')
def delete_job(job_id):
    # Разрешаем удаление владельцу-работодателю и админу
    is_admin = session.get('role') == 'admin'
    if not is_admin and not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Блокировка: предупреждение при наличии принятых откликов (матрица секция 6.1)
    apps_resp = postgrest_request('GET', f'applications?job_id=eq.{job_id}&status=eq.accepted&select=id')
    has_accepted = apps_resp.ok and apps_resp.json()

    if has_accepted:
        # Требуем явный параметр подтверждения через AJAX
        data = request.get_json(silent=True) or {}
        if not data.get('confirm'):
            return jsonify({'success': False, 'error': 'У задания есть принятые отклики. Подтвердите удаление.', 'needs_confirm': True}), 409

    # X4: Атомарное каскадное удаление через RPC (транзакция PostgreSQL)
    resp = postgrest_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
    if not resp.ok:
        logger.warning('delete_job_cascade failed job_id=%s: %s', job_id, resp.text)
        flash('Не удалось удалить вакансию', 'danger')
        return redirect(url_for('jobs.my_jobs'))
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
    """HTML-страница приглашений (использует унифицированный сервис)."""
    from app.services.invitation_service import list_invitations as get_invitations
    invitations = get_invitations()
    return render_template('invitations.html', invitations=invitations)


@jobs_bp.route('/api/invitations/reject-all', methods=['POST'])
@login_required
def reject_all_invitations():
    """Отклонить все ожидающие приглашения текущего пользователя."""
    user_id = session['user_id']
    postgrest_admin_request('PATCH',
        f'invitations?worker_id=eq.{user_id}&status=eq.pending',
        json={'status': 'rejected', 'responded_at': datetime.now(timezone.utc).isoformat()})
    return jsonify({'success': True})


@jobs_bp.route('/jobs/<job_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id')
@rate_limit
def edit_job(job_id):
    # Используем admin_request для обхода RLS — работодатель должен видеть
    # своё задание в любом статусе (включая неоплаченные)
    job_resp = postgrest_admin_request('GET', f'jobs?id=eq.{job_id}&select=*')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.my_jobs'))
    job = job_resp.json()[0]
    if job['employer_id'] != session['user_id']:
        flash('Нет доступа', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    # Проверить наличие accepted-откликов (P1: блокировка редактирования)
    apps_check = postgrest_request('GET',
        f'applications?job_id=eq.{job_id}&status=eq.accepted&select=id')
    has_accepted = apps_check.ok and apps_check.json()

    # Загружаем справочники
    skills_resp = postgrest_request('GET', 'skills?select=id,name&order=sort_order.asc,name.asc')
    skills_list = skills_resp.json() if skills_resp.ok else []
    religions_resp = postgrest_request('GET', 'religions?select=id,name&order=sort_order.asc,name.asc')
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

        # Валидация: дата выполнения не должна быть в прошлом
        new_deadline = request.form.get('deadline', '')
        if new_deadline:
            deadline_error = validate_deadline_not_past(new_deadline)
            if deadline_error:
                flash(deadline_error, 'danger')
                return render_template('job_new.html',
                    job=job,
                    is_edit=True,
                    skills_list=skills_list,
                    religions_list=religions_list,
                    yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'])

        # C36: Валидация диапазонов
        payment_amount = float(request.form.get('payment') or job.get('payment_amount', 0))
        max_workers = int(request.form.get('max_workers', job.get('max_workers', 1)))

        validation_errors = []
        if not (0 <= payment_amount <= 1_000_000):
            validation_errors.append('Оплата должна быть от 0 до 1 000 000 ₽')
        if not (1 <= max_workers <= 100):
            validation_errors.append('Количество работников должно быть от 1 до 100')

        if validation_errors:
            for err in validation_errors:
                flash(err, 'danger')
            return render_template('job_new.html',
                job=job,
                is_edit=True,
                skills_list=skills_list,
                religions_list=religions_list,
                yandex_api_key=current_app.config['YANDEX_MAPS_API_KEY'])

        data = {
            'organization_name': request.form.get('title', job['organization_name']),
            'detailed_description': request.form.get('description', job.get('detailed_description', '')),
            'work_type': request.form.get('work_type', job.get('work_type', '')),
            'payment_amount': payment_amount,
            'city': request.form.get('city', job.get('city', '')),
            'address': request.form.get('address', job.get('address', '')),
            'max_workers': max_workers,
            # preferred_religion убран: дискриминация при найме (ТК РФ ст.3).
            'date_time': request.form.get('deadline') or job.get('date_time', ''),
            'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        resp = postgrest_request('PATCH', f'jobs?id=eq.{job_id}', json=data)
        if resp.ok:
            flash('Задание обновлено', 'success')
            return redirect(url_for('jobs.job_detail', job_id=job_id))
        else:
            flash('Ошибка обновления', 'danger')
            return redirect(url_for('jobs.edit_job', job_id=job_id))

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
@validate_uuid('job_id')
def add_favorite_job(job_id):
    fav_resp = postgrest_request('POST', 'job_favorites', json={'user_id': session['user_id'], 'job_id': job_id})
    if assert_postgrest_ok(fav_resp, 'добавление задания в избранное'):
        flash('Задание добавлено в избранное', 'success')
    return safe_redirect('jobs.index')


@jobs_bp.route('/unfavorite-job/<job_id>', methods=['POST'])
@login_required
@validate_uuid('job_id')
def remove_favorite_job(job_id):
    unfav_resp = postgrest_request('DELETE', f'job_favorites?user_id=eq.{session["user_id"]}&job_id=eq.{job_id}')
    if assert_postgrest_ok(unfav_resp, 'удаление задания из избранного'):
        flash('Задание удалено из избранного', 'success')
    return safe_redirect('favorites.favorites')


# ──────────────────────────────────────────────
