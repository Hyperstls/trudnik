"""
Blueprint монетизации: платежи за контакты, чеки самозанятого,
генерация акта ГПХ, напоминания о чеке, проверка переквалификации.

Юридически значимые действия:
- Фиксация оплаты за информационную услугу (раскрытие контакта)
- Формирование чека самозанятого (заглушка API ФНС)
- Предупреждение о переквалификации (ст. 15 ТК РФ)
"""

import io
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request, session, send_file, render_template, url_for, flash

from app.decorators import login_required
from app.services.payment_service import PaymentService
from app.services.receipt_service import ReceiptService
from app.utils import supabase_request
from app.services.notification_service import create as notify

monetization_bp = Blueprint('monetization', __name__, url_prefix='/api')




# ============================================================
# 2. ЧЕКИ (администратор)
# ============================================================

@monetization_bp.route('/receipts/<receipt_id>/resend', methods=['POST'])
@login_required
def resend_receipt(receipt_id):
    """Переотправка чека администратором."""
    # Проверка роли администратора
    role_resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
    if not role_resp.ok or not role_resp.json() or role_resp.json()[0]['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    success = ReceiptService.resend_receipt(receipt_id)
    return jsonify({'success': success})


# ============================================================
# 3. ПРОВЕРКА ПЕРЕКВАЛИФИКАЦИИ
# ============================================================

@monetization_bp.route('/hires/check', methods=['GET'])
@login_required
def check_hires():
    """
    Проверить количество наймов текущего пользователя за 30 дней.

    Юридически значимое действие: предупреждение о переквалификации.
    Ст. 15 ТК РФ — признаки трудовых отношений.
    """
    user_id = session['user_id']
    role_resp = supabase_request('GET', f'profiles?id=eq.{user_id}&select=role')
    role = role_resp.json()[0]['role'] if role_resp.ok and role_resp.json() else 'worker'

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    if role == 'employer':
        # Проверить всех работников этого работодателя
        hires_resp = supabase_request(
            'GET',
            f'hires?employer_id=eq.{user_id}&hired_at=gte.{thirty_days_ago}&select=worker_id'
        )
    else:
        # Проверить всех работодателей этого работника
        hires_resp = supabase_request(
            'GET',
            f'hires?worker_id=eq.{user_id}&hired_at=gte.{thirty_days_ago}&select=employer_id'
        )

    if not hires_resp.ok or not hires_resp.json():
        return jsonify({'warnings': []})

    hires = hires_resp.json()

    # Группировать по парам
    from collections import Counter
    if role == 'employer':
        pairs = Counter(h['worker_id'] for h in hires)
    else:
        pairs = Counter(h['employer_id'] for h in hires)

    warnings = []
    for partner_id, count in pairs.items():
        if count >= 3:
            # Получить имя партнёра
            partner_resp = supabase_request('GET', f'profiles?id=eq.{partner_id}&select=full_name')
            partner_name = partner_resp.json()[0]['full_name'] if partner_resp.ok and partner_resp.json() else partner_id[:8]

            warnings.append({
                'partner_id': partner_id,
                'partner_name': partner_name,
                'count': count,
                'message': (
                    f'Рекомендуем рассмотреть оформление трудовых отношений с {partner_name}, '
                    f'если работа имеет постоянный характер. Частые разовые услуги '
                    f'({count} раз(а) за 30 дней) могут быть переквалифицированы.'
                ),
            })

    return jsonify({'warnings': warnings})


# ============================================================
# 4. ГЕНЕРАЦИЯ АКТА ГПХ (PDF)
# ============================================================

@monetization_bp.route('/act/generate/<application_id>', methods=['GET'])
@login_required
def generate_act(application_id):
    """
    Сгенерировать PDF-документ договора-акта ГПХ.

    Юридически значимое действие: формирование договора гражданско-правового
    характера, подтверждающего разовый характер услуги.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return jsonify({'success': False, 'error': 'PDF library not installed. Run: pip install fpdf2'}), 500

    # Получить данные отклика
    app_resp = supabase_request(
        'GET',
        f'applications?id=eq.{application_id}&select=*,job:jobs(*),worker:profiles!worker_id(*)'
    )
    if not app_resp.ok or not app_resp.json():
        return jsonify({'success': False, 'error': 'Application not found'}), 404

    app_data = app_resp.json()[0]
    job = app_data.get('job', {})
    worker = app_data.get('worker', {})

    # Получить данные работодателя
    employer_resp = supabase_request('GET', f'profiles?id=eq.{job["employer_id"]}&select=full_name,inn')
    employer = employer_resp.json()[0] if employer_resp.ok and employer_resp.json() else {}

    # Сгенерировать PDF
    pdf = FPDF()
    pdf.add_page()

    # Заголовок
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'ДОГОВОР-АКТ', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Helvetica', '', 12)
    pdf.cell(0, 8, 'оказания услуг (выполнения работ)', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)

    # Номер и дата
    now = datetime.now()
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 7, f'№ {application_id[:8].upper()}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f'Дата составления: {now.strftime("%d.%m.%Y")}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Стороны
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '1. СТОРОНЫ ДОГОВОРА', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Заказчик: {employer.get("full_name", "Храм")}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f'ИНН Заказчика: {employer.get("inn", "—")}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.cell(0, 6, f'Исполнитель: {worker.get("full_name", "—")}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f'ИНН Исполнителя: {worker.get("inn", "—")}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Предмет договора
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '2. ПРЕДМЕТ ДОГОВОРА', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 6, f'Заказчик поручает, а Исполнитель принимает на себя '
                         f'обязательство выполнить следующую работу:\n'
                         f'{job.get("detailed_description", job.get("object_description", "—"))}')
    pdf.ln(5)

    # Сроки и стоимость
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '3. СРОКИ И СТОИМОСТЬ', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Срок выполнения: {job.get("date_time", "—")}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f'Стоимость: {job.get("payment_amount", 0)} руб.', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Юридически значимая фраза
    pdf.set_font('Helvetica', 'B', 10)
    pdf.multi_cell(0, 6, 'Исполнитель является плательщиком налога на профессиональный доход '
                         'и обязуется выдать Заказчику чек через приложение "Мой налог" '
                         'на сумму полученной оплаты.')
    pdf.ln(10)

    # Подписи
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '4. ПОДПИСИ СТОРОН', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, 'Заказчик: _______________ / ___________________ /', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f'Дата: {now.strftime("%d.%m.%Y")}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(0, 6, 'Исполнитель: _______________ / ___________________ /', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f'Дата: {now.strftime("%d.%m.%Y")}', new_x="LMARGIN", new_y="NEXT")

    # Отправить PDF
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'act_gpk_{application_id[:8]}.pdf',
    )


# ============================================================
# 5. НАПОМИНАНИЕ О ЧЕКЕ
# ============================================================

@monetization_bp.route('/cheque/remind/<application_id>', methods=['POST'])
@login_required
def remind_cheque(application_id):
    """
    Напомнить исполнителю выставить чек через «Мой налог».

    Юридически значимое действие: напоминание об обязанности
    самозанятого выдать чек заказчику.
    """
    app_resp = supabase_request(
        'GET',
        f'applications?id=eq.{application_id}&select=worker_id,job:jobs(payment_amount,organization_name)'
    )
    if not app_resp.ok or not app_resp.json():
        return jsonify({'success': False, 'error': 'Application not found'}), 404

    app_data = app_resp.json()[0]
    worker_id = app_data['worker_id']
    job = app_data.get('job', {})
    amount = job.get('payment_amount', 0)
    org_name = job.get('organization_name', 'Храм')

    # Проверить, что напоминание отправляет исполнитель
    if session['user_id'] != worker_id:
        return jsonify({'success': False, 'error': 'Only the worker can send this reminder'}), 403

    # Отправить уведомление (всплывающее сообщение)
    notify(
        worker_id, 'cheque_reminder',
        'Напоминание о чеке',
        f'Не забудьте выставить чек храму "{org_name}" в приложении '
        f'"Мой налог" на сумму {amount} руб.'
    )

    return jsonify({'success': True, 'message': 'Напоминание отправлено'})


# ============================================================
# 6. НАСТРОЙКИ МОНЕТИЗАЦИИ (администратор)
# ============================================================

@monetization_bp.route('/admin/monetization-settings', methods=['GET', 'POST'])
@login_required
def admin_monetization_settings():
    """Получить или сохранить настройки монетизации (тарифы + owner_inn)."""
    # Проверка роли администратора
    role_resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
    if not role_resp.ok or not role_resp.json() or role_resp.json()[0]['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if request.method == 'POST':
        data = request.get_json() or {}
        tariff_key = data.get('tariff_key')
        price = data.get('price')
        renewal_price = data.get('renewal_price')
        owner_inn = data.get('owner_inn')

        # Обновить тариф
        if tariff_key and price is not None:
            try:
                price = int(price)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'price must be a number'}), 400

            update_data = {'price': price}
            if renewal_price is not None:
                try:
                    update_data['renewal_price'] = int(renewal_price)
                except (ValueError, TypeError):
                    pass
            supabase_request('PATCH', f'tariff_settings?tariff_key=eq.{tariff_key}', json=update_data)

        # Обновить ИНН владельца
        if owner_inn is not None:
            supabase_request('PATCH', 'monetization_settings?key=eq.owner_inn', json={'value': owner_inn})

        return jsonify({'success': True})

    # GET — получить настройки
    settings = PaymentService.get_settings()
    tariffs = PaymentService.get_tariffs()
    return jsonify({'success': True, 'tariffs': tariffs, 'owner_inn': settings.get('owner_inn', '')})


@monetization_bp.route('/admin/payments', methods=['GET'])
@login_required
def admin_payments_list():
    """Список всех платежей за публикацию (для админа)."""
    role_resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
    if not role_resp.ok or not role_resp.json() or role_resp.json()[0]['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    resp = supabase_request('GET', 'job_payments?select=*&order=created_at.desc')
    payments = resp.json() if resp.ok else []

    return jsonify({'success': True, 'payments': payments})


@monetization_bp.route('/admin/job-stats', methods=['GET'])
@login_required
def admin_job_stats():
    """Статистика по оплаченным публикациям."""
    role_resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
    if not role_resp.ok or not role_resp.json() or role_resp.json()[0]['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    stats_resp = supabase_request('GET',
        'job_payments?status=eq.paid&select=amount,tariff,paid_at')
    payments = stats_resp.json() if stats_resp.ok else []
    total_revenue = sum(p['amount'] for p in payments)
    by_tariff = {}
    for p in payments:
        t = p.get('tariff', 'standard')
        by_tariff[t] = by_tariff.get(t, 0) + p['amount']

    return jsonify({
        'success': True,
        'total_paid_publications': len(payments),
        'total_revenue': total_revenue,
        'by_tariff': by_tariff,
    })


# ============================================================
# Внутренние утилиты
# ============================================================

def _check_hire_limit(employer_id, worker_id):
    """
    Проверить количество наймов пары за 30 дней.

    Юридически значимое действие: предупреждение о переквалификации
    (ст. 15 ТК РФ).
    """
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    count_resp = supabase_request(
        'GET',
        f'hires?employer_id=eq.{employer_id}&worker_id=eq.{worker_id}&hired_at=gte.{thirty_days_ago}&select=id'
    )

    if not count_resp.ok or not count_resp.json():
        return None

    count = len(count_resp.json())

    if count >= 3:
        # Получить имя работодателя
        employer_resp = supabase_request('GET', f'profiles?id=eq.{employer_id}&select=full_name')
        employer_name = employer_resp.json()[0]['full_name'] if employer_resp.ok and employer_resp.json() else 'Храм'

        worker_resp = supabase_request('GET', f'profiles?id=eq.{worker_id}&select=full_name')
        worker_name = worker_resp.json()[0]['full_name'] if worker_resp.ok and worker_resp.json() else 'Исполнитель'

        warning_msg = (
            f'Рекомендуем рассмотреть оформление трудовых отношений между '
            f'"{employer_name}" и {worker_name}, если работа имеет постоянный характер. '
            f'Частые разовые услуги ({count} раз(а) за 30 дней) могут быть переквалифицированы.'
        )

        # Уведомить обе стороны и администратора
        notify(employer_id, 'hire_limit_warning', 'Внимание: переквалификация', warning_msg)
        notify(worker_id, 'hire_limit_warning', 'Внимание: переквалификация', warning_msg)

        admin_resp = supabase_request('GET', 'profiles?role=eq.admin&select=id')
        if admin_resp.ok and admin_resp.json():
            for admin in admin_resp.json():
                notify(admin['id'], 'hire_limit_warning', 'Внимание: частая пара наймов', warning_msg)

        return {
            'warning': True,
            'count': count,
            'message': warning_msg,
        }

    return None
