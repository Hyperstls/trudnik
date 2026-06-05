"""
Сервис формирования чеков самозанятого (интеграция с API «Мой налог»).

Юридически значимое действие: формирование чека самозанятого.
В будущем — интеграция с API ФНС (Мой налог) через партнёрский сервис
(Сбер НПД, Платформа НПД). Требуется ИНН владельца платформы (самозанятого)
из конфигурации.
"""

import json
from datetime import datetime, timezone

from app.utils import supabase_request


class ReceiptService:
    """Сервис для формирования и отправки чеков самозанятого."""

    @staticmethod
    def issue_receipt(church_name, church_inn, service_description, amount, executor_id, contact_payment_id):
        """
        Сформировать и сохранить чек самозанятого.

        В текущей версии — логирование и сохранение в БД.
        Продакшн: отправка в API «Мой налог» через партнёрский сервис
        (Сбер НПД, Платформа НПД).

        Args:
            church_name: Название храма (заказчик)
            church_inn: ИНН храма
            service_description: Описание услуги
            amount: Сумма (руб.)
            executor_id: ID владельца платформы (самозанятого)
            contact_payment_id: ID платежа за контакт
        """
        # Получить ИНН владельца платформы из настроек
        from app.services.payment_service import PaymentService
        settings = PaymentService.get_settings()
        owner_inn = settings.get('owner_inn', '')

        # Сформировать JSON-объект чека
        # Соответствует требованиям API «Мой налог» (ФНС)
        receipt_data = {
            'receipt_type': 'income',  # чек на доход
            'owner_inn': owner_inn,
            'client': {
                'name': church_name,
                'inn': church_inn,
                'type': 'legal_entity',  # юрлицо/ИП
            },
            'services': [
                {
                    'name': service_description,
                    'amount': amount,
                    'quantity': 1,
                }
            ],
            'total_amount': amount,
            'taxation_type': 'npd',  # налог на профессиональный доход
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        # Юридически значимое действие: сохранение чека в истории
        resp = supabase_request('POST', 'receipts', json={
            'contact_payment_id': contact_payment_id,
            'church_name': church_name,
            'church_inn': church_inn,
            'service_description': service_description,
            'amount': amount,
            'status': 'sent',
            'receipt_json': receipt_data,
        })

        receipt_id = ''
        if resp.ok and resp.json():
            receipt_data_resp = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
            receipt_id = receipt_data_resp.get('id', '')

        # Логирование (заглушка отправки в ФНС)
        print(f"[ЧЕК] Сформирован чек #{receipt_id[:8] if receipt_id else 'N/A'}")
        print(f"[ЧЕК] Отправитель (самозанятый): ИНН {owner_inn}")
        print(f"[ЧЕК] Получатель: {church_name} (ИНН {church_inn})")
        print(f"[ЧЕК] Услуга: {service_description}")
        print(f"[ЧЕК] Сумма: {amount} руб.")
        print(f"[ЧЕК] JSON: {json.dumps(receipt_data, ensure_ascii=False, indent=2)}")

        return receipt_id

    @staticmethod
    def resend_receipt(receipt_id):
        """
        Переотправка чека администратором.

        Args:
            receipt_id: ID записи чека

        Returns:
            bool: успех операции
        """
        now = datetime.now(timezone.utc).isoformat()

        resp = supabase_request('PATCH', f'receipts?id=eq.{receipt_id}', json={
            'status': 'resent',
            'resent_at': now,
        })

        if resp.ok:
            print(f"[ЧЕК] Чек #{receipt_id[:8]} переотправлен")
            return True

        return False
