import requests
import sys

BASE = 'http://127.0.0.1:5000'
session = requests.Session()

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f'  [OK] {name}')
        passed += 1
        return True
    except Exception as e:
        print(f'  [FAIL] {name}: {e}')
        failed += 1
        return False

# --- ТЕСТЫ ---

# 1. Главная страница доступна
def t1():
    r = session.get(f'{BASE}/')
    assert r.status_code == 200, f'status={r.status_code}'
test('Главная (200)', t1)

# 2. Страница логина
def t2():
    r = session.get(f'{BASE}/login')
    assert r.status_code == 200
test('Логин (GET 200)', t2)

# 3. Вход админа
def t3():
    r = session.post(f'{BASE}/login', data={'email': 'admin@trudnik.ru', 'password': 'test'}, allow_redirects=False)
    assert r.status_code == 302, f'status={r.status_code}'
    assert r.headers.get('Location') == '/', f'redirect={r.headers.get("Location")}'
test('Вход admin@trudnik.ru/test (302 -> /)', t3)

# 4. Админ-панель доступна
def t4():
    r = session.get(f'{BASE}/admin')
    assert r.status_code == 200
    assert 'Админ-панель' in r.text or 'admin' in r.text.lower()
test('Админ-панель (200)', t4)

# 5. Вкладки админки
for tab in ['dashboard', 'users', 'jobs', 'verification', 'dictionaries']:
    def make_test(tab=tab):
        def t():
            r = session.get(f'{BASE}/admin?tab={tab}')
            assert r.status_code == 200
        return t
    test(f'Админка tab={tab}', make_test())

# 6. Профиль
def t6():
    r = session.get(f'{BASE}/profile')
    assert r.status_code == 200
test('Профиль (200)', t6)

# 7. Выход
def t7():
    r = session.get(f'{BASE}/logout', allow_redirects=False)
    assert r.status_code == 302, f'status={r.status_code}'
test('Выход (302)', t7)

# 8. После выхода - админка недоступна
def t8():
    r = session.get(f'{BASE}/admin', allow_redirects=False)
    assert r.status_code == 302, f'status={r.status_code} (ожидался редирект)'
test('После выхода /admin -> 302', t8)

# 9. Повторный вход
def t9():
    r = session.post(f'{BASE}/login', data={'email': 'admin@trudnik.ru', 'password': 'test'}, allow_redirects=False)
    assert r.status_code == 302
test('Повторный вход (302)', t9)

# 10. Вход неверный
def t10():
    s2 = requests.Session()
    r = s2.post(f'{BASE}/login', data={'email': 'no@no.ru', 'password': 'wrong'}, allow_redirects=False)
    assert r.status_code == 200  # страница логина с ошибкой
    assert 'неверный' in r.text.lower() or 'ошибк' in r.text.lower() or 'не найден' in r.text.lower()
test('Неверный логин (200 + ошибка)', t10)

print(f'\n{"="*40}')
print(f'Пройдено: {passed}/{passed+failed}')
