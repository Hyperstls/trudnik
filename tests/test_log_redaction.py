"""T22 — JWT secret prefix must NOT leak into logs (regression test).

Раньше generate_jwt логировал secret[:8] на INFO при каждом подписании
(каждый PostgREST-запрос), а config.py — PGRST_JWT_SECRET[:16] на DEBUG.
Любой доступ к логам раскрывал префикс секрета.
"""
import logging
import os


def test_generate_jwt_does_not_log_secret_prefix(app_context, caplog):
    """В логах не должно быть ни префикса секрета, ни старой строки утечки."""
    caplog.set_level(logging.DEBUG)
    from app.utils.auth import generate_jwt

    token = generate_jwt(user_id='log-test-user', role='worker', exp_seconds=3600)
    assert token, 'JWT должен создаваться'

    combined = '\n'.join(f'{r.name}: {r.getMessage()}' for r in caplog.records)

    # Старая утечка-строка убрана
    assert 'signing with secret prefix' not in combined
    assert 'secret prefix=%' not in combined

    # Сам префикс секрета не фигурирует нигде в логах
    secret = os.environ.get('PGRST_JWT_SECRET', '')
    if secret:
        assert secret[:8] not in combined, f'secret prefix leaked in logs:\n{combined}'
        assert secret[:16] not in combined
