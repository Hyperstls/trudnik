"""
Тесты для D4: проверка использования apiFetch в шаблонах.

Проверяет, что все мутирующие fetch() вызовы (POST/PUT/DELETE)
заменены на apiFetch() в ключевых шаблонах.
"""

import os
import re


def _check_no_raw_mutating_fetch(content, template_name):
    """Проверяет что в контенте нет прямых fetch() с мутирующими методами.
    
    Использует negative lookbehind (?<!api) чтобы исключить apiFetch.
    """
    # Паттерн ищет fetch( но НЕ apiFetch(
    mutating_fetch_pattern = r"(?<!api)fetch\s*\([^)]*['\"](?:POST|PUT|DELETE)['\"]"
    matches = re.findall(mutating_fetch_pattern, content, re.IGNORECASE)
    assert len(matches) == 0, f"Найдены прямые fetch() вызовы с мутирующими методами в {template_name}: {matches}"


def test_my_jobs_uses_apifetch():
    """D4: my_jobs.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'my_jobs.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'my_jobs.html')
    assert 'apiFetch' in content, "apiFetch не используется в my_jobs.html"


def test_job_detail_uses_apifetch():
    """D4: job_detail.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'job_detail.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'job_detail.html')
    assert 'apiFetch' in content, "apiFetch не используется в job_detail.html"


def test_notifications_uses_apifetch():
    """D4: notifications.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'notifications.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'notifications.html')
    assert 'apiFetch' in content, "apiFetch не используется в notifications.html"


def test_notification_settings_uses_apifetch():
    """D4: notification_settings.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'notification_settings.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'notification_settings.html')
    assert 'apiFetch' in content, "apiFetch не используется в notification_settings.html"


def test_invitations_uses_apifetch():
    """D4: invitations.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'invitations.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'invitations.html')
    assert 'apiFetch' in content, "apiFetch не используется в invitations.html"


def test_favorites_uses_apifetch():
    """D4: favorites.html использует apiFetch для мутирующих запросов."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'favorites.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    _check_no_raw_mutating_fetch(content, 'favorites.html')
    assert 'apiFetch' in content, "apiFetch не используется в favorites.html"


def test_base_html_includes_api_js():
    """D4: base.html подключает api.js."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'base.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, что api.js подключен
    assert 'api.js' in content, "api.js не подключен в base.html"
    
    # Проверяем, что api.js подключен ДО других скриптов (должен быть одним из первых)
    api_js_pos = content.find('api.js')
    assert api_js_pos > 0, "api.js не найден в base.html"
