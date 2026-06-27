"""
Финальный тест продакшена Trudnik
Использует requests для API проверок + куки из curl
"""
import requests
import re
import os

BASE_URL = "https://trudnik-hyperstls.amvera.io"
EMAIL = "admin@test.ru"
PASSWORD = "Step@1986"

results = []

def log(desc, status, detail=""):
    icon = "✅" if status else "❌"
    msg = f"{icon} {desc}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append({"desc": desc, "status": status, "detail": detail})

def main():
    session = requests.Session()
    
    print("\n" + "="*60)
    print("  ФИНАЛЬНЫЙ ТЕСТ ПРОДАКШЕНА TRUDNIK")
    print("="*60)
    
    # 1. Health check
    r = session.get(f"{BASE_URL}/health")
    log("Health check", r.ok, f"Status: {r.status_code}, Body: {r.text[:100]}")
    
    # 2. Получить страницу логина для CSRF токена
    r = session.get(f"{BASE_URL}/login")
    log("GET /login", r.ok, f"Status: {r.status_code}")
    
    csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', r.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    log("CSRF токен", bool(csrf_token), f"Токен: {csrf_token[:20]}..." if csrf_token else "None")
    
    # 3. Логин
    r = session.post(f"{BASE_URL}/login", data={
        "email": EMAIL,
        "password": PASSWORD,
        "_csrf_token": csrf_token
    }, headers={"X-CSRF-Token": csrf_token}, allow_redirects=True)
    log("POST /login (авторизация)", r.ok, f"Status: {r.status_code}, URL: {r.url}")
    
    # 4. Главная после логина
    r = session.get(f"{BASE_URL}/")
    log("GET / (после логина)", r.ok, f"Status: {r.status_code}, URL: {r.url}")
    
    # Проверка что не редиректнуло на login
    is_logged_in = "/login" not in r.url
    log("Авторизация активна", is_logged_in, f"URL: {r.url}")
    
    # 5. Админка
    r = session.get(f"{BASE_URL}/admin")
    log("GET /admin", r.ok, f"Status: {r.status_code}, URL: {r.url}")
    
    content = r.text
    
    # Проверки админки
    has_admin_panel = "Панель администратора" in content
    log("Панель администратора", has_admin_panel)
    
    has_version = "214f946" in content
    log("Версия (git hash 214f946)", has_version)
    
    has_skills = '?tab=skills' in content
    log("Вкладка Skills", has_skills)
    
    has_religions = '?tab=religions' in content
    log("Вкладка Religions", has_religions)
    
    has_logout = "Выйти" in content or "/logout" in content
    log("Кнопка выхода", has_logout)
    
    # 6. Skills вкладка
    r = session.get(f"{BASE_URL}/admin?tab=skills")
    log("GET /admin?tab=skills", r.ok, f"Status: {r.status_code}, Size: {len(r.text)} chars")
    
    # 7. Religions вкладка
    r = session.get(f"{BASE_URL}/admin?tab=religions")
    log("GET /admin?tab=religions", r.ok, f"Status: {r.status_code}, Size: {len(r.text)} chars")
    
    # 8. Выход
    r = session.get(f"{BASE_URL}/logout", allow_redirects=True)
    log("GET /logout", r.ok, f"Status: {r.status_code}, URL: {r.url}")
    
    # 9. Проверка выхода
    r = session.get(f"{BASE_URL}/")
    is_logged_out = "Войти" in r.text or "/login" in r.url
    log("Проверка выхода (кнопка Войти)", is_logged_out)
    
    # Итоги
    print("\n" + "="*60)
    print("  ИТОГОВАЯ СВОДКА")
    print("="*60)
    passed = sum(1 for r in results if r["status"])
    failed = sum(1 for r in results if not r["status"])
    for r in results:
        icon = "✅" if r["status"] else "❌"
        print(f"  {icon} {r['desc']}: {'OK' if r['status'] else 'FAIL'}")
        if r["detail"]:
            print(f"      → {r['detail']}")
    print(f"\n  Итого: {passed} пройдено, {failed} не пройдено")
    print("="*60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    exit(main())
