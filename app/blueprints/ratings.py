"""Blueprint для рейтингов и отзывов."""
from flask import Blueprint, jsonify, request, session, current_app, render_template, redirect, flash, url_for

from app.decorators import login_required
from app.utils import rate_limit, supabase_request, supabase_admin_request, update_rating

ratings_bp = Blueprint('ratings', __name__)


@ratings_bp.route('/api/ratings/<job_id>', methods=['GET'])
def get_job_ratings(job_id):
    """Получить все оценки для задания."""
    resp = supabase_request(
        'GET',
        f'ratings?job_id=eq.{job_id}&select=*,rater:profiles!rater_user_id(full_name,photo_url),rated:profiles!rated_user_id(full_name,photo_url)&order=created_at.desc'
    )
    ratings = resp.json() if resp.ok else []

    # Средняя оценка
    avg_resp = supabase_request(
        'GET',
        f'ratings?job_id=eq.{job_id}&select=rating'
    )
    avg_rating = 0
    if avg_resp.ok and avg_resp.json():
        vals = [r['rating'] for r in avg_resp.json()]
        avg_rating = round(sum(vals) / len(vals), 1) if vals else 0

    return jsonify({
        'success': True,
        'ratings': ratings,
        'average': avg_rating,
        'count': len(ratings)
    })


@ratings_bp.route('/api/ratings/user/<user_id>', methods=['GET'])
def get_user_rating(user_id):
    """Получить агрегированный рейтинг пользователя."""
    resp = supabase_request(
        'GET',
        f'ratings?rated_user_id=eq.{user_id}&select=rating'
    )
    if not resp.ok or not resp.json():
        return jsonify({'success': True, 'average': 0, 'count': 0})

    vals = [r['rating'] for r in resp.json()]
    return jsonify({
        'success': True,
        'average': round(sum(vals) / len(vals), 1) if vals else 0,
        'count': len(vals),
        'ratings': resp.json()
    })


@ratings_bp.route('/api/ratings', methods=['POST'])
@login_required
@rate_limit
def upsert_rating():
    """Создать или обновить оценку (один пользователь — одна оценка на задание).
    
    Body:
        job_id (str): ID задания
        rated_user_id (str): ID оцениваемого пользователя
        rating (int): 1-5
        comment (str, optional): текст отзыва
        target_type (str): 'worker' | 'employer' — кого оценивают
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    rated_user_id = data.get('rated_user_id')
    rating = data.get('rating')
    comment = data.get('comment', '')
    target_type = data.get('target_type', 'worker')  # кто оценивается

    # Валидация
    if not all([job_id, rated_user_id, rating]):
        return jsonify({'success': False, 'error': 'job_id, rated_user_id, rating обязательны'}), 400

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'rating должен быть целым числом'}), 400

    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'error': 'rating от 1 до 5'}), 400

    if target_type not in ('worker', 'employer'):
        return jsonify({'success': False, 'error': 'target_type должен быть worker или employer'}), 400

    rater_user_id = session['user_id']

    # Нельзя оценить самого себя
    if rater_user_id == rated_user_id:
        return jsonify({'success': False, 'error': 'Нельзя оценить самого себя'}), 400

    # Получить задание (проверить, что оно завершено)
    job_resp = supabase_admin_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=id,status,employer_id'
    )
    if not job_resp.ok or not job_resp.json():
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

    job = job_resp.json()[0]
    if job['status'] != 'completed':
        return jsonify({'success': False, 'error': 'Оценить можно только завершённое задание'}), 400

    # Проверить, что оценщик — участник задания (работодатель или принятый работник)
    if rater_user_id != job['employer_id']:
        # Проверить, есть ли accepted-отклик от этого пользователя на это задание
        app_check = supabase_admin_request('GET',
            f'applications?job_id=eq.{job_id}&worker_id=eq.{rater_user_id}&status=eq.accepted&select=id')
        if not (app_check.ok and app_check.json()):
            return jsonify({'success': False, 'error': 'Вы не являетесь участником этого задания'}), 403

    # Определить rating_type (роль оценивающего)
    if rater_user_id == job['employer_id']:
        rating_type = 'employer'
    else:
        rating_type = 'worker'

    # UPSERT: вставка или обновление существующей оценки
    rating_data = {
        'job_id': job_id,
        'rater_user_id': rater_user_id,
        'rated_user_id': rated_user_id,
        'rating_type': rating_type,
        'target_type': target_type,
        'rating': rating,
        'comment': comment,
        'updated_at': 'now()',
    }

    # Пробуем найти существующую оценку
    existing = supabase_request(
        'GET',
        f'ratings?rater_user_id=eq.{rater_user_id}&job_id=eq.{job_id}&select=id'
    )

    if existing.ok and existing.json():
        # UPDATE
        rating_id = existing.json()[0]['id']
        resp = supabase_admin_request(
            'PATCH',
            f'ratings?id=eq.{rating_id}',
            json=rating_data
        )
        is_new = False
    else:
        # INSERT с обработкой конфликта (на случай гонки)
        resp = supabase_admin_request('POST', 'ratings', json=rating_data)
        is_new = True

        # Если INSERT упал с конфликтом уникальности — обновляем
        if not resp.ok and 'violates unique constraint' in (resp.text or '').lower():
            existing2 = supabase_admin_request(
                'GET',
                f'ratings?rater_user_id=eq.{rater_user_id}&job_id=eq.{job_id}&select=id'
            )
            if existing2.ok and existing2.json():
                rating_id = existing2.json()[0]['id']
                resp = supabase_admin_request(
                    'PATCH',
                    f'ratings?id=eq.{rating_id}',
                    json=rating_data
                )
                is_new = False

    if not resp.ok:
        current_app.logger.error(
            '[RATING] Failed to upsert: rater=%s job=%s status=%s text=%s',
            rater_user_id, job_id, resp.status_code, (resp.text or '')[:200]
        )
        return jsonify({'success': False, 'error': 'Ошибка при сохранении оценки'}), 500

    # Обновить средний рейтинг пользователя
    update_rating(rated_user_id, rating)

    return jsonify({
        'success': True,
        'is_new': is_new,
        'message': 'Оценка сохранена' if is_new else 'Оценка обновлена'
    })


# ============================================================
# Детальные оценки пользователя
# ============================================================

@ratings_bp.route('/api/ratings/user/<user_id>/details', methods=['GET'])
def get_user_rating_details(user_id):
    """Получить все детальные оценки пользователя с отзывами."""
    resp = supabase_request(
        'GET',
        f'ratings?rated_user_id=eq.{user_id}&select=*,rater:profiles!rater_user_id(full_name,photo_url)&order=created_at.desc&limit=100'
    )
    if not resp.ok:
        return jsonify({'success': False, 'error': 'Ошибка загрузки оценок'}), 500

    ratings = resp.json() or []

    # Вычисляем средний рейтинг
    avg_rating = 0
    if ratings:
        vals = [r['rating'] for r in ratings]
        avg_rating = round(sum(vals) / len(vals), 1)

    return jsonify({
        'success': True,
        'ratings': ratings,
        'average': avg_rating,
        'count': len(ratings)
    })


# ============================================================
# Страница оценок пользователя (HTML)
# ============================================================

@ratings_bp.route('/ratings/user/<user_id>')
def user_ratings_page(user_id):
    """Страница со списком всех оценок пользователя."""
    return render_template('user_ratings.html', profile_user_id=user_id)


@ratings_bp.route('/jobs/<job_id>/rate-workers')
@login_required
def rate_workers_page(job_id):
    """
    Страница оценки всех принятых работников задания.
    Доступна только работодателю — владельцу задания.
    """
    user_id = session['user_id']

    # --- 1. Проверка роли ---
    if session.get('role') != 'employer':
        flash('Только работодатели могут оценивать работников', 'danger')
        return redirect(url_for('jobs.index'))

    # --- 2. Получить задание и проверить владельца ---
    job_resp = supabase_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=id,title,status,employer_id'
    )
    if not job_resp.ok:
        if job_resp.status_code == 401:
            flash('Сессия истекла, пожалуйста войдите снова', 'warning')
            return redirect(url_for('auth.login'))
        flash('Ошибка при загрузке задания', 'danger')
        return redirect(url_for('jobs.my_jobs'))
    if not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    job = job_resp.json()[0]

    if job['employer_id'] != user_id:
        flash('Вы не являетесь работодателем этого задания', 'danger')
        return redirect(url_for('jobs.my_jobs'))

    # --- 3. Загрузить принятых работников с JOIN к profiles ---
    workers_resp = supabase_request(
        'GET',
        f'applications?job_id=eq.{job_id}&status=eq.accepted'
        f'&select=worker_id,profiles!worker_id(full_name,photo_url,rating)'
    )
    workers = []
    if workers_resp.ok and workers_resp.json():
        for app_item in workers_resp.json():
            profile = app_item.get('profiles') or {}
            workers.append({
                'worker_id': app_item['worker_id'],
                'full_name': profile.get('full_name', 'Пользователь'),
                'photo_url': profile.get('photo_url', ''),
                'rating': profile.get('rating', 0),
            })

    # --- 4. Загрузить существующие оценки (этого работодателя, этого задания) ---
    ratings_resp = supabase_request(
        'GET',
        f'ratings?rater_user_id=eq.{user_id}&job_id=eq.{job_id}'
        f'&select=rated_user_id,rating,comment'
    )
    existing_ratings = {}
    if ratings_resp.ok and ratings_resp.json():
        for r in ratings_resp.json():
            existing_ratings[r['rated_user_id']] = r

    # --- 5. Рендер шаблона ---
    return render_template(
        'rate_workers.html',
        job=job,
        workers=workers,
        existing_ratings=existing_ratings
    )


