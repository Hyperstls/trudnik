"""Тесты для WebSocket-аутентификации — верификация JWT-токенов."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt

from websocket_server.auth import verify_token


class TestWebSocketAuth(unittest.TestCase):
    """Unit-тесты аутентификации WebSocket через JWT."""

    SECRET_KEY = 'test-secret-key-for-ws-auth-32bytes-minimum'

    @classmethod
    def setUpClass(cls) -> None:
        """Генерация тестовых токенов."""
        # Патчим SECRET_KEY в модуле auth для всех тестов
        cls._patcher = patch.object(
            __import__('websocket_server.auth', fromlist=['SECRET_KEY']),
            'SECRET_KEY',
            cls.SECRET_KEY,
        )
        cls._patcher.start()

        # Валидный токен
        cls.valid_token = jwt.encode(
            {'user_id': 42, 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            cls.SECRET_KEY,
            algorithm='HS256',
        )

        # Истёкший токен
        cls.expired_token = jwt.encode(
            {'user_id': 42, 'exp': datetime.now(timezone.utc) - timedelta(hours=1)},
            cls.SECRET_KEY,
            algorithm='HS256',
        )

        # Токен без user_id
        cls.token_without_uid = jwt.encode(
            {'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            cls.SECRET_KEY,
            algorithm='HS256',
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Останавливаем патчер."""
        cls._patcher.stop()

    # ────────────────────────────────────────────────────────────
    # Валидный токен
    # ────────────────────────────────────────────────────────────

    def test_verify_valid_token(self) -> None:
        """Валидный JWT-токен возвращает payload с user_id."""
        payload = verify_token(self.valid_token)

        self.assertIsNotNone(payload)
        self.assertIsInstance(payload, dict)
        self.assertIn('user_id', payload)
        self.assertEqual(payload['user_id'], 42)

    # ────────────────────────────────────────────────────────────
    # Истёкший токен
    # ────────────────────────────────────────────────────────────

    def test_verify_expired_token(self) -> None:
        """Истёкший JWT-токен возвращает None."""
        payload = verify_token(self.expired_token)

        self.assertIsNone(payload)

    # ────────────────────────────────────────────────────────────
    # Невалидный токен
    # ────────────────────────────────────────────────────────────

    def test_verify_invalid_token(self) -> None:
        """Невалидный JWT-токен (подделанный) возвращает None."""
        payload = verify_token('not.a.valid.jwt.token.string')

        self.assertIsNone(payload)

    def test_verify_token_wrong_signature(self) -> None:
        """JWT-токен с неверной подписью возвращает None."""
        wrong_token = jwt.encode(
            {'user_id': 42, 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            'wrong-secret-key-different-from-the-test-one',
            algorithm='HS256',
        )

        payload = verify_token(wrong_token)

        self.assertIsNone(payload)

    def test_verify_token_wrong_algorithm(self) -> None:
        """JWT-токен с другим алгоритмом (HS384) возвращает None."""
        wrong_algo_token = jwt.encode(
            {'user_id': 42, 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            self.SECRET_KEY,
            algorithm='HS384',
        )

        payload = verify_token(wrong_algo_token)

        self.assertIsNone(payload)

    # ────────────────────────────────────────────────────────────
    # Отсутствующий токен
    # ────────────────────────────────────────────────────────────

    def test_verify_missing_token(self) -> None:
        """Пустая строка как токен возвращает None."""
        payload = verify_token('')

        self.assertIsNone(payload)

    def test_verify_none_token(self) -> None:
        """None как токен возвращает None (не падает)."""
        payload = verify_token(None)  # type: ignore[arg-type]

        self.assertIsNone(payload)

    # ────────────────────────────────────────────────────────────
    # Токен без user_id
    # ────────────────────────────────────────────────────────────

    def test_verify_token_without_user_id(self) -> None:
        """JWT-токен без поля user_id возвращает None."""
        payload = verify_token(self.token_without_uid)

        self.assertIsNone(payload)


if __name__ == '__main__':
    unittest.main()
