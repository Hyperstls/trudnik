"""Сервис платежей: YooKassa (или заглушка для режима разработки).

Конфигурация из env:
    YOOKASSA_SHOP_ID — ID магазина в YooKassa
    YOOKASSA_SECRET_KEY — секретный ключ API YooKassa

Если переменные не заданы — create_payment возвращает заглушку для режима разработки.
"""

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone

from app.utils import postgrest_admin_request

logger = logging.getLogger(__name__)

YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', '')


class PaymentService:
    """Сервис для работы с YooKassa API."""

    @staticmethod
    def is_configured() -> bool:
        """Проверить, настроена ли YooKassa."""
        return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)

    @staticmethod
    def create_payment(
        amount: float,
        currency: str = 'RUB',
        description: str = '',
        return_url: str = '',
    ) -> dict:
        """Создать платёж через YooKassa API.

        Args:
            amount: сумма платежа в рублях.
            currency: валюта (по умолчанию RUB).
            description: описание платежа.
            return_url: URL для возврата после оплаты.

        Returns:
            dict с ключами: success (bool), payment_id (str), confirmation_url (str),
            или заглушку для режима разработки.
        """
        if not PaymentService.is_configured():
            # Заглушка для режима разработки
            mock_payment_id = f'mock_{uuid.uuid4().hex[:12]}'
            logger.warning(
                'YooKassa not configured — returning mock payment: id=%s amount=%.2f %s',
                mock_payment_id, amount, currency
            )
            return {
                'success': True,
                'payment_id': mock_payment_id,
                'confirmation_url': f'{return_url}?mock_payment_id={mock_payment_id}' if return_url else '',
                'status': 'pending',
                'mock': True,
            }

        try:
            import requests

            idempotency_key = uuid.uuid4().hex
            payload = {
                'amount': {
                    'value': f'{amount:.2f}',
                    'currency': currency,
                },
                'capture': True,
                'description': description or 'Оплата задания на Trudnik',
                'confirmation': {
                    'type': 'redirect',
                    'return_url': return_url,
                },
            }

            response = requests.post(
                'https://api.yookassa.ru/v3/payments',
                json=payload,
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                headers={
                    'Idempotence-Key': idempotency_key,
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )

            if response.status_code in (200, 201):
                data = response.json()
                payment_id = data.get('id', '')
                confirmation_url = (
                    data.get('confirmation', {}).get('confirmation_url', '')
                )
                logger.info(
                    'YooKassa payment created: id=%s amount=%.2f %s status=%s',
                    payment_id, amount, currency, data.get('status', 'unknown')
                )
                return {
                    'success': True,
                    'payment_id': payment_id,
                    'confirmation_url': confirmation_url,
                    'status': data.get('status', 'pending'),
                    'mock': False,
                }
            else:
                logger.error(
                    'YooKassa payment creation failed: status=%s body=%s',
                    response.status_code, response.text
                )
                return {
                    'success': False,
                    'error': f'YooKassa API error: {response.status_code}',
                    'details': response.text[:500],
                }

        except ImportError:
            logger.error('requests library not installed — cannot call YooKassa API')
            return {
                'success': False,
                'error': 'Библиотека requests не установлена',
            }
        except Exception as e:
            logger.error('YooKassa payment creation exception: %s', e)
            return {
                'success': False,
                'error': str(e),
            }

    @staticmethod
    def verify_webhook(data: bytes, signature: str) -> bool:
        """Проверить подлинность webhook-уведомления от YooKassa.

        Args:
            data: тело запроса (bytes).
            signature: заголовок X-YooKassa-Signature.

        Returns:
            True если подпись верна.
        """
        if not PaymentService.is_configured():
            if os.environ.get('DEPLOYMENT_ENV', '') == 'production':
                raise RuntimeError("YooKassa not configured for production")
            # В режиме разработки всегда возвращаем True для заглушек
            logger.debug('YooKassa not configured — webhook verification skipped')
            return True

        if not signature:
            logger.warning('YooKassa webhook: missing X-YooKassa-Signature header')
            return False

        try:
            expected = hmac.new(
                YOOKASSA_SECRET_KEY.encode('utf-8'),
                data,
                hashlib.sha256,
            ).hexdigest()

            # Constant-time comparison для предотвращения timing attacks
            return hmac.compare_digest(expected, signature)
        except Exception as e:
            logger.error('YooKassa webhook verification error: %s', e)
            return False

    @staticmethod
    def process_payment(payment_id: str, status: str) -> bool:
        """Обновить статус платежа в БД.

        Args:
            payment_id: ID платежа в YooKassa.
            status: новый статус (succeeded, canceled).

        Returns:
            True если статус обновлён.
        """
        if not PaymentService.is_configured():
            logger.warning(
                'YooKassa not configured — mock payment %s processed with status %s',
                payment_id, status
            )
            return True

        try:
            updated_at = datetime.now(timezone.utc).isoformat()
            resp = postgrest_admin_request(
                'PATCH',
                f'job_payments?payment_id=eq.{payment_id}',
                json={
                    'status': status,
                    'updated_at': updated_at,
                }
            )
            if resp.ok:
                logger.info(
                    'Payment %s status updated to %s', payment_id, status
                )
                return True
            else:
                logger.error(
                    'Failed to update payment %s: status=%s body=%s',
                    payment_id, resp.status_code, resp.text
                )
                return False
        except Exception as e:
            logger.error(
                'Exception updating payment %s: %s', payment_id, e
            )
            return False


# Глобальный экземпляр для удобного импорта
payment_service = PaymentService()
