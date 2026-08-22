import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.config import Config
from app.decorators import login_required, rate_limit, role_required, validate_uuid
from app.utils import postgrest_request, postgrest_rpc
from app.services.notification_service import enqueue_notification

logger = logging.getLogger(__name__)

applications_bp = Blueprint('applications', __name__)


@applications_bp.route('/apply/<job_id>', methods=['POST'])
@login_required
@validate_uuid('job_id')
@rate_limit
def apply_job(job_id):
    user_id = session['user_id']

    # Атомарная RPC: все проверки + вставка отклика в одной транзакции PostgreSQL
    # RPC сам обрабатывает дубликаты (code=duplicate) — pre-check удалён (B24)
    rpc_result = postgrest_rpc('apply_job_atomic', {
        'p_job_id': job_id,
        'p_worker_id': user_id,
    }, use_admin=True)

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            logger.error(
                "apply_job: RPC apply_job_atomic not found for job_id=%s user_id=%s",
                job_id, user_id
            )
            return jsonify({'success': False, 'error': 'Сервис не настроен'}), 503
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

    # Успех: уведомить работодателя о новом отклике (transactional outbox)
    employer_id = result.get('employer_id')
    if employer_id:
        _link = url_for('jobs.job_detail', job_id=job_id, _external=True)
        success = enqueue_notification(employer_id, 'application_received', 'Новый отклик',
               f'На ваше задание поступил новый отклик',
               data={'job_id': job_id, 'link': _link})
        if not success:
            logger.error("apply_job: enqueue_notification() вернул False для employer_id=%s job_id=%s",
                         employer_id, job_id)

    flash('Отклик отправлен', 'success')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/apply-selected', methods=['POST'])
@login_required
@role_required('worker')
def apply_selected():
    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.index'))

    user_id = session['user_id']

    applied = 0
    skipped_count = 0
    error_count = 0
    # Словарь для группировки уведомлений: employer_id -> list of job_ids
    employer_jobs = {}

    for job_id in job_ids:
        # Атомарная RPC: все проверки (статус, blacklist, свой же заказ, дубликат, слоты) + вставка
        rpc_result = postgrest_rpc('apply_job_atomic', {
            'p_job_id': job_id,
            'p_worker_id': user_id,
        }, use_admin=True)

        if not rpc_result.ok:
            if rpc_result.status_code == 404:
                logger.warning(
                    "apply_selected: RPC apply_job_atomic not found for job_id=%s, skipping", job_id
                )
            skipped_count += 1
            continue

        result = rpc_result.json()
        if not result or not result.get('success'):
            error_code = (result or {}).get('code', 'unknown')
            if error_code in ('duplicate', 'job_not_open', 'own_job', 'no_slots'):
                skipped_count += 1
            else:
                error_count += 1
                logger.warning(
                    "apply_selected: RPC apply_job_atomic failed for job_id=%s code=%s error=%s",
                    job_id, error_code, (result or {}).get('error', '')
                )
            continue

        applied += 1
        employer_id = result.get('employer_id')
        if employer_id:
            if employer_id not in employer_jobs:
                employer_jobs[employer_id] = []
            employer_jobs[employer_id].append(job_id)

    # Отправляем уведомления работодателям (transactional outbox)
    if employer_jobs:
        _applications_link = url_for('applications.my_applications', _external=True)
        for emp_id, jids in employer_jobs.items():
            job_list = ', '.join(f'#{jid}' for jid in jids)
            success = enqueue_notification(
                emp_id, 'application_received', 'Новые отклики',
                f'На ваши задания ({job_list}) поступили новые отклики',
                data={'job_ids': jids, 'link': _applications_link}
            )
            if not success:
                logger.error("apply_selected: enqueue_notification() вернул False для employer_id=%s job_ids=%s",
                             emp_id, jids)

    if applied > 0:
        flash(f'Отклик отправлен на {applied} заданий', 'success')
    if skipped_count > 0:
        flash(f'{skipped_count} заданий пропущено (уже откликались или недоступны).', 'warning')
    if error_count > 0:
        flash(f'{error_count} заданий не обработано из-за ошибок.', 'danger')
    if applied == 0 and skipped_count == 0 and error_count == 0:
        flash('Вы уже откликались на все выбранные задания', 'info')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/unapply/<job_id>', methods=['POST'])
@login_required
@validate_uuid('job_id')
def unapply_job(job_id):
    """Отзыв отклика по job_id (редирект на withdraw_application_atomic).

    Находит отклик по job_id + worker_id, затем вызывает атомарный отзыв.
    Сохраняет обратную совместимость URL /unapply/<job_id>.
    """
    from app.services.application_service import withdraw_application_atomic

    user_id = session['user_id']
    # Найти отклик по job_id + worker_id
    app_resp = postgrest_request(
        'GET',
        f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}&select=id'
    )
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден (возможно, он уже отозван)', 'danger')
        return redirect(url_for('jobs.index'))

    app_id = app_resp.json()[0]['id']
    result = withdraw_application_atomic(app_id, user_id)

    if result.get('success'):
        flash(result.get('message', 'Отклик отозван'), 'success')
    else:
        flash(result.get('error', 'Не удалось отозвать отклик'), 'danger')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/unapply-selected', methods=['POST'])
@login_required
def unapply_selected():
    """Массовый отзыв откликов через withdraw_application_atomic.

    Находит каждый отклик по job_id + worker_id и вызывает атомарный отзыв.
    Сохраняет обратную совместимость URL /unapply-selected.
    """
    from app.services.application_service import withdraw_application_atomic

    job_ids = request.form.getlist('job_ids')
    if not job_ids:
        flash('Не выбрано ни одного задания', 'danger')
        return redirect(url_for('jobs.index'))
    user_id = session['user_id']
    withdrawn = 0
    errors = 0
    for job_id in job_ids:
        app_resp = postgrest_request(
            'GET',
            f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}&select=id'
        )
        if not app_resp.ok or not app_resp.json():
            errors += 1
            continue
        app_id = app_resp.json()[0]['id']
        result = withdraw_application_atomic(app_id, user_id)
        if result.get('success'):
            withdrawn += 1
        else:
            errors += 1
    if withdrawn > 0:
        flash(f'Отклики отозваны ({withdrawn} заданий)', 'success')
    if errors > 0:
        flash(f'{errors} откликов не удалось отозвать', 'warning')
    if withdrawn == 0 and errors == 0:
        flash('Ни один отклик не найден', 'info')
    return redirect(url_for('jobs.index'))


@applications_bp.route('/api/applications/<app_id>/withdraw', methods=['POST'])
@login_required
@validate_uuid('app_id')
def api_withdraw_application(app_id):
    """Отзыв отклика работником (автором).
    Использует унифицированный сервис app/services/application_service.py.
    """
    from app.services.application_service import withdraw_application_atomic

    result = withdraw_application_atomic(app_id, session['user_id'])
    if not result['success']:
        status_code = {
            'Отклик не найден': 404,
            'Вы не автор этого отклика': 403,
            'Отклик уже отозван': 409,
        }
        error_msg = result.get('error', '')
        code = 409
        for key, sc in status_code.items():
            if key in error_msg:
                code = sc
                break
        return jsonify(result), code

    return jsonify(result)


@applications_bp.route('/my-applications')
@login_required
@role_required('employer')
def my_applications():
    """Отображение откликов на задания работодателя (с пагинацией)."""
    user_id = session['user_id']
    skills_filter = request.args.get('skills', '')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', Config.PAGINATION_DEFAULT_PER_PAGE, type=int)))

    selected_skills = [s.strip().lower() for s in skills_filter.split(',') if s.strip()] if skills_filter else []

    # C33: При фильтре по навыкам — загружаем все заявки без пагинации,
    # фильтруем на стороне Python, затем пагинируем. Это гарантирует,
    # что offset учитывает фильтр и пагинация работает корректно.
    if selected_skills:
        # Загружаем все заявки (с разумным верхним пределом 500)
        resp = postgrest_request('GET',
            f'applications?job.employer_id=eq.{user_id}&select=*,worker:profiles!inner(id,full_name,photo_url,rating,desired_payment,email_public),job:jobs(organization_name,date_time,payment_amount,status,current_workers,max_workers)&limit=500',
            headers={'Prefer': 'count=exact'})
        all_applications = resp.json() if resp.ok else []

        # Фильтрация по навыкам отключена: profiles.skills убран (миграция на user_skills).
        # TODO: реализовать фильтр через user_skills junction table.
        # all_applications проходит без фильтра.

        total = len(all_applications)
        offset = (page - 1) * per_page
        applications = all_applications[offset:offset + per_page]
    else:
        offset = (page - 1) * per_page
        resp = postgrest_request('GET',
            f'applications?job.employer_id=eq.{user_id}&select=*,worker:profiles!inner(id,full_name,photo_url,rating,desired_payment,email_public),job:jobs(organization_name,date_time,payment_amount,status,current_workers,max_workers)&limit={per_page}&offset={offset}',
            headers={'Prefer': 'count=exact'})
        applications = resp.json() if resp.ok else []
        total = 0
        if resp.ok:
            content_range = resp.headers.get('Content-Range', '')
            if '/' in content_range:
                total = int(content_range.split('/')[-1])

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

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return render_template('my_applications.html', applications=applications, jobs=jobs,
                           selected_skills=selected_skills,
                           page=page, per_page=per_page, total=total,
                           total_pages=total_pages)


@applications_bp.route('/api/applications/<app_id>/accept', methods=['POST'])
@login_required
@rate_limit
@validate_uuid('app_id')
def api_accept_application(app_id):
    return api_handle_application(app_id, 'accept')


@applications_bp.route('/api/applications/<app_id>/reject', methods=['POST'])
@login_required
@rate_limit
@validate_uuid('app_id')
def api_reject_application(app_id):
    return api_handle_application(app_id, 'reject')


@applications_bp.route('/api/applications/<app_id>/reopen', methods=['POST'])
@login_required
@validate_uuid('app_id')
def api_reopen_application(app_id):
    return api_handle_application(app_id, 'reopen')


def api_handle_application(app_id, action):
    """AJAX-эндпоинт: принять / отклонить / повторно принять отклик"""
    current_app.logger.info('[APPLICATIONS] action=%s app_id=%s user_id=%s', action, app_id, session.get('user_id'))
    app_resp = postgrest_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        current_app.logger.warning('[APPLICATIONS] app_id=%s FAILED: ok=%s status=%s text=%s', app_id, app_resp.ok, app_resp.status_code, (app_resp.text or '')[:200])
        return jsonify({'success': False, 'error': 'Отклик не найден'}), 404

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']
    current_status = app_data.get('status', 'pending')
    # === AUTHORIZATION: проверяем, что задание принадлежит текущему пользователю ===
    owner_resp = postgrest_request('GET', f'jobs?id=eq.{job_id}&select=employer_id')
    if not (owner_resp.ok and owner_resp.json()):
        return jsonify({'success': False, 'error': 'Задание не найдено'}), 404
    if owner_resp.json()[0]['employer_id'] != session.get('user_id'):
        return jsonify({'success': False, 'error': 'Доступ запрещён'}), 403

    if action == 'accept':
        # Атомарный accept через RPC (принимает заявки в статусах pending и rejected)
        # RPC сам проверяет статус с FOR UPDATE — нет TOCTOU race condition
        rpc_result = postgrest_rpc('accept_application', {
            'p_job_id': job_id,
            'p_app_id': app_id,
        }, use_admin=True)

        if not rpc_result.ok:
            current_app.logger.warning('[APPLICATIONS] accept RPC failed: app_id=%s status=%s text=%s', 
                                       app_id, rpc_result.status_code, (rpc_result.text or '')[:200])
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

        result_data = rpc_result.json()
        if not result_data or not result_data.get('success'):
            error_code = (result_data or {}).get('code', '')
            error_msg = (result_data or {}).get('error', 'Не удалось принять отклик')
            # bad_status = заявка уже обработана (race condition)
            if error_code == 'bad_status' or 'concurrent' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Заявка уже обработана'}), 409
            status_code = 409 if 'места' in error_msg or error_code == 'no_slots' else 400
            return jsonify({'success': False, 'error': error_msg}), status_code

        # Уведомить работника (transactional outbox)
        success = enqueue_notification(worker_id, 'application_accepted', 'Отклик принят',
               f'Ваш отклик на задание #{job_id} был принят',
               data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})
        if not success:
            logger.error("api_handle_application accept: enqueue_notification() вернул False для worker_id=%s job_id=%s",
                         worker_id, job_id)

        return jsonify({
            'success': True,
            'new_status': 'accepted',
            'message': 'Работник принят'
        })

    elif action == 'reject':
        # Атомарный reject через RPC (этап 4.4)
        # RPC сам проверяет статус с FOR UPDATE — нет TOCTOU race condition
        rpc_result = postgrest_rpc('reject_application', {
            'p_job_id': job_id,
            'p_app_id': app_id,
        }, use_admin=True)

        if not rpc_result.ok:
            current_app.logger.warning('[APPLICATIONS] reject RPC failed: app_id=%s status=%s text=%s', 
                                       app_id, rpc_result.status_code, (rpc_result.text or '')[:200])
            return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

        result_data = rpc_result.json()
        if not result_data or not result_data.get('success'):
            error_code = (result_data or {}).get('code', '')
            error_msg = (result_data or {}).get('error', 'Не удалось отклонить отклик')
            # already_rejected = заявка уже обработана (race condition)
            if error_code == 'already_rejected' or 'concurrent' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Заявка уже обработана'}), 409
            return jsonify({'success': False, 'error': error_msg}), 400

        # Уведомить работника (transactional outbox)
        success = enqueue_notification(worker_id, 'application_rejected', 'Отклик отклонён',
               f'Ваш отклик на задание #{job_id} был отклонён',
               data={'job_id': job_id, 'link': url_for('applications.my_applications', _external=True)})
        if not success:
            logger.error("api_handle_application reject: enqueue_notification() вернул False для worker_id=%s job_id=%s",
                         worker_id, job_id)

        return jsonify({
            'success': True,
            'new_status': 'rejected',
            'message': 'Отклик отклонён'
        })

    elif action == 'reopen':
        # Повторное принятие отклонённого отклика — делегируем accept
        # RPC сам проверит статус с FOR UPDATE
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
            app_resp = postgrest_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
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
            resp_obj = result[0] if isinstance(result, tuple) else result
            try:
                data = resp_obj.get_json()
            except Exception:
                data = None
            if not data or not isinstance(data, dict):
                results['errors'].append({'id': app_id, 'error': 'Неожиданный ответ сервера'})
                continue
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
@validate_uuid('app_id')
def cancel_application(app_id):
    """Отмена принятого работника"""
    app_resp = postgrest_request('GET', f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        flash('Отклик не найден', 'danger')
        return redirect(url_for('applications.my_applications'))

    app_data = app_resp.json()[0]
    job_id = app_data['job_id']
    worker_id = app_data['worker_id']

    # Проверка: отменить можно только accepted-отклик
    if app_data.get('status') != 'accepted':
        flash('Можно отменить только принятого работника', 'danger')
        return redirect(url_for('applications.my_applications'))

    # C32: Ownership check — убедиться, что задание принадлежит текущему пользователю
    job_resp = postgrest_request('GET', f'jobs?id=eq.{job_id}&select=status,date_time,organization_name,employer_id')
    if not job_resp.ok or not job_resp.json():
        flash('Задание не найдено', 'danger')
        return redirect(url_for('applications.my_applications'))

    job = job_resp.json()[0]

    if job.get('employer_id') != session.get('user_id'):
        flash('Нет доступа к этому заданию', 'danger')
        return redirect(url_for('applications.my_applications'))

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

    # Атомарная отмена через RPC cancel_worker_atomic
    rpc_result = postgrest_rpc('cancel_worker_atomic', {
        'p_application_id': app_id,
        'p_user_id': session.get('user_id'),
    }, use_admin=True)

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            logger.error(
                'cancel_application: RPC cancel_worker_atomic not found for app_id=%s', app_id
            )
            return jsonify({'success': False, 'error': 'Сервис не настроен'}), 503
        flash('Ошибка при отмене работника', 'danger')
        return redirect(url_for('applications.my_applications'))

    rpc_data = rpc_result.json()
    if not rpc_data or not rpc_data.get('success'):
        error_msg = (rpc_data or {}).get('error', 'Не удалось отменить работника')
        flash(error_msg, 'danger')
        return redirect(url_for('applications.my_applications'))

    current_app.logger.info(
        'cancel_application: RPC cancel_worker_atomic OK for app_id=%s job_id=%s new_status=%s',
        app_id, job_id, rpc_data.get('new_status')
    )

    flash('Работник отменен', 'success')
    return redirect(url_for('applications.my_applications'))
