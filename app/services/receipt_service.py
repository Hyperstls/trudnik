"""
Сервис формирования чеков самозанятого (интеграция с API «Мой налог»).

Юридически значимое действие: формирование чека самозанятого.
В будущем — интеграция с API ФНС (Мой налог) через партнёрский сервис
(Сбер НПД, Платформа НПД). Требуется ИНН владельца платформы (самозанятого)
из конфигурации.
"""

import json
from datetime import datetime, timezone

from flask import current_app

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
        current_app.logger.info("[ЧЕК] Сформирован чек #%s", receipt_id[:8] if receipt_id else 'N/A')
        current_app.logger.info("[ЧЕК] Отправитель (самозанятый): ИНН %s", owner_inn)
        current_app.logger.info("[ЧЕК] Получатель: %s (ИНН %s)", church_name, church_inn)
        current_app.logger.info("[ЧЕК] Услуга: %s", service_description)
        current_app.logger.info("[ЧЕК] Сумма: %s руб.", amount)
        current_app.logger.info("[ЧЕК] JSON: %s", json.dumps(receipt_data, ensure_ascii=False, indent=2))

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
            current_app.logger.info("[ЧЕК] Чек #%s переотправлен", receipt_id[:8])
            return True

        return False

    @staticmethod
    def issue_job_publication_receipt(employer_name, employer_inn, job_id, tariff, amount):
        """
        Сформировать чек за публикацию задания.

        Args:
            employer_name: Название храма (заказчик)
            employer_inn: ИНН храма
            job_id: ID задания
            tariff: Ключ тарифа
            amount: Сумма (руб.)

        Returns:
            str: receipt_id или пустая строка
        """
        from app.services.payment_service import PaymentService
        settings = PaymentService.get_settings()
        owner_inn = settings.get('owner_inn', '')

        service_description = f"Публикация задания №{job_id[:8]}... на платформе Трудник (тариф {tariff})"

        receipt_data = {
            'receipt_type': 'income',
            'owner_inn': owner_inn,
            'client': {
                'name': employer_name,
                'inn': employer_inn,
                'type': 'legal_entity',
            },
            'services': [
                {
                    'name': service_description,
                    'amount': amount,
                    'quantity': 1,
                }
            ],
            'total_amount': amount,
            'taxation_type': 'npd',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        resp = supabase_request('POST', 'receipts', json={
            'church_name': employer_name,
            'church_inn': employer_inn,
            'service_description': service_description,
            'amount': amount,
            'status': 'sent',
            'receipt_json': receipt_data,
        })

        receipt_id = ''
        if resp.ok and resp.json():
            receipt_data_resp = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
            receipt_id = receipt_data_resp.get('id', '')

        current_app.logger.info("[ЧЕК] Сформирован чек за публикацию #%s", receipt_id[:8] if receipt_id else 'N/A')
        current_app.logger.info("[ЧЕК] Отправитель (самозанятый): ИНН %s", owner_inn)
        current_app.logger.info("[ЧЕК] Получатель: %s (ИНН %s)", employer_name, employer_inn)
        current_app.logger.info("[ЧЕК] Услуга: %s", service_description)
        current_app.logger.info("[ЧЕК] Сумма: %s руб.", amount)
        current_app.logger.info("[ЧЕК] JSON: %s", json.dumps(receipt_data, ensure_ascii=False, indent=2))

        return receipt_id
