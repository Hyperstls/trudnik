from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required
from app.utils import add_notification, supabase_request

applications_bp = Blueprint('applications', __name__)


@applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
@login_required
def apply_job(job_id):
    user_id = session['user_id']
    check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if check.ok and check.json():
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('jobs.index'))

    # Проверить статус задания
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,current_workers,max_workers,employer_id')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('jobs.index'))

    job = job_resp.json()[0]

    # Проверить, что задание не собственное
    if job['employer_id'] == user_id:
        flash('Вы не можете откликаться на собственное задание', 'danger')
        return redirect(url_for('jobs.index'))

    # Проверить статус задания
    if job['status'] != 'open':
        flash('На это задание нельзя откликаться (не open)', 'danger')
        return redirect(url_for('jobs.index'))

    # Проверить количество мест
    current_workers = job.get('current_workers', 0)
    max_workers = job.get('max_workers', 1)

    if current_workers >= max_workers:
        flash(f'Места в задании заполнены (максимум {max_workers})', 'info')
        return redirect(url_for('jobs.index'))

    supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})
    flash('Отклик отправлен', 'success')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/apply-selected', methods=['POST'])
@login_required
def apply_selected():
    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.index'))

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
    return redirect(url_for('jobs.index'))


@applications_bp.route('/unapply/<job_id>', methods=['POST'])
@login_required
def unapply_job(job_id):
    user_id = session['user_id']
    resp = supabase_request('DELETE', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if resp is not None and resp.ok:
        flash('Отклик отозван', 'success')
    else:
        flash('Не удалось отозвать отклик (возможно, он уже удалён)', 'danger')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/unapply-selected', methods=['POST'])
@login_required
def unapply_selected():
    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.index'))
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
    return redirect(url_for('jobs.index'))


@applications_bp.route('/my-applications')
@login_required
def my_applications():
    """Отображение откликов на задания работодателя"""
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('jobs.index'))

    user_id = session['user_id']
    resp = supabase_request('GET',
        f'applications?job.employer_id=eq.{user_id}&select=*,worker:profiles!inner(id,full_name,photo_url,rating,skills,desired_payment,inn,phone,email_public),job:jobs(organization_name,date_time,payment_amount,status,current_workers,max_workers)')
    applications = resp.json() if resp.ok else []

    worker_ids = [app.get('worker', {}).get('id') for app in applications if app.get('worker', {}).get('id')]
    jobs = {}
    if worker_ids:
        job_ids = list(set([app.get('job_id') for app in applications]))
        if job_ids:
            job_resp = supabase_request('GET', f'jobs?id=in.({",".join(job_ids)})&select=id,organization_name,date_time,payment_amount,status,application_count,current_workers,max_workers')
            if job_resp.ok and job_resp.json():
                jobs = {job['id']: job for job in job_resp.json()}

    # Получить настройки монетизации
    from app.services.payment_service import PaymentService
    monetization_settings = PaymentService.get_settings()
    contact_price = int(monetization_settings.get('contact_price', 290))

    # Добавить контактные данные для оплаченных откликов (если контакт оплачен)
    for app_data in applications:
        if app_data.get('contact_paid') and app_data.get('worker'):
            # Контакты уже раскрыты — передаём их в шаблон
            app_data['worker_contacts'] = app_data['worker']
        else:
            app_data['worker_contacts'] = None
            # Маскируем контакты в данных worker для оплаченных
            if app_data.get('worker'):
                app_data['worker']['phone'] = '***'
                app_data['worker']['email_public'] = '***'
                app_data['worker']['inn'] = '***'

    return render_template('my_applications.html', applications=applications, jobs=jobs,
                           contact_price=contact_price)


@applications_bp.route('/applications/<app_id>/<action>', methods=['POST'])
@login_required
def handle_application(app_id, action):
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('jobs.index'))

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']

    if action == 'accept':
        # Проверить количество мест
        job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers')
        if not job_resp.ok or not job_resp.json():
            flash('Ошибка: задание не найдено', 'danger')
            return redirect(url_for('applications.my_applications'))

        job = job_resp.json()[0]
        current_workers = job.get('current_workers', 0)
        max_workers = job.get('max_workers', 1)

        if current_workers >= max_workers:
            flash(f'Ошибка: все места в задании уже заняты (максимум {max_workers})', 'danger')
            return redirect(url_for('applications.my_applications'))

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
    return redirect(url_for('applications.my_applications'))


@applications_bp.route('/application/<app_id>/cancel', methods=['POST'])
@login_required
def cancel_application(app_id):
    """Отмена принятого работника"""
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,shift_id')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('applications.my_applications'))

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']
    shift_id = app_data.get('shift_id')

    # Получить информацию о задании
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,start_time')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('applications.my_applications'))

    job = job_resp.json()[0]

    # Проверить статус задания (можно отменить только до начала)
    if job['status'] in ['active', 'payment_pending', 'paid', 'completed']:
        flash('Нельзя отменить работника после начала смены', 'danger')
        return redirect(url_for('applications.my_applications'))

    # Проверить время (если статус in_progress - проверить 12 часов)
    if job['status'] == 'in_progress' and shift_id:
        shift_resp = supabase_request('GET', f'shifts?id=eq.{shift_id}&select=start_time')
        if shift_resp.ok and shift_resp.json():
            start_time = datetime.fromisoformat(shift_resp.json()[0]['start_time'].replace('Z', '+00:00'))
            now = datetime.now(start_time.tzinfo)
            hours_before = (start_time - now).total_seconds() / 3600
            if hours_before < 12:
                flash(f'Нельзя отменить работника менее чем за 12 часов до начала (осталось {hours_before:.1f} ч)', 'danger')
                return redirect(url_for('applications.my_applications'))

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
    add_notification(worker_id, 'application_rejected', 'Отклик отменен',
                     f'Ваш отклик на задание {job.get("organization_name", "#" + job_id)} был отменен')

    flash('Работник отменен', 'success')
    return redirect(url_for('applications.my_applications'))
