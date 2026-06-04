from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import add_notification, supabase_request, update_rating

shifts_bp = Blueprint('shifts', __name__)


@shifts_bp.route('/shifts')
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


@shifts_bp.route('/shift/<shift_id>/checkin', methods=['POST'])
@login_required
def shift_checkin(shift_id):
    """Чек-ин работника"""
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=worker_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('shifts'))

    shift = shift_resp.json()[0]

    if session.get('user_id') != shift['worker_id']:
        flash('Нет прав для чек-ина', 'danger')
        return redirect(url_for('shifts'))

    supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
        'worker_checkin': True,
        'start_time': datetime.now().isoformat(),
        'status': 'active'
    })

    job_resp = supabase_request('GET', f'jobs?id=eq.{shift["job_id"]}&select=status')
    if job_resp.ok and job_resp.json():
        job = job_resp.json()[0]
        if job['status'] == 'in_progress':
            supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'active'})

    flash('Чек-ин успешно выполнен', 'success')
    return redirect(url_for('shifts'))


@shifts_bp.route('/shift/<shift_id>/complete', methods=['POST'])
@login_required
def shift_complete(shift_id):
    """Завершение смены работником"""
    shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=worker_id,employer_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('shifts'))

    shift = shift_resp.json()[0]

    if session.get('user_id') != shift['worker_id']:
        flash('Нет прав для завершения', 'danger')
        return redirect(url_for('shifts'))

    if shift['status'] != 'active':
        flash('Только активные смены можно завершить', 'danger')
        return redirect(url_for('shifts'))

    supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={
        'worker_complete': True,
        'complete_time': datetime.now().isoformat(),
        'status': 'payment_pending'
    })

    supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'payment_pending'})

    flash('Смена завершена, ожидание подтверждения оплаты', 'success')
    return redirect(url_for('shifts'))


@shifts_bp.route('/shift/<shift_id>/confirm-payment', methods=['POST'])
@login_required
def confirm_payment(shift_id):
    """Подтверждение оплаты (работодателем или работником)"""
    action = request.form.get('action', '')

    shift_resp = supabase_request('GET',
        f'shifts?id=eq.{shift_id}&select=employer_id,worker_id,job_id,employer_payment_confirmed,worker_payment_confirmed,status')
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
    shift_resp = supabase_request('GET',
        f'shifts?id=eq.{shift_id}&select=employer_payment_confirmed,worker_payment_confirmed')
    if shift_resp.ok and shift_resp.json():
        shift = shift_resp.json()[0]
        if shift.get('employer_payment_confirmed') and shift.get('worker_payment_confirmed'):
            # Обе стороны подтвердили — установить статус paid
            supabase_request('PATCH', f'shifts?id=eq.{shift_id}', json={'status': 'paid'})
            supabase_request('PATCH', f'jobs?id=eq.{shift["job_id"]}', json={'status': 'paid'})

            # Отправить уведомления
            add_notification(shift['employer_id'], 'payment_sent', 'Оплата подтверждена',
                             f'Оплата по смене #{shift_id} подтверждена обеими сторонами')
            add_notification(shift['worker_id'], 'payment_received', 'Оплата подтверждена',
                             f'Оплата по смене #{shift_id} подтверждена обеими сторонами')

    return redirect(url_for('shifts'))


@shifts_bp.route('/rate-worker/<worker_id>/<job_id>', methods=['POST'])
@login_required
def rate_worker(worker_id, job_id):
    """Оценка работника после завершения смены"""
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '')

    # Получить информацию о смене
    shift_resp = supabase_request('GET',
        f'shifts?worker_id=eq.{worker_id}&job_id=eq.{job_id}&select=id,employer_id,worker_id,job_id,status')
    if not shift_resp.ok or not shift_resp.json():
        flash('Смена не найдена', 'danger')
        return redirect(url_for('index'))

    shift = shift_resp.json()[0]

    # Проверить статус (только для paid)
    if shift['status'] != 'paid':
        flash('Оценить можно только после завершения оплаты', 'danger')
        return redirect(url_for('shifts'))

    # Проверить, что оценка оставляется только один раз
    existing = supabase_request('GET',
        f'ratings?rated_user_id=eq.{worker_id}&rater_user_id=eq.{session["user_id"]}&job_id=eq.{job_id}')
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


@shifts_bp.route('/shift/<shift_id>/dispute', methods=['POST'])
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
        add_notification(admin_id, 'dispute_started', 'Новый спор',
                         f'Пользователь запросил спор по смене #{shift_id}')

    # Добавить уведомления участникам
    add_notification(shift['employer_id'], 'dispute_started', 'Спор открыт',
                     f'Ваш спор по смене #{shift_id} открыт на рассмотрении')
    add_notification(shift['worker_id'], 'dispute_started', 'Спор открыт',
                     f'Ваш спор по смене #{shift_id} открыт на рассмотрении')

    flash('Спор открыт на рассмотрение', 'warning')
    return redirect(url_for('shifts'))
