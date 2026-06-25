"""Генерация криптостойкого JWT-секрета для локальной разработки.

Использование:
    python scripts/generate_jwt_secret.py

Сгенерированный ключ необходимо добавить в .env:
    PGRST_JWT_SECRET=<сгенерированный_ключ>

Требования:
    - Минимум 32 символа (рекомендация PostgREST)
    - Криптостойкая случайная последовательность
    - Одинаковое значение в PGRST_JWT_SECRET для postgrest и Flask
"""

import secrets


def generate_jwt_secret(byte_length: int = 64) -> str:
    """Генерирует случайный ключ в hex-формате.

    Args:
        byte_length: количество случайных байт (по умолчанию 64 → 128 hex-символов).

    Returns:
        Hex-строка длиной byte_length * 2.
    """
    return secrets.token_hex(byte_length)


if __name__ == "__main__":
    secret = generate_jwt_secret()
    print(f"PGRST_JWT_SECRET={secret}")
    print()
    print("Добавьте эту строку в ваш .env файл:")
    print(f"  PGRST_JWT_SECRET={secret}")
    print()
    print(f"Характеристики ключа:")
    print(f"  Длина: {len(secret)} символов")
    print(f"  Энтропия: {len(secret) * 4} бит")
    print(f"  Кодировка: hex (0-9, a-f)")
    print()
    print("!!! Этот ключ должен быть одинаковым в:")
    print("   - PGRST_JWT_SECRET для сервиса postgrest в docker-compose.yml")
    print("   - PGRST_JWT_SECRET для сервисов web / celery_worker / celery_beat")
    print("   - PGRST_JWT_SECRET в вашем .env файле")
