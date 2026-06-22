"""Генерирует PGRST_JWT_SECRET и выводит инструкцию по установке."""
import secrets
import hashlib


def generate_secret(length=64):
    """Генерирует криптографически безопасный секрет."""
    return secrets.token_hex(length // 2)


if __name__ == '__main__':
    secret = generate_secret()
    print("=" * 70)
    print("НОВЫЙ PGRST_JWT_SECRET (сохраните его!):")
    print("=" * 70)
    print(secret)
    print()
    print("=" * 70)
    print("ГДЕ УСТАНОВИТЬ:")
    print("=" * 70)
    print()
    print("1. В .env файле (локальная разработка):")
    print(f"   PGRST_JWT_SECRET={secret}")
    print()
    print("2. В amvera.yml (секреты приложения trudnik-app):")
    print("   secrets:")
    print("     - name: PGRST_JWT_SECRET")
    print(f"       value: {secret}")
    print()
    print("3. В панели Amvera -> Сервис trudnik-pr (PostgREST):")
    print("   Переменная окружения: PGRST_JWT_SECRET")
    print(f"   Значение: {secret}")
    print()
    print("4. В панели Amvera -> Сервис trudnik-celery (если есть):")
    print("   Переменная окружения: PGRST_JWT_SECRET")
    print(f"   Значение: {secret}")
