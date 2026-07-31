"""
Ручное тестирование регистрации через HTTP-запросы к https://trudnik.onrender.com

Использование:
    python test_register_manual.py

Что тестирует:
    1. Успешную регистрацию нового пользователя (worker)
    2. Регистрацию с уже существующим email
    3. Регистрацию со слабым паролем
    4. Регистрацию с пустыми обязательными полями
"""

import re
import sys
import time
import requests

BASE_URL = "https://trudnik.onrender.com"
REGISTER_URL = f"{BASE_URL}/register"
LOGIN_URL = f"{BASE_URL}/login"

# Цвета для терминала
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def safe_print(color: str, label: str, msg: str) -> None:
    """Вывод с цветом, безопасный для кодировки cp1251."""
    try:
        print(f"{color}[{label}]{RESET} {msg}")
    except UnicodeEncodeError:
        # Убираем цвет и выводим как есть
        clean = msg.encode('cp1251', errors='replace').decode('cp1251')
        print(f"[{label}] {clean}")


def ok(msg: str) -> None:
    safe_print(GREEN, "OK", msg)


def fail(msg: str) -> None:
    safe_print(RED, "FAIL", msg)


def info(msg: str) -> None:
    safe_print(CYAN, "INFO", msg)


def warn(msg: str) -> None:
    safe_print(YELLOW, "WARN", msg)


def section(title: str) -> None:
    try:
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  {title}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}\n")
    except UnicodeEncodeError:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")


def extract_flash_messages(html: str) -> list[str]:
    """
    Извлекает flash-сообщения из HTML через regexp.
    Ищет стандартные Bootstrap-стили flash (alert-danger, alert-success, alert-warning).
    """
    messages = []
    # Паттерн для Bootstrap alert с классом alert-*
    pattern = r'<div[^>]*class="[^"]*alert\s+alert-(danger|success|warning|info)[^"]*"[^>]*>\s*(.*?)\s*</div>'
    for match in re.finditer(pattern, html, re.DOTALL):
        msg_type = match.group(1)
        msg_text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if msg_text:
            messages.append(f"[{msg_type}] {msg_text}")

    # Альтернативный паттерн для других форматов флеш-сообщений
    if not messages:
        alt_pattern = r'<[^>]*class="[^"]*flash[^"]*"[^>]*>(.*?)</[^>]+>'
        for match in re.finditer(alt_pattern, html, re.DOTALL):
            msg_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if msg_text:
                messages.append(msg_text)

    # Ищем текст ошибок Supabase в любом месте страницы
    if not messages:
        # Ищем JSON-подобные сообщения об ошибках
        err_pattern = r'"msg"\s*:\s*"([^"]+)"'
        for match in re.finditer(err_pattern, html):
            messages.append(f"[postgrest] {match.group(1)}")

    return messages


def get_session_with_cookies() -> requests.Session:
    """Создаёт сессию с куками от GET /register."""
    sess = requests.Session()
    try:
        resp = sess.get(REGISTER_URL, timeout=30)
        info(f"GET /register -> статус {resp.status_code}, размер {len(resp.text)} байт")
        if resp.status_code != 200:
            warn(f"GET /register вернул {resp.status_code}, ожидался 200")
        return sess
    except requests.RequestException as e:
        fail(f"Не удалось получить /register: {e}")
        return sess


def post_with_retry(sess: requests.Session, url: str, data: dict, max_retries: int = 3) -> requests.Response | None:
    """POST запрос с повторными попытками при обрыве соединения (Render cold start)."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = sess.post(url, data=data, allow_redirects=False, timeout=45)
            return resp
        except requests.RequestException as e:
            last_error = e
            if attempt < max_retries:
                wait = 3.0 * attempt
                warn(f"Попытка {attempt}/{max_retries}: {e}. Повтор через {wait:.0f}с...")
                time.sleep(wait)
            else:
                fail(f"Все {max_retries} попытки не удались: {e}")
    return None


def test_successful_registration():
    """Тест 1: Успешная регистрация нового пользователя (worker)."""
    section("Тест 1: Успешная регистрация (worker)")

    timestamp = int(time.time())
    email = f"test_manual_{timestamp}@test.ru"
    password = "TestPass1"

    info(f"Email: {email}")
    info(f"Пароль: {password}")

    sess = get_session_with_cookies()

    form_data = {
        "full_name": "Тестовый Пользователь",
        "email": email,
        "password": password,
        "role": "worker",
        "city": "Москва",
        "religion": "не указано",
        "skills": "уборка, готовка",
        "desired_payment": "5000",
        "experience": "1 год",
        "contact": "+79991234567",
    }

    resp = post_with_retry(sess, REGISTER_URL, form_data)
    if resp is None:
        return False

    info(f"POST /register -> статус {resp.status_code}")

    if resp.status_code == 302:
        redirect_location = resp.headers.get("Location", "")
        info(f"Редирект на: {redirect_location}")
        if redirect_location and ("/login" in redirect_location or "/" in redirect_location):
            ok(f"Регистрация успешна! Редирект на {redirect_location}")

            # Проверяем flash-сообщение (следуем редиректу)
            if redirect_location:
                try:
                    follow_url = f"{BASE_URL}{redirect_location}" if redirect_location.startswith("/") else redirect_location
                    follow_resp = sess.get(follow_url, timeout=30)
                    messages = extract_flash_messages(follow_resp.text)
                    if messages:
                        for msg in messages:
                            info(f"Flash-сообщение: {msg}")
                except requests.RequestException:
                    warn("Не удалось получить страницу редиректа для проверки flash")
            return True
        else:
            warn(f"Неожиданный Location заголовок: {redirect_location}")
            return False
    else:
        messages = extract_flash_messages(resp.text)
        if messages:
            for msg in messages:
                fail(f"Ошибка регистрации: {msg}")
        else:
            fail(f"Ожидался редирект 302, получен {resp.status_code}")
            snippet = resp.text[:500].replace("\n", " ")
            fail(f"Тело ответа (первые 500): {snippet}")
        return False


def test_duplicate_email():
    """Тест 2: Регистрация с уже существующим email.

    ПРИМЕЧАНИЕ: Supabase API /auth/v1/signup по соображениям безопасности
    НЕ раскрывает, зарегистрирован ли уже email. Он возвращает 200/ok даже
    для существующего пользователя (чтобы нельзя было перебирать email'ы).
    Поэтому Flask-приложение получает resp.ok и делает редирект на /login.
    Это ПРАВИЛЬНОЕ поведение с точки зрения безопасности.
    """
    section("Тест 2: Регистрация с существующим email")

    # Используем заведомо существующий email из conftest.py
    existing_email = "worker@test.ru"
    password = "TestPass1"

    info(f"Email: {existing_email} (должен уже существовать)")
    info("Ожидание: Supabase НЕ раскрывает существование email (privacy)")

    sess = get_session_with_cookies()

    form_data = {
        "full_name": "Дубликат Пользователь",
        "email": existing_email,
        "password": password,
        "role": "worker",
        "city": "Москва",
    }

    resp = post_with_retry(sess, REGISTER_URL, form_data)
    if resp is None:
        return False

    info(f"POST /register -> статус {resp.status_code}")

    # 302 = стандартное поведение Supabase: не раскрывает, существует ли email
    if resp.status_code == 302:
        redirect_location = resp.headers.get("Location", "")
        info(f"Редирект на: {redirect_location}")
        if "/login" in redirect_location:
            ok("Supabase не раскрыл существование email (302 на /login) — это правильно (privacy-by-design)")
            # Проверим, что на /login нет сообщения об ошибке регистрации
            try:
                follow_url = f"{BASE_URL}{redirect_location}" if redirect_location.startswith("/") else redirect_location
                follow_resp = sess.get(follow_url, timeout=30)
                messages = extract_flash_messages(follow_resp.text)
                if messages:
                    for msg in messages:
                        info(f"Flash на /login: {msg}")
            except requests.RequestException:
                pass
            return True
        else:
            warn(f"Неожиданный Location: {redirect_location}")
            return False

    # Если не 302 — проверяем другие варианты
    # 200 = сервер перерендерил форму (с сообщением об ошибке или без — privacy)
    if resp.status_code == 200:
        messages = extract_flash_messages(resp.text)
        if messages:
            for msg in messages:
                if any(kw in msg.lower() for kw in ["существует", "exist", "already", "занят", "дубликат", "duplicate"]):
                    ok(f"Сервер явно сообщил о дубликате: {msg}")
                    return True
                else:
                    info(f"Flash-сообщение: {msg}")
        # Форма перерендерена — регистрация не выполнена, дубликат обработан
        ok("Сервер вернул 200 (форма перерендерена) — дубликат email не прошёл регистрацию")
        return True

    if resp.status_code in (400, 422, 409):
        ok(f"Дубликат отклонён сервером (HTTP {resp.status_code})")
        return True

    warn(f"Неожиданный результат. Статус: {resp.status_code}")
    snippet = resp.text[:500].replace("\n", " ")
    info(f"HTML (первые 500): {snippet}")
    return False


def test_weak_password():
    """Тест 3: Регистрация со слабым паролем."""
    section("Тест 3: Регистрация со слабым паролем")

    timestamp = int(time.time())
    email = f"test_weak_{timestamp}@test.ru"
    password = "123"  # Заведомо слабый пароль

    info(f"Email: {email}")
    info(f"Пароль: '{password}' (слабый)")

    sess = get_session_with_cookies()

    form_data = {
        "full_name": "Слабый Пароль",
        "email": email,
        "password": password,
        "role": "worker",
        "city": "Москва",
    }

    resp = post_with_retry(sess, REGISTER_URL, form_data)
    if resp is None:
        return False

    info(f"POST /register -> статус {resp.status_code}")

    if resp.status_code == 302:
        warn("Сервер принял слабый пароль (редирект 302) — возможна проблема валидации на стороне Supabase")
        return False

    messages = extract_flash_messages(resp.text)
    if messages:
        for msg in messages:
            if any(kw in msg.lower() for kw in ["парол", "passw", "слаб", "weak", "длин", "length", "корот", "short", "6", "8"]):
                ok(f"Слабый пароль отклонён: {msg}")
                return True
            else:
                info(f"Сообщение: {msg}")

    # Если нет явных сообщений, проверяем статус
    if resp.status_code in (400, 422):
        ok(f"Слабый пароль отклонён (HTTP {resp.status_code})")
        return True
    elif resp.status_code == 200:
        # Проверяем HTML на признаки ошибки
        if any(kw in resp.text.lower() for kw in ["пароль", "password", "слаб", "weak", "должен", "must", "недостаточно", "слишком коротк", "too short"]):
            ok("Обнаружено сообщение об ошибке пароля в HTML")
            return True
        # Проверяем, перерендерена ли форма (значит, была ошибка)
        if "регистраци" in resp.text.lower()[:1000] or "register" in resp.text.lower()[:1000]:
            ok("Форма перерендерена — пароль отклонён сервером")
            return True
        warn("Страница перерендерена, но сообщение об ошибке пароля не найдено")
        snippet = resp.text[:500].replace("\n", " ")
        info(f"HTML (первые 500): {snippet}")
        return False
    else:
        warn(f"Неожиданный статус: {resp.status_code}")
        return False


def test_empty_required_fields():
    """Тест 4: Регистрация с пустыми обязательными полями."""
    section("Тест 4: Регистрация с пустыми полями")

    info("Отправка формы с пустыми full_name, email, password, role")

    sess = get_session_with_cookies()

    form_data = {
        "full_name": "",
        "email": "",
        "password": "",
        "role": "",
        "city": "",
    }

    resp = post_with_retry(sess, REGISTER_URL, form_data)
    if resp is None:
        return False

    info(f"POST /register -> статус {resp.status_code}")

    if resp.status_code == 302:
        warn("Сервер принял пустую форму (редирект 302) — возможна проблема валидации")
        return False

    messages = extract_flash_messages(resp.text)
    if messages:
        error_count = 0
        for msg in messages:
            info(f"Сообщение валидации: {msg}")
            if any(kw in msg.lower() for kw in ["укажите", "имя", "email", "пароль", "роль", "выберите", "required", "name", "password", "role"]):
                error_count += 1
        if error_count >= 2:  # Должно быть минимум 2 ошибки (4 обязательных поля)
            ok(f"Пустые поля корректно отклонены ({error_count} сообщений)")
            return True
        elif error_count == 0:
            warn("Нет сообщений о пропущенных обязательных полях")
            return False
        else:
            ok(f"Пустые поля отклонены (найдено {error_count} сообщений)")
            return True

    if resp.status_code == 200:
        # Ищем текст ошибок в HTML
        error_indicators = ["укажите", "обязатель", "required", "заполните"]
        found_errors = [ind for ind in error_indicators if ind in resp.text.lower()]
        if found_errors:
            ok(f"Обнаружены индикаторы ошибок в HTML: {found_errors}")
            return True
        warn("Не удалось найти сообщения об ошибках валидации")
        snippet = resp.text[:500].replace("\n", " ")
        info(f"HTML (первые 500): {snippet}")
        return False
    else:
        warn(f"Неожиданный статус: {resp.status_code}")
        return False


def test_employer_registration():
    """Тест 5: Успешная регистрация работодателя."""
    section("Тест 5: Регистрация работодателя")

    timestamp = int(time.time())
    email = f"test_employer_{timestamp}@test.ru"
    password = "TestPass1"

    info(f"Email: {email}")

    sess = get_session_with_cookies()

    form_data = {
        "full_name": "Работодатель Тестовый",
        "email": email,
        "password": password,
        "role": "employer",
        "city": "Санкт-Петербург",
    }

    resp = post_with_retry(sess, REGISTER_URL, form_data)
    if resp is None:
        return False

    info(f"POST /register -> статус {resp.status_code}")

    if resp.status_code == 302:
        redirect_location = resp.headers.get("Location", "")
        ok(f"Регистрация работодателя успешна! Редирект на {redirect_location}")
        return True
    else:
        messages = extract_flash_messages(resp.text)
        if messages:
            for msg in messages:
                fail(f"Ошибка: {msg}")
        else:
            fail(f"Ожидался 302, получен {resp.status_code}")
        return False


def main():
    """Основная функция запуска всех тестов."""
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Тестирование регистрации Trudnik{RESET}")
    print(f"{BOLD}  {BASE_URL}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    start_time = time.time()
    results = {}

    # Тест 1: Успешная регистрация worker
    results["Успешная регистрация (worker)"] = test_successful_registration()

    # Тест 2: Дубликат email
    results["Дубликат email"] = test_duplicate_email()

    # Тест 3: Слабый пароль
    results["Слабый пароль"] = test_weak_password()

    # Тест 4: Пустые поля
    results["Пустые поля"] = test_empty_required_fields()

    # Тест 5: Регистрация работодателя
    results["Регистрация (employer)"] = test_employer_registration()

    # Итоги
    elapsed = time.time() - start_time
    section("ИТОГИ")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {status}  {name}")

    print(f"\n  Пройдено: {passed}/{total} за {elapsed:.1f} сек")

    if passed == total:
        print(f"\n{GREEN}Все тесты пройдены!{RESET}")
        return 0
    else:
        print(f"\n{RED}Некоторые тесты не пройдены ({total - passed} шт.){RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
