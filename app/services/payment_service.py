"""
Сервис обработки платежей за раскрытие контакта.

Юридически значимое действие: фиксация платежа за информационную услугу.
Платформа не участвует в расчётах между храмом и исполнителем.
Платёж — только за раскрытие контакта (информационная услуга самозанятого).
"""

from datetime import datetime, timezone

from app.services.receipt_service import ReceiptService
from app.utils import supabase_request


class PaymentService:
    """Сервис для обработки платежей за раскрытие контакта исполнителя."""

    @staticmethod
    def get_settings():
        """Загрузить настройки монетизации из БД."""
        resp = supabase_request('GET', 'monetization_settings?select=key,value')
        if not resp.ok or not resp.json():
            return {'contact_price': 290, 'owner_inn': ''}

        settings = {}
        for item in resp.json():
            settings[item['key']] = item['value']

        try:
            contact_price = int(settings.get('contact_price', '290'))
        except (ValueError, TypeError):
            contact_price = 290

        return {
            'contact_price': contact_price,
            'owner_inn': settings.get('owner_inn', ''),
        }

    @staticmethod
    def process_contact_payment(payment: dict, church_name: str, church_inn: str):
        """
        Обработать платёж за раскрытие контакта.

        Здесь будет интеграция с Тинькофф.Платежи / CloudPayments / Сбер.
        Передаётся сумма, ИНН храма, идентификатор заказа.

        Args:
            payment: Объект contact_payments из БД (содержит id, application_id,
                     employer_id, worker_id, job_id, amount и др.)
            church_name: Название храма
            church_inn: ИНН храма

        Returns:
            dict: {success, transactionId}
        """
        payment_id = payment['id']
        application_id = payment['application_id']
        employer_id = payment['employer_id']
        worker_id = payment['worker_id']
        job_id = payment['job_id']
        amount = payment['amount']

        # Эмуляция вызова внешнего платёжного шлюза
        # В реальности: запрос к API эквайринга
        transaction_id = f"test_txn_{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        # Симулируем успешный ответ от платёжного шлюза
        payment_result = {
            'success': True,
            'transactionId': transaction_id,
        }

        # Юридически значимое действие: фиксация успешного платежа
        if payment_result['success']:
            now = datetime.now(timezone.utc).isoformat()

            # Обновить статус платежа
            supabase_request('PATCH', f'contact_payments?id=eq.{payment_id}', json={
                'status': 'paid',
                'transaction_id': transaction_id,
                'paid_at': now,
            })

            # Отметить отклик как оплаченный
            supabase_request('PATCH', f'applications?id=eq.{application_id}', json={
                'contact_paid': True,
                'contact_payment_id': payment_id,
            })

            # Юридически значимое действие: формирование чека самозанятого.
            # В будущем — интеграция с API ФНС (Мой налог).
            receipt_service = ReceiptService()
            receipt_service.issue_receipt(
                church_name=church_name,
                church_inn=church_inn,
                service_description=f"Предоставление контактной информации о соискателе №{worker_id[:8]}...",
                amount=amount,
                executor_id=employer_id,
                contact_payment_id=payment_id,
            )

        return payment_result

    @staticmethod
    def create_payment_intent(employer_id, worker_id, job_id, application_id):
        """
        Создать платёжное намерение (запись в contact_payments).

        Args:
            employer_id: ID работодателя
            worker_id: ID исполнителя
            job_id: ID задания
            application_id: ID отклика

        Returns:
            dict: {payment_id, amount} или None при ошибке
        """
        settings = PaymentService.get_settings()
        amount = settings.get('contact_price', 290)

        # Проверить, что платёж ещё не был сделан (защита от TOCTOU race condition)
        existing_resp = supabase_request(
            'GET',
            f'contact_payments?application_id=eq.{application_id}&status=eq.paid&select=id'
        )
        if existing_resp.ok and existing_resp.json():
            return None

        resp = supabase_request('POST', 'contact_payments', json={
            'employer_id': employer_id,
            'worker_id': worker_id,
            'job_id': job_id,
            'application_id': application_id,
            'amount': amount,
            'status': 'pending',
        })

        if resp.ok and resp.json():
            payment = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
            return {
                'payment_id': payment['id'],
                'amount': amount,
            }

        return None
