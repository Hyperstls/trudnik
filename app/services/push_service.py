"""Сервис Push-уведомлений (Web Push API) для Trudnik.

Использует pywebpush для отправки push-уведомлений через браузерный Push API.
Работает с Supabase REST API для хранения подписок (таблица push_subscriptions).

VAPID-ключи генерируются администратором и задаются через переменные окружения.

БЕЗОПАСНОСТЬ (service_role):
    Все операции с таблицей push_subscriptions используют postgrest_admin_request
    (service_role) по двум причинам:
    1. RLS-политика push_subscriptions имеет SELECT/INSERT/DELETE для auth.uid(),
       но НЕ имеет UPDATE-политики. Метод save_subscription() делает PATCH при
       обновлении существующей подписки, что требует service_role.
    2. PushService вызывается из Celery-задач (push_tasks.py), где нет сессии
       пользователя — service_role необходим для фоновых операций.

    TODO (безопасность): Добавить RLS UPDATE-политику для push_subscriptions:
        CREATE POLICY "Users can update own push subscriptions"
            ON push_subscriptions FOR UPDATE
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    После этого:
    - save_subscription() сможет использовать postgrest_request с токеном пользователя
      при вызове из Flask-контекста.
    - get_user_subscriptions() (SELECT) и delete_subscription() (DELETE) уже сейчас
      могут работать через postgrest_request, но требуют рефакторинга для разделения
      контекстов (Flask vs Celery).
"""

import base64
import logging
import os
import time as _time_module
import urllib.parse
from typing import Optional

from app.utils.postgrest_client import postgrest_admin_request as postgrest_admin_request

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# PushService
# ═══════════════════════════════════════════════════════════════


class PushService:
    """Сервис для отправки Web Push уведомлений через pywebpush."""

    def __init__(self,
                 vapid_private_key: Optional[str] = None,
                 vapid_public_key: Optional[str] = None,
                 vapid_claims_email: Optional[str] = None,
                 vapid_claims_subject: Optional[str] = None) -> None:
        """Инициализация сервиса с VAPID-ключами (по умолчанию из переменных окружения)."""
        self.vapid_private_key: str = vapid_private_key if vapid_private_key is not None else os.environ.get('VAPID_PRIVATE_KEY', '')
        self.vapid_public_key: str = vapid_public_key if vapid_public_key is not None else os.environ.get('VAPID_PUBLIC_KEY', '')
        self.vapid_claims_email: str = vapid_claims_email if vapid_claims_email is not None else os.environ.get(
            'VAPID_CLAIMS_EMAIL', 'notifications@trudnik.ru'
        )
        self.vapid_claims_subject: str = vapid_claims_subject if vapid_claims_subject is not None else os.environ.get(
            'VAPID_CLAIMS_SUBJECT', 'mailto:notifications@trudnik.ru'
        )

        if not self.vapid_private_key:
            logger.warning(
                'VAPID_PRIVATE_KEY не задан в переменных окружения. '
                'Push-уведомления не будут работать.'
            )
        if not self.vapid_public_key:
            logger.warning(
                'VAPID_PUBLIC_KEY не задан в переменных окружения. '
                'Push-уведомления не будут работать.'
            )

    # ────────────────────────────────────────────────────────────
    # Утилита генерации VAPID-ключей
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def generate_vapid_keys() -> tuple:
        """Генерирует пару VAPID-ключей для Web Push.

        Использует криптографию на эллиптических кривых (P-256 / SECP256R1).

        Returns:
            Кортеж (private_key, public_key) в base64url-кодировке без padding.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            logger.error(
                'cryptography не установлен. Установите: pip install cryptography'
            )
            raise

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        # Экспорт в raw-формат (32 байта для private, 64 байта для public)
        private_raw = private_key.private_numbers().private_value.to_bytes(32, 'big')

        pub_numbers = public_key.public_numbers()
        public_raw = (
            pub_numbers.x.to_bytes(32, 'big') +
            pub_numbers.y.to_bytes(32, 'big')
        )

        # Кодирование в base64url без padding
        private_b64 = base64.urlsafe_b64encode(private_raw).rstrip(b'=').decode('ascii')
        public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b'=').decode('ascii')

        return private_b64, public_b64

    # ────────────────────────────────────────────────────────────
    # Отправка push-уведомления одной подписке
    # ────────────────────────────────────────────────────────────

    def send_notification(
        self, subscription_info: dict, payload: dict
    ) -> dict:
        """Отправляет push-уведомление на одну подписку.

        Args:
            subscription_info: словарь с ключами endpoint, p256dh, auth.
            payload: данные уведомления (заголовок, текст, ссылка и т.д.).

        Returns:
            Словарь с результатом:
                {'success': bool, 'error': str|None, 'should_unsubscribe': bool}
        """
        if not self.vapid_private_key or not self.vapid_public_key:
            return {
                'success': False,
                'error': 'VAPID-ключи не настроены на сервере',
                'should_unsubscribe': False,
            }

        try:
            from pywebpush import WebPusher, WebPushException
        except ImportError:
            logger.error('pywebpush не установлен. Установите: pip install pywebpush')
            return {
                'success': False,
                'error': 'pywebpush не установлен',
                'should_unsubscribe': False,
            }

        try:
            subscription_data = {
                'endpoint': subscription_info['endpoint'],
                'keys': {
                    'p256dh': subscription_info['p256dh'],
                    'auth': subscription_info['auth'],
                },
            }

            WebPusher(subscription_data).send(
                data=payload,
                vapid_private_key=self.vapid_private_key,
                vapid_claims={
                    'sub': self.vapid_claims_subject,
                    'aud': subscription_info['endpoint'],
                    'exp': int(_time_module.time() + 86400),
                },
            )

            return {'success': True, 'error': None, 'should_unsubscribe': False}

        except WebPushException as e:
            logger.error('WebPushException при отправке: %s (код: %s)', e, getattr(e, 'response', None))

            if hasattr(e, 'response') and e.response is not None:
                status_code = (
                    e.response.status_code
                    if hasattr(e.response, 'status_code')
                    else None
                )

                # 410 Gone — подписка невалидна, нужно удалить
                if status_code == 410:
                    return {
                        'success': False,
                        'error': 'Подписка недействительна (410 Gone)',
                        'should_unsubscribe': True,
                    }

                # 400/401 — вероятно истекла или неверный ключ
                if status_code in (400, 401):
                    return {
                        'success': False,
                        'error': f'Подписка истекла или недействительна ({status_code})',
                        'should_unsubscribe': True,
                    }

            return {
                'success': False,
                'error': str(e),
                'should_unsubscribe': False,
            }

        except Exception as e:
            logger.error('Неизвестная ошибка при отправке push: %s', e)
            return {
                'success': False,
                'error': str(e),
                'should_unsubscribe': False,
            }

    # ────────────────────────────────────────────────────────────
    # Отправка push-уведомления всем подпискам пользователя
    # ────────────────────────────────────────────────────────────

    def send_to_user(self, user_id: str, payload: dict) -> list:
        """Отправляет push-уведомление на все подписки пользователя.

        Невалидные подписки автоматически удаляются из БД.

        Args:
            user_id: UUID пользователя.
            payload: данные уведомления для отправки.

        Returns:
            Список словарей с результатами отправки для каждой подписки.
        """
        subscriptions = self.get_user_subscriptions(user_id)
        results = []

        for sub in subscriptions:
            result = self.send_notification(sub, payload)
            result['endpoint'] = sub.get('endpoint', '')
            results.append(result)

            # Удаляем невалидные подписки
            if result.get('should_unsubscribe'):
                self.delete_subscription(sub.get('endpoint', ''), user_id=user_id)
                logger.info(
                    'Удалена невалидная подписка: user=%s endpoint=%s',
                    user_id, sub.get('endpoint', '')[:50]
                )

        return results

    # ────────────────────────────────────────────────────────────
    # Работа с БД (Supabase REST API)
    # ────────────────────────────────────────────────────────────

    def save_subscription(self, user_id: str, subscription_data: dict) -> bool:
        """Сохраняет новую push-подписку пользователя в БД.

        Args:
            user_id: UUID пользователя.
            subscription_data: данные подписки (endpoint, keys.p256dh, keys.auth).

        Returns:
            True если успешно сохранено, иначе False.
        """
        endpoint = subscription_data.get('endpoint', '')
        if not endpoint:
            logger.error('save_subscription: отсутствует endpoint')
            return False

        # Извлекаем ключи (могут быть вложены в keys или на верхнем уровне)
        keys = subscription_data.get('keys', {})
        p256dh = keys.get('p256dh', '') or subscription_data.get('p256dh', '')
        auth = keys.get('auth', '') or subscription_data.get('auth', '')

        payload = {
            'user_id': user_id,
            'endpoint': endpoint,
            'p256dh': p256dh,
            'auth': auth,
        }

        # Проверяем, существует ли уже такая подписка (по endpoint)
        check = postgrest_admin_request(
            'GET',
            f'push_subscriptions?endpoint=eq.{_encode_uri_component(endpoint)}&select=id'
        )
        if check.ok and check.json():
            # Обновляем существующую
            sub_id = check.json()[0]['id']
            resp = postgrest_admin_request(
                'PATCH',
                f'push_subscriptions?id=eq.{sub_id}',
                json=payload
            )
            return resp.ok

        # Создаём новую
        resp = postgrest_admin_request('POST', 'push_subscriptions', json=payload)
        if not resp.ok:
            logger.error(
                'Ошибка сохранения подписки: status=%s body=%s',
                resp.status_code, resp.text
            )
            return False
        return True

    def get_user_subscriptions(self, user_id: str) -> list:
        """Получает все активные push-подписки пользователя.

        Args:
            user_id: UUID пользователя.

        Returns:
            Список словарей с ключами endpoint, p256dh, auth.
        """
        resp = postgrest_admin_request(
            'GET',
            f'push_subscriptions?user_id=eq.{user_id}&select=endpoint,p256dh,auth'
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else []
        logger.error(
            'Ошибка получения подписок: status=%s body=%s',
            resp.status_code, resp.text
        )
        return []

    def delete_subscription(self, endpoint: str, user_id: str = "") -> bool:
        """Удаляет push-подписку по endpoint с проверкой принадлежности пользователю.

        Args:
            endpoint: URL эндпоинта подписки.
            user_id: UUID пользователя (опционально). Если передан — удаление
                     только если подписка принадлежит этому пользователю.

        Returns:
            True если успешно удалено, иначе False.
        """
        if not endpoint:
            return False
        url = f'push_subscriptions?endpoint=eq.{_encode_uri_component(endpoint)}'
        if user_id:
            url += f'&user_id=eq.{user_id}'
        resp = postgrest_admin_request('DELETE', url)
        return resp.ok

    def delete_all_user_subscriptions(self, user_id: str) -> bool:
        """Удаляет все push-подписки пользователя.

        Args:
            user_id: UUID пользователя.

        Returns:
            True если успешно удалено, иначе False.
        """
        resp = postgrest_admin_request(
            'DELETE',
            f'push_subscriptions?user_id=eq.{user_id}'
        )
        if not resp.ok:
            logger.error(
                'Ошибка удаления всех подписок: status=%s body=%s',
                resp.status_code, resp.text
            )
            return False
        return True

    def get_all_subscriptions(self, limit: int = 100, offset: int = 0) -> list:
        """Получает страницу подписок с пагинацией (для периодической очистки).

        Args:
            limit: Максимальное количество подписок на странице (по умолчанию 100).
            offset: Смещение для пагинации (по умолчанию 0).

        Returns:
            Список подписок с полями id, user_id, endpoint, p256dh, auth.
        """
        resp = postgrest_admin_request(
            'GET',
            f'push_subscriptions?select=id,user_id,endpoint,p256dh,auth&limit={limit}&offset={offset}'
        )
        if resp.ok:
            data = resp.json()
            return data if isinstance(data, list) else []
        return []


# ═══════════════════════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════════════════════


def _encode_uri_component(value: str) -> str:
    """Кодирует строку для безопасной передачи в URL PostgREST.

    Заменяет специальные символы на %-коды, используя ограниченный набор
    (совместимо с форматом фильтрации PostgREST eq.{value}).

    Args:
        value: исходная строка.

    Returns:
        Закодированная строка.
    """
    # PostgREST использует декодирование URL, но endpoint содержит спецсимволы
    # Кодируем полный endpoint для безопасной вставки в URL
    encoded = urllib.parse.quote(value, safe='')
    return encoded
