"""
Сервис обработки платежей за публикацию задания.

Юридически значимое действие: фиксация платежа за размещение объявления.
Платформа не участвует в расчётах между храмом и исполнителем.
Платёж — за публикацию задания на платформе.
"""

from datetime import datetime, timezone, timedelta

from app.services.receipt_service import ReceiptService
from app.utils import supabase_request


class PaymentService:
    """Сервис для обработки платежей за публикацию задания."""

    @staticmethod
    def get_settings():
        """Загрузить настройки монетизации из БД (owner_inn + тарифы)."""
        resp = supabase_request('GET', 'monetization_settings?select=key,value')
        settings = {}
        if resp.ok and resp.json():
            for item in resp.json():
                settings[item['key']] = item['value']
        return {
            'owner_inn': settings.get('owner_inn', ''),
            'tariffs': PaymentService.get_tariffs(),
        }

    @staticmethod
    def get_tariffs():
        """Получить список активных тарифов."""
        resp = supabase_request('GET', 'tariff_settings?is_active=eq.true&order=price.asc')
        if resp.ok and resp.json():
            return resp.json()
        return [
            {'tariff_key': 'standard', 'price': 490, 'duration_days': 30, 'renewal_price': 290}
        ]

    @staticmethod
    def create_job_payment(employer_id, job_id, tariff='standard'):
        """Создать платёж за публикацию задания.

        Args:
            employer_id: ID работодателя
            job_id: ID задания
            tariff: Ключ тарифа

        Returns:
            dict: {payment_id, amount} или None при ошибке
        """
        tariffs = {t['tariff_key']: t for t in PaymentService.get_tariffs()}
        tariff_info = tariffs.get(tariff, {'price': 490, 'duration_days': 30})
        amount = tariff_info['price']

        resp = supabase_request('POST', 'job_payments', json={
            'job_id': job_id,
            'employer_id': employer_id,
            'amount': amount,
            'tariff': tariff,
            'type': 'publication',
            'status': 'pending',
        })
        if resp.ok and resp.json():
            payment = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
            return {'payment_id': payment['id'], 'amount': amount}
        return None

    @staticmethod
    def process_job_payment(payment_id, employer_id):
        """Обработать платёж и опубликовать задание.

        Args:
            payment_id: ID платежа
            employer_id: ID работодателя

        Returns:
            dict: {success, transaction_id}
        """
        # Получить платёж
        payment_resp = supabase_request(
            'GET',
            f'job_payments?id=eq.{payment_id}&select=*,job:jobs(organization_name)')
        if not payment_resp.ok or not payment_resp.json():
            return {'success': False, 'error': 'Payment not found'}

        payment = payment_resp.json()[0]

        # Эмуляция эквайринга (в будущем — реальный API)
        import time
        transaction_id = f"txn_{int(time.time() * 1000)}"

        now = datetime.now(timezone.utc).isoformat()
        tariffs = {t['tariff_key']: t for t in PaymentService.get_tariffs()}
        tariff_info = tariffs.get(payment.get('tariff', 'standard'), {'duration_days': 30})
        expires_at = (datetime.now(timezone.utc) + timedelta(days=tariff_info['duration_days'])).isoformat()

        # Обновить платёж
        supabase_request('PATCH', f'job_payments?id=eq.{payment_id}', json={
            'status': 'paid',
            'transaction_id': transaction_id,
            'paid_at': now,
        })

        # Опубликовать задание
        job_id = payment['job_id']
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'status': 'open',
            'is_paid': True,
            'paid_at': now,
            'expires_at': expires_at,
        })

        # Чек
        employer_resp = supabase_request('GET', f'profiles?id=eq.{employer_id}&select=full_name,inn')
        employer_data = employer_resp.json()[0] if employer_resp.ok and employer_resp.json() else {}
        ReceiptService.issue_job_publication_receipt(
            employer_name=employer_data.get('full_name', ''),
            employer_inn=employer_data.get('inn', ''),
            job_id=job_id,
            tariff=payment.get('tariff', 'standard'),
            amount=payment['amount'],
        )

        # Уведомление
        from app.services.notification_service import create as notify
        notify(employer_id, 'job_published', 'Задание опубликовано',
               'Задание опубликовано! Ожидайте откликов.',
               data={'job_id': job_id})

        return {'success': True, 'transaction_id': transaction_id}
