from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required
from app.utils import rate_limit, supabase_request
from app.services.notification_service import create as notify

applications_bp = Blueprint('applications', __name__)


@applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
@login_required
@rate_limit
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

    # Проверить, не заблокирован ли работник у этого работодателя
    blacklist_resp = supabase_request(
        'GET',
        f'blacklists?user_id=eq.{job["employer_id"]}&blocked_user_id=eq.{user_id}&select=id'
    )
    if blacklist_resp.ok and blacklist_resp.json():
        if request.method == 'POST':
            return jsonify({'success': False, 'error': 'Вы не можете откликнуться: работодатель добавил вас в чёрный список'}), 403
        flash('Вы не можете откликнуться: работодатель добавил вас в чёрный список', 'danger')
        return redirect(url_for('jobs.index'))

    # Проверить статус задания (разрешён только open)
    if job['status'] != 'open':
        flash('На это задание нельзя откликаться', 'danger')
        return redirect(url_for('jobs.index'))

    # Проверить количество мест
    current_workers = job.get('current_workers', 0)
    max_workers = job.get('max_workers', 1)

    if current_workers >= max_workers:
        flash(f'Места в задании заполнены (максимум {max_workers})', 'info')
        return redirect(url_for('jobs.index'))

    supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})

    # Уведомить работодателя о новом отклике
    notify(job['employer_id'], 'application_received', 'Новый отклик',
           f'На ваше задание поступил новый отклик', data={'job_id': job_id})

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


@applications_bp.route('/api/applications/<app_id>/withdraw', methods=['POST'])
@login_required
def api_withdraw_application(app_id):
    """Отзыв отклика работником (автором).
    - pending → withdrawn в любое время (без ограничений)
    - accepted → withdrawn только если > 12 часов до начала задания
    - Уменьшает current_workers, если accepted
    - Если current_workers падает до 0 и статус completed → open
    """
    user_id = session['user_id']

    # Получить отклик
    app_resp = supabase_request('GET',
        f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        return jsonify({'success': False, 'error': 'Отклик не найден'}), 404

    app_data = app_resp.json()[0]
    if app_data['worker_id'] != user_id:
        return jsonify({'success': False, 'error': 'Вы не автор этого отклика'}), 403

    current_status = app_data.get('status', 'pending')
    if current_status == 'withdrawn':
        return jsonify({'success': False, 'error': 'Отклик уже отозван'}), 409

    job_id = app_data['job_id']

    # Получить задание
    job_resp = supabase_request('GET',
        f'jobs?id=eq.{job_id}&select=status,date_time,current_workers,max_workers,employer_id')
    if not job_resp.ok or not job_resp.json():
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

    job = job_resp.json()[0]

    # Если accepted — проверить 12-часовой лимит
    if current_status == 'accepted':
        date_time_str = job.get('date_time')
        if date_time_str:
            try:
                if isinstance(date_time_str, str):
                    date_time = datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
                else:
                    date_time = date_time_str
                now = datetime.now(timezone.utc)
                hours_before = (date_time - now).total_seconds() / 3600
                if hours_before < 12:
                    return jsonify({
                        'success': False,
                        'error': f'Нельзя отозвать принятый отклик менее чем за 12 часов до начала задания (осталось {hours_before:.1f} ч)'
                    }), 409
            except (ValueError, TypeError):
                pass  # Если дата невалидна — пропускаем проверку

        # Уменьшить current_workers
        current_workers = max(0, job.get('current_workers', 1) - 1)
        new_job_status = job.get('status')
        if current_workers == 0 and new_job_status == 'completed':
            new_job_status = 'open'

        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'current_workers': current_workers,
            'status': new_job_status
        })

        # Уведомить работодателя
        notify(job['employer_id'], 'withdraw', 'Работник отозвал отклик',
               f'Принятый работник отозвал отклик с задания #{job_id}')

    # Поменять статус отклика на withdrawn
    supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'withdrawn'})

    # Если был pending — просто удаляем отклик (старая логика unapply)
    if current_status == 'pending':
        supabase_request('DELETE', f'applications?id=eq.{app_id}')

    return jsonify({
        'success': True,
        'message': 'Отклик отозван',
        'new_status': 'withdrawn'
    })


@applications_bp.route('/my-applications')
@login_required
def my_applications():
    """Отображение откликов на задания работодателя"""
    if session.get('role') != 'employer':
        flash('Доступ только для работодателей', 'danger')
        return redirect(url_for('jobs.index'))

    user_id = session['user_id']
    skills_filter = request.args.get('skills', '')

    resp = supabase_request('GET',
        f'applications?job.employer_id=eq.{user_id}&select=*,worker:profiles!inner(id,full_name,photo_url,rating,skills,desired_payment,inn,phone,email_public),job:jobs(organization_name,date_time,payment_amount,status,current_workers,max_workers)')
    applications = resp.json() if resp.ok else []

    # Фильтрация по навыкам (AND — все выбранные навыки должны быть у трудника)
    if skills_filter:
        selected_skills = [s.strip().lower() for s in skills_filter.split(',') if s.strip()]
        if selected_skills:
            applications = [a for a in applications if a.get('worker') and a['worker'].get('skills') and
                           all(any(sk.lower() in (ws.lower() if ws else '') for ws in a['worker']['skills']) for sk in selected_skills)]

    selected_skills_list = [s.strip() for s in skills_filter.split(',') if s.strip()] if skills_filter else []

    # Используем встроенные данные заданий из запроса (job:jobs(...))
    # вместо повторного запроса к API
    jobs = {}
    for app in applications:
        job_data = app.get('job')
        if job_data and job_data.get('id'):
            jobs[job_data['id']] = job_data

    # Контакты видны сразу (новая модель pay-per-job)
    for app_data in applications:
        if app_data.get('worker'):
            app_data['worker_contacts'] = app_data['worker']
        else:
            app_data['worker_contacts'] = None

    return render_template('my_applications.html', applications=applications, jobs=jobs,
                           selected_skills=selected_skills_list)


@applications_bp.route('/api/applications/test', methods=['GET', 'POST'])
def api_test():
    return jsonify({'success': True, 'message': 'applications blueprint is alive'})
# Маршруты accept/reject/reopen вынесены в app/__init__.py (на объект app)
# из-за проблем с blueprint-роутингом на production (Render).
# Функция api_handle_application импортируется оттуда.

def api_handle_application(app_id, action):
    """AJAX-эндпоинт: принять / отклонить / повторно принять отклик"""
    current_app.logger.info('[APPLICATIONS] action=%s app_id=%s user_id=%s', action, app_id, session.get('user_id'))
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        current_app.logger.warning('[APPLICATIONS] app_id=%s FAILED: ok=%s status=%s text=%s', app_id, app_resp.ok, app_resp.status_code, (app_resp.text or '')[:200])
        return jsonify({'success': False, 'error': 'Отклик не найден'}), 404

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']
    current_status = app_data.get('status', 'pending')
    # === AUTHORIZATION: проверяем, что задание принадлежит текущему пользователю ===
    owner_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=employer_id')
    if not (owner_resp.ok and owner_resp.json()):
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404
    if owner_resp.json()[0]['employer_id'] != session.get('user_id'):
        return jsonify({'success': False, 'error': 'Доступ запрещён'}), 403

    if action == 'accept':
        # Повторное принятие: возвращаем rejected → pending
        if current_status == 'rejected':
            supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'pending'})

        # Проверить количество мест и статус задания
        job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers,status')
        if not job_resp.ok or not job_resp.json():
            return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

        job = job_resp.json()[0]
        current_workers = job.get('current_workers', 0)
        max_workers = job.get('max_workers', 1)

        if current_workers >= max_workers:
            return jsonify({'success': False, 'error': f'Все места в задании заняты (максимум {max_workers})'}), 409

        if job.get('status') != 'open':
            return jsonify({'success': False, 'error': 'Задание уже закрыто для принятия откликов'}), 409

        # Атомарный PATCH с условием: обновляем только если current_workers < max_workers
        # PostgREST выполняет UPDATE с WHERE current_workers < {max_workers} атомарно на уровне БД
        # Благодаря Prefer: return=representation, при успехе возвращается обновлённая запись
        new_count = current_workers + 1
        new_status = 'completed' if new_count >= max_workers else 'open'
        patch_resp = supabase_request('PATCH', f'jobs?id=eq.{job_id}&current_workers=lt.{max_workers}', json={
            'status': new_status,
            'current_workers': new_count
        })
        current_app.logger.info(
            '[ACCEPT] atomic PATCH: job_id=%s current=%s max=%s ok=%s status=%s json=%s text=%s',
            job_id, current_workers, max_workers, patch_resp.ok, patch_resp.status_code,
            (patch_resp.json() if patch_resp.ok else None), (patch_resp.text or '')[:200]
        )
        if not (patch_resp.ok and patch_resp.json()):
            return jsonify({'success': False, 'error': 'Не удалось забронировать место (конкуренция запросов)'}), 409

        # Принять отклик
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'accepted'})

        # Отклонить остальные ожидающие отклики на это задание
        supabase_request('PATCH', f'applications?job_id=eq.{job_id}&status=eq.pending&id=neq.{app_id}',
                         json={'status': 'rejected'})

        # Уведомить работника
        notify(worker_id, 'application_accepted', 'Отклик принят',
               f'Ваш отклик на задание #{job_id} был принят')

        return jsonify({
            'success': True,
            'new_status': 'accepted',
            'message': 'Работник принят'
        })

    elif action == 'reject':
        if current_status == 'accepted':
            # === ОТКЛОНЕНИЕ УЖЕ ПРИНЯТОГО РАБОТНИКА ===
            # 1. Получить данные задания
            job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers,status')
            if not job_resp.ok or not job_resp.json():
                return jsonify({'success': False, 'error': 'Задание не найдено'}), 404

            job = job_resp.json()[0]
            current_workers = max(0, job.get('current_workers', 1) - 1)
            new_job_status = 'open' if current_workers == 0 else 'completed'

            # 2. Уменьшить счётчик и обновить статус задания
            supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
                'status': new_job_status,
                'current_workers': current_workers
            })

            # 3. Отклонить отклик
            supabase_request('PATCH', f'applications?id=eq.{app_id}', json={
                'status': 'rejected',
            })

            # 5. Уведомить работника
            notify(worker_id, 'application_rejected', 'Отклик отклонён',
                             f'Ваш отклик на задание #{job_id} был отклонён работодателем')

            return jsonify({
                'success': True,
                'new_status': 'rejected',
                'current_workers': current_workers,
                'job_status': new_job_status,
                'message': 'Работник отклонён'
            })

        # === ОБЫЧНОЕ ОТКЛОНЕНИЕ (pending → rejected) ===
        supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'rejected'})
        notify(worker_id, 'application_rejected', 'Отклик отклонён',
                         f'Ваш отклик на задание #{job_id} был отклонён')

        return jsonify({
            'success': True,
            'new_status': 'rejected',
            'message': 'Отклик отклонён'
        })

    elif action == 'reopen':
        if current_status != 'rejected':
            return jsonify({'success': False, 'error': 'Можно повторно принять только отклонённый отклик'}), 409

        return api_handle_application(app_id, 'accept')

    return jsonify({'success': False, 'error': 'Неизвестное действие'}), 400


@applications_bp.route('/api/applications/batch', methods=['POST'])
@login_required
def api_batch_applications():
    """Массовая операция над откликами (принять / отклонить / повторно принять)"""
    data = request.get_json(silent=True) or {}
    app_ids = data.get('app_ids', [])
    action = data.get('action')

    if not app_ids or not action:
        return jsonify({'success': False, 'error': 'Не указаны ID откликов или действие'}), 400

    if action not in ('accept', 'reject', 'reopen'):
        return jsonify({'success': False, 'error': f'Неизвестное действие: {action}'}), 400

    results = {'success': [], 'errors': []}

    for app_id in app_ids:
        try:
            # Симулируем вызов индивидуального эндпоинта
            app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
            if not app_resp.ok or not app_resp.json():
                results['errors'].append({'id': app_id, 'error': 'Отклик не найден'})
                continue

            app_data = app_resp.json()[0]
            current_status = app_data.get('status', 'pending')

            # Для reopen проверяем, что статус rejected
            if action == 'reopen' and current_status != 'rejected':
                results['errors'].append({'id': app_id, 'error': 'Можно повторно принять только отклонённый отклик'})
                continue

            # Выполняем действие через общий обработчик
            # (он сам делает все проверки: авторизацию, места, атомарный PATCH)
            result = api_handle_application(app_id, action)
            # api_handle_application может вернуть Response или tuple (Response, status)
            if isinstance(result, tuple):
                data = result[0].get_json()
            else:
                data = result.get_json()
            if data.get('success'):
                results['success'].append({
                    'id': app_id,
                    'new_status': data.get('new_status', action if action != 'reopen' else 'accepted')
                })
            else:
                results['errors'].append({'id': app_id, 'error': data.get('error', 'Ошибка')})
        except Exception as e:
            current_app.logger.error('Batch application error: app_id=%s, action=%s, error=%s',
                                     app_id, action, str(e))
            results['errors'].append({'id': app_id, 'error': str(e)})

    return jsonify({
        'success': len(results['success']) > 0,
        'results': results,
        'message': f'✅ {len(results["success"])} успешно, ⚠️ {len(results["errors"])} с ошибками'
    })


@applications_bp.route('/application/<app_id>/cancel', methods=['POST'])
@login_required
def cancel_application(app_id):
    """Отмена принятого работника"""
    app_resp = supabase_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('applications.my_applications'))

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']

    # Получить информацию о задании
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status,date_time,organization_name')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('applications.my_applications'))

    job = job_resp.json()[0]

    # Проверить статус задания (нельзя отменить в отозванном)
    if job['status'] == 'cancelled':
        flash('Нельзя отменить работника в отозванном задании', 'danger')
        return redirect(url_for('applications.my_applications'))

    # Проверить время (если статус completed - проверить 12 часов до начала)
    if job['status'] == 'completed':
        date_time_str = job.get('date_time')
        if date_time_str:
            try:
                if isinstance(date_time_str, str):
                    date_time = datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
                else:
                    date_time = date_time_str
                now = datetime.now(timezone.utc)
                hours_before = (date_time - now).total_seconds() / 3600
                if hours_before < 12:
                    flash(f'Нельзя отменить работника менее чем за 12 часов до начала (осталось {hours_before:.1f} ч)', 'danger')
                    return redirect(url_for('applications.my_applications'))
            except (ValueError, TypeError):
                pass

    # Уменьшить счетчик работников
    job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=current_workers,max_workers')
    if job_resp.ok and job_resp.json():
        job_data = job_resp.json()[0]
        current_workers = max(0, job_data.get('current_workers', 1) - 1)

        # Вернуть статус в open если все ушли
        new_status = 'open' if current_workers == 0 else 'completed'
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'status': new_status,
            'current_workers': current_workers
        })

    # Отклонить отклик
    supabase_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'rejected'})

    # Отправить уведомления
    notify(worker_id, 'application_rejected', 'Отклик отменен',
                     f'Ваш отклик на задание {job.get("organization_name", "#" + job_id)} был отменен')

    flash('Работник отменен', 'success')
    return redirect(url_for('applications.my_applications'))
