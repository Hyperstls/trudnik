"""Диагностический скрипт: сравнение JWT, генерируемых Flask vs вручную."""
import os, sys, json, time

# Установить переменные окружения ДО импорта app
os.environ['FLASK_APP'] = 'app:create_app'
os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'dev-secret-key-change-in-production-abc123'
os.environ['POSTGREST_URL'] = 'http://localhost:3000'
os.environ['PGRST_JWT_SECRET'] = '9671f571463b29d1b93339c75082974856af1f5d3cce302aaa76f449a50447a1106d1e496728324fc31a654866c7c842456ee4fa077c91841d3fb8ac7e8fb1f6'

sys.path.insert(0, '.')
from app import create_app
import jwt as pyjwt
import requests as req

app = create_app()

with app.app_context():
    from flask import current_app
    from app.utils.auth import generate_jwt
    from app.utils.postgrest_client import get_service_role_headers, get_user_headers, PGRST_JWT_SECRET as MODULE_PGRST_SECRET
    
    print("=" * 70)
    print("ИСТОЧНИКИ СЕКРЕТА")
    print("=" * 70)
    print(f"os.environ['PGRST_JWT_SECRET']   = {repr(os.environ['PGRST_JWT_SECRET'])[:60]}")
    print(f"os.environ['SECRET_KEY']          = {repr(os.environ['SECRET_KEY'])[:60]}")
    print(f"current_app.config['PGRST_JWT_SECRET'] = {repr(current_app.config.get('PGRST_JWT_SECRET'))[:60]}")
    print(f"current_app.config['SECRET_KEY']  = {repr(current_app.config.get('SECRET_KEY'))[:60]}")
    print(f"postgrest_client.PGRST_JWT_SECRET = {repr(MODULE_PGRST_SECRET)[:60]}")
    
    # Сравнить секреты побайтово
    s1 = (current_app.config.get('PGRST_JWT_SECRET') or '').encode('utf-8')
    s2 = os.environ.get('PGRST_JWT_SECRET', '').encode('utf-8')
    s3 = (current_app.config.get('SECRET_KEY') or '').encode('utf-8')
    print(f"\nPGRST_JWT_SECRET == SECRET_KEY? {s1 == s3}")
    print(f"config.PGRST == os.environ.PGRST? {s1 == s2}")
    
    print("\n" + "=" * 70)
    print("ГЕНЕРАЦИЯ JWT ЧЕРЕЗ auth.generate_jwt() (как для пользователя)")
    print("=" * 70)
    token = generate_jwt(user_id='test-user-id', role='trudnikapp')
    print(f"Token (первые 80): {token[:80]}...")
    
    # Декодировать без проверки подписи
    decoded = pyjwt.decode(token, options={"verify_signature": False})
    print(f"\nPayload:")
    for k, v in decoded.items():
        print(f"  {k}: {v!r} (type={type(v).__name__})")
    
    # Проверить типы iat/exp
    iat_val = decoded.get('iat')
    exp_val = decoded.get('exp')
    if isinstance(iat_val, (int, float)):
        print(f"\n[OK] iat - число (Unix timestamp): {iat_val}")
    else:
        print(f"\n[FAIL] iat - НЕ число! Тип: {type(iat_val).__name__}, значение: {iat_val!r}")
    if isinstance(exp_val, (int, float)):
        print(f"[OK] exp - число (Unix timestamp): {exp_val}")
    else:
        print(f"[FAIL] exp - НЕ число! Тип: {type(exp_val).__name__}, значение: {exp_val!r}")
    
    # Верификация с разными секретами
    print(f"\nВерификация с PGRST_JWT_SECRET:")
    try:
        pyjwt.decode(token, os.environ['PGRST_JWT_SECRET'], algorithms=['HS256'])
        print("  [OK] УСПЕШНО")
    except Exception as e:
        print(f"  [FAIL] ОШИБКА: {e}")
    
    print(f"Верификация с SECRET_KEY:")
    try:
        pyjwt.decode(token, os.environ['SECRET_KEY'], algorithms=['HS256'])
        print("  [OK] УСПЕШНО")
    except Exception as e:
        print(f"  [FAIL] ОШИБКА: {e}")
    
    print("\n" + "=" * 70)
    print("ГЕНЕРАЦИЯ JWT ЧЕРЕЗ get_service_role_headers() (работает)")
    print("=" * 70)
    svc_headers = get_service_role_headers()
    svc_token = svc_headers['Authorization'].replace('Bearer ', '')
    svc_decoded = pyjwt.decode(svc_token, options={"verify_signature": False})
    print(f"Payload:")
    for k, v in svc_decoded.items():
        print(f"  {k}: {v!r} (type={type(v).__name__})")
    
    print("\n" + "=" * 70)
    print("ГЕНЕРАЦИЯ JWT ЧЕРЕЗ get_user_headers() (вызывает 401)")
    print("=" * 70)
    # Эмулируем сессию Flask
    with app.test_request_context():
        from flask import session
        session['user_id'] = 'test-user-id'
        session['role'] = 'trudnikapp'
        uh_headers = get_user_headers()
        uh_token = uh_headers['Authorization'].replace('Bearer ', '')
        uh_decoded = pyjwt.decode(uh_token, options={"verify_signature": False})
        print(f"Payload:")
        for k, v in uh_decoded.items():
            print(f"  {k}: {v!r} (type={type(v).__name__})")
    
    print("\n" + "=" * 70)
    print("ЗАПРОСЫ К POSTGREST")
    print("=" * 70)
    
    def test_postgrest(label, headers):
        try:
            r = req.get('http://localhost:3000/users?limit=1', headers=headers, timeout=10)
            print(f"{label}: HTTP {r.status_code}")
            if r.status_code != 200:
                print(f"  Body: {r.text[:300]}")
                # Показать WWW-Authenticate если есть
                if 'WWW-Authenticate' in r.headers:
                    print(f"  WWW-Authenticate: {r.headers['WWW-Authenticate']}")
            return r.status_code
        except Exception as e:
            print(f"{label}: ОШИБКА соединения: {e}")
            return 0
    
    # 1. JWT от generate_jwt (datetime iat/exp)
    test_postgrest("JWT от generate_jwt()", {'Authorization': f'Bearer {token}'})
    
    # 2. JWT от get_service_role_headers (int iat/exp)
    test_postgrest("JWT от get_service_role_headers()", svc_headers)
    
    # 3. JWT от get_user_headers
    test_postgrest("JWT от get_user_headers()", uh_headers)
    
    # 4. Ручной JWT с int-таймстемпами (контроль)
    now = int(time.time())
    manual_token = pyjwt.encode(
        {'role': 'trudnikapp', 'iat': now, 'exp': now + 3600, 'jti': 'test-manual'},
        os.environ['PGRST_JWT_SECRET'],
        algorithm='HS256'
    )
    test_postgrest("Ручной JWT (int timestamps)", {'Authorization': f'Bearer {manual_token}'})
    
    # 5. Ручной JWT с datetime-таймстемпами (для сравнения)
    from datetime import datetime, timedelta
    dt_now = datetime.utcnow()
    manual_dt_token = pyjwt.encode(
        {'role': 'trudnikapp', 'iat': dt_now, 'exp': dt_now + timedelta(hours=1), 'jti': 'test-dt'},
        os.environ['PGRST_JWT_SECRET'],
        algorithm='HS256'
    )
    # Декодируем и смотрим что внутри
    dt_decoded = pyjwt.decode(manual_dt_token, options={"verify_signature": False})
    print(f"\nРучной JWT с datetime: iat={dt_decoded['iat']!r} (type={type(dt_decoded['iat']).__name__}), exp={dt_decoded['exp']!r} (type={type(dt_decoded['exp']).__name__})")
    test_postgrest("Ручной JWT (datetime timestamps)", {'Authorization': f'Bearer {manual_dt_token}'})
    
    print("\n" + "=" * 70)
    print("ДИАГНОЗ")
    print("=" * 70)
