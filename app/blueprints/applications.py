from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required
from app.utils import rate_limit, supabase_request, supabase_admin_request, supabase_rpc
from app.services.notification_service import create as notify

applications_bp = Blueprint('applications', __name__)


@applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
@login_required
@rate_limit
def apply_job(job_id):
    user_id = session['user_id']

    # Быстрая предварительная проверка дубликата (некритичная, только для UX)
    check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if check.ok and check.json():
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('jobs.index'))

    # Атомарная RPC: все проверки + вставка отклика в одной транзакции PostgreSQL
    # Устраняет TOCTOU race condition между проверкой мест и созданием отклика
    rpc_result = supabase_rpc('apply_job_atomic', {
        'p_job_id': job_id,
        'p_worker_id': user_id,
    }, use_admin=True)

    if not rpc_result.ok:
        flash('Ошибка при отправке отклика', 'danger')
        return redirect(url_for('jobs.index'))

    result = rpc_result.json()

    if not result or not result.get('success'):
        error_code = (result or {}).get('code', 'unknown')
        error_msg = (result or {}).get('error', 'Не удалось отправить отклик')

        # Для blacklist-ошибки при POST-запросе возвращаем JSON (как в оригинале)
        if error_code == 'blacklisted':
            if request.method == 'POST':
                return jsonify({'success': False, 'error': error_msg}), 403
            flash(error_msg, 'danger')
            return redirect(url_for('jobs.index'))

        category = 'info' if error_code in ('duplicate', 'no_slots') else 'danger'
        flash(error_msg, category)
        return redirect(url_for('jobs.index'))

    # Успех: уведомить работодателя о новом отклике
    employer_id = result.get('employer_id')
    if employer_id:
        notify(employer_id, 'application_received', 'Новый отклик',
               f'На ваше задание поступил новый отклик',
               data={'job_id': job_id, 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

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
    skipped_count = 0
    for job_id in job_ids:
        # Проверить статус задания
        job_resp = supabase_request('GET', f'jobs?id=eq.{job_id}&select=status')
        if job_resp.ok and job_resp.json():
            job = job_resp.json()[0]
            if job['status'] != 'open':
                skipped_count += 1
                continue

        check = supabase_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
        if not (check.ok and check.json()):
            supabase_request('POST', 'applications', json={'job_id': job_id, 'worker_id': user_id})
            applied += 1

    if applied > 0:
        flash(f'Отклик отправлен на {applied} заданий', 'success')
    else:
        flash('Вы уже откликались на все выбранные задания', 'info')
    if skipped_count > 0:
        flash(f'{skipped_count} заданий пропущено (нельзя откликнуться).', 'warning')
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
               f'Принятый работник отозвал отклик с задания #{job_id}',
               data={'job_id': job_id, 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

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
@login_required
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

        # Атомарный accept через RPC (этап 4.4)
        rpc_result = supabase_rpc('accept_application', {
            'p_job_id': job_id,
            'p_app_id': app_id,
        }, use_admin=True)

        if not rpc_result.ok:
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

        result_data = rpc_result.json()
        if not result_data or not result_data.get('success'):
            error_msg = (result_data or {}).get('error', 'Не удалось принять отклик')
            status_code = 409 if 'места' in error_msg else 400
            return jsonify({'success': False, 'error': error_msg}), status_code

        # Уведомить работника
        notify(worker_id, 'application_accepted', 'Отклик принят',
               f'Ваш отклик на задание #{job_id} был принят',
               data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})

        return jsonify({
            'success': True,
            'new_status': 'accepted',
            'message': 'Работник принят'
        })

    elif action == 'reject':
        # Атомарный reject через RPC (этап 4.4)
        rpc_result = supabase_rpc('reject_application', {
            'p_job_id': job_id,
            'p_app_id': app_id,
        }, use_admin=True)

        if not rpc_result.ok:
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

        result_data = rpc_result.json()
        if not result_data or not result_data.get('success'):
            error_msg = (result_data or {}).get('error', 'Не удалось отклонить отклик')
            return jsonify({'success': False, 'error': error_msg}), 400

        # Уведомить работника
        notify(worker_id, 'application_rejected', 'Отклик отклонён',
               f'Ваш отклик на задание #{job_id} был отклонён',
               data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})

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

    if len(app_ids) > Config.MAX_BATCH_SIZE:
        return jsonify({'success': False, 'error': f'Максимальный размер пакета: {Config.MAX_BATCH_SIZE}'}), 400

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
                      f'Ваш отклик на задание {job.get("organization_name", "#" + job_id)} был отменен',
                      data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})

    flash('Работник отменен', 'success')
    return redirect(url_for('applications.my_applications'))
