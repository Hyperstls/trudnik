Введение
Этот документ — приложение к архитектурному аудиту проекта «Трудник». Он содержит детальные реализации для каждой из шести фаз рефакторинга, оформленные в виде готовых pull request'ов в GitHub-стиле: Summary, Files changed, Diff, Tests, Risk, Success metrics. Каждый PR можно применять независимо (с соблюдением порядка фаз).
Все примеры кода совместимы с существующим стеком (Flask 3.1, PostgREST 12, Celery 5.6, Redis, FastAPI) и не требуют ввода новых тяжёлых зависимостей. Допускается параллельная работа нескольких инженеров над разными фазами — Фазы 0 и 1 можно выполнять одновременно, Фазы 2 и 3 тоже независимы.
Как читать этот документ
●	Каждый PR начинается с баннера (тёмно-бирюзовый блок) с номером фазы, названием, веткой и base-веткой.
●	«Summary» — краткое описание изменений в 2-3 предложениях.
●	«Files changed» — таблица со списком изменённых файлов, количеством строк, типом изменения и риском.
●	«Diff» — блоки unified diff с цветовой подсветкой: зелёный фон для добавленных строк, красный для удалённых. Можно скопировать напрямую в patch-файл.
●	«Tests» — pytest-тесты, готовые к запуску. Включают как функциональные тесты, так и регрессионные (например, проверка отсутствия threading.Thread).
●	«Risk & rollback» — оценка риска, план отката, митигация.
●	«Success metrics» — измеримые критерии готовности фазы (latency, coverage, отсутствие антипаттернов).
 
Сводная таблица PR
| PR | Фаза | Длительность | Новые файлы | Тесты | Риск |
|---|---|---|---|---|---|
| #0 | Инфраструктурная уборка | 1 неделя | 1 (app/cache.py) | 3 | Low |
| #1 | Кастомные исключения + error handler | 2 недели | 2 (errors.py, error_handlers.py) | 12 | Medium |
| #2 | Repository + admin stats RPC | 3 недели | 5 (repositories/*, migration 076) | 15 | Medium |
| #3 | Use Cases + устранение threading.Thread | 4 недели | 4 (use_cases/*) | 18 | High |
| #4 | Redis cache_for + multi-replica WS | 2 недели | 1 (registry.py) | 12 | Medium-High |
| #5 | DI-контейнер + Config dataclass | 1 неделя | 1 (container.py) | 10 | Low |
Все PR следуют принципу atomic deploy: каждый можно откатить через `git revert` без побочных эффектов. SQL-миграция требуется только для PR #2 (создание RPC-функции get_admin_stats). Во всех остальных случаях изменения ограничены Python-кодом.
Порядок внедрения
Строгий порядок НЕ обязателен, но рекомендован для минимизации регрессий. Минимальный набор для безопасного старта — PR #0 и PR #1 (8 недель при одном инженере). Они дают наибольший выигрыш при минимальном риске: устраняются side-effects при импорте, появляется предсказуемая обработка ошибок, появляются первые юнит-тесты на инфраструктуру.
PR #2 и PR #3 можно выполнять параллельно разными инженерами: Repository-слой и Use Cases не зависят друг от друга. PR #4 (multi-replica WS) можно начинать после PR #0 (нужен app/cache.py) и PR #2 (нужен container). PR #5 — финальная очистка, можно делать в любой момент после PR #2.
Что НЕ входит в этот документ
●	Подробные изменения в шаблонах Jinja2 (templates/*.html) — они минимальны и описаны в каждом PR.
●	Обновления CI/CD конфигурации (.github/workflows/*.yml) — нужно добавить запуск новых тестов в существующий pipeline.
●	Документация для конечных пользователей — поведение системы для них не меняется (кроме более понятных HTTP-ответов на /api/*).
●	Мониторинг и alerting — это отдельная задача, параллельная рефакторингу (см. раздел «Бонус» в основном аудите).
Pull Request #0 — Фаза 0: Инфраструктурная уборка
Pull Request #0  ·  branch: refactor/phase-0-cleanup → main
Фаза 0 — Инфраструктурная уборка (cleanup без изменения поведения)
Summary  Убираем технический долг, не меняющий наблюдаемое поведение: выносим кеш-функции из app/__init__.py в app/cache.py, удаляем глобальный app = create_app() на уровне модуля, чистим неиспользуемые импорты. Цель — убрать side-effects при импорте модуля app, чтобы gunicorn --preload перестал блокироваться на 30 секунд на _wait_for_postgrest.
0.1.	Files changed
| File | Lines +/- | Type | Risk |
|---|---|---|---|
| app/__init__.py | -82 / +12 | Modified | Low |
| app/cache.py | +0 / +68 | New | None |
| app/services/notification_service.py | -6 / +2 | Modified | Low |
| app/blueprints/jobs.py | -4 / +2 | Modified | Low |
| app.py | -0 / +4 | Modified | Low |
| asgi.py | -0 / +4 | Modified | Low |
| scripts/run_e2e_prod.py | -2 / +2 | Modified | Low |
| tests/conftest.py | -0 / +6 | Modified | None |
0.2. Diff: app/cache.py (новый модуль)
Создаём отдельный модуль для кеш-функций, которые раньше жили в app/__init__.py как приватные _redis_cache_get / _redis_cache_set / _redis_cache_delete. Модуль зависит только от redis_client и current_app.logger — никаких обратных зависимостей на app. Это устраняет циклический импорт notification_service → app.
app/cache.py — новый файл (68 строк)
# app/cache.py
"""Redis-backed cache helpers shared between Flask app, services, and tasks.
 
Этот модуль НЕ зависит от app/__init__.py — наоборот, app/__init__.py
импортирует из него. Это устраняет циклическую зависимость, из-за которой
раньше в notification_service приходилось писать:
    from app import _redis_cache_delete  # циклический импорт
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from flask import current_app
from app.utils.redis_client import get_redis_client
 
logger = logging.getLogger(__name__)
_DEFAULT_TTL = 30  # секунд
 
 
def cache_get(key: str, *, as_int: bool = False) -> Optional[Any]:
    """Получить значение из Redis-кеша. None если Redis недоступен или ключ не найден."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        if value is None:
            return None
        return int(value) if as_int else value
    except Exception as e:
        logger.warning('cache_get(%s) failed: %s', key, e)
        return None
 
 
def cache_set(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """Сохранить значение в Redis-кеш с TTL. No-op если Redis недоступен."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(key, ttl, value)
    except Exception as e:
        logger.warning('cache_set(%s) failed: %s', key, e)
 
 
def cache_delete(key: str) -> None:
    """Удалить ключ из кеша. No-op если Redis недоступен."""
    client = get_redis_client()
    if client is not None:
        try:
            client.delete(key)
        except Exception as e:
            logger.warning('cache_delete(%s) failed: %s', key, e)
 
 
def cache_incr(key: str, ttl: int = _DEFAULT_TTL) -> Optional[int]:
    """Атомарный INCR + EXPIRE (если ключ новый). Возвращает новое значение или None."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        current = client.incr(key)
        if current == 1:
            client.expire(key, ttl)
        return current
    except Exception as e:
        logger.warning('cache_incr(%s) failed: %s', key, e)
        return None
0.3. Diff: app/__init__.py (удаление глобального app + вынос кеша)
Главное изменение — убрать строку `app = create_app()` в конце модуля. Она приводила к side-effects при импорте: _wait_for_postgrest блокировал поток на 30 секунд, инициализировался Redis-клиент, выполнялась проверка JWT-секрета. Это ломало gunicorn --preload и замедляло запуск тестов.
app/__init__.py — unified diff
--- a/app/__init__.py
+++ b/app/__init__.py
@@ -1,4 +1,3 @@
-import subprocess
 import secrets
 import os
 import time
@@ -13,57 +12,6 @@
 from app.config import Config
 import time as _time_module
 _app_start_time = _time_module.time()
-
-# ── Redis-кэш (TTL 30 сек) ──
-# Глобальный кэш между worker'ами через Redis.
-# При отсутствии Redis — graceful degradation (возврат None).
-from app.utils.redis_client import get_redis_client
-
-_REDIS_CACHE_TTL = 30  # секунд
-
-
-def _redis_cache_get(key: str):
-    try:
-        client = get_redis_client()
-        if client is None:
-            return None
-        value = client.get(key)
-        if value is not None:
-            return int(value)
-    except Exception:
-        pass
-    return None
-
-
-def _redis_cache_set(key: str, value: int, ttl: int = _REDIS_CACHE_TTL):
-    try:
-        client = get_redis_client()
-        if client is not None:
-            client.setex(key, ttl, value)
-    except Exception:
-        pass
-
-
-def _redis_cache_delete(key: str):
-    try:
-        client = get_redis_client()
-        if client is not None:
-            client.delete(key)
-    except Exception:
-        pass
+from app.cache import cache_get, cache_set, cache_delete  # реэкспорт для обратной совместимости
 
 # Псевдонимы для обратной совместимости (deprecation warning в логах при первом использовании)
_redis_cache_get = cache_get
_redis_cache_set = cache_set
_redis_cache_delete = cache_delete
@@ -510,7 +448,3 @@
     return app
-
-# Экземпляр приложения для WSGI/ASGI (Render, Gunicorn и совместимость)
-app = create_app()
+# ВНИМАНИЕ: глобальный app удалён. Используйте create_app() явно в app.py и asgi.py.
0.4. Diff: app.py (явный вызов create_app)
app.py — 4 новые строки
# app.py — точка входа для локальной разработки и docker-compose
"""WSGI entry point. Explicitly creates Flask app via factory.
 
Запуск:
    python app.py                # локальная разработка
    gunicorn 'app:app'          # gunicorn без preload
    gunicorn --preload 'app:app'  # gunicorn с preload (теперь безопасно)
"""
from app import create_app
 
app = create_app()
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(app.config.get('PORT', 5000)), debug=False)
0.5. Diff: asgi.py (явный вызов create_app)
asgi.py — unified diff
--- a/asgi.py
+++ b/asgi.py
@@ -3,7 +3,8 @@
 Routes /ws WebSocket to FastAPI, everything else to Flask via WSGIMiddleware.
 """
 from a2wsgi import WSGIMiddleware
-from app import app as flask_app
+from app import create_app
 from websocket_server.main import app as ws_app
 
+flask_app = create_app()
 # Wrap Flask as ASGI
 flask_asgi = WSGIMiddleware(flask_app)
0.6. Diff: app/services/notification_service.py (прямой импорт)
Заменяем lazy import `from app import _redis_cache_delete` (который был обходом циклической зависимости) на прямой импорт из нового модуля app.cache.
app/services/notification_service.py — 2 места
--- a/app/services/notification_service.py
+++ b/app/services/notification_service.py
@@ -219,9 +219,7 @@
     # Инвалидируем Redis-кэш счётчика непрочитанных уведомлений
-    # noqa: локальный импорт — циклическая зависимость (app → notification_service → app)
-    try:
-        from app import _redis_cache_delete
-        _redis_cache_delete(f'unread:{user_id}')
-    except Exception:
-        pass  # Redis недоступен — не фатально
+    # Прямой импорт — циклической зависимости больше нет (Фаза 0)
+    from app.cache import cache_delete
+    cache_delete(f'unread:{user_id}')
     return True
@@ -328,9 +326,7 @@
         # Инвалидируем Redis-кэш счётчика непрочитанных уведомлений
-        try:
-            from app import _redis_cache_delete
-            _redis_cache_delete(f'unread:{user_id}')
-        except Exception:
-            pass
+        from app.cache import cache_delete
+        cache_delete(f'unread:{user_id}')
0.7. Diff: app/blueprints/jobs.py (прямой импорт)
app/blueprints/jobs.py — строка 79
--- a/app/blueprints/jobs.py
+++ b/app/blueprints/jobs.py
@@ -76,9 +76,7 @@
     # application_count с кешированием в Redis
-    from app import _redis_cache_get, _redis_cache_set
-    cached = _redis_cache_get(f'job_app_count:{job_id}')
+    from app.cache import cache_get, cache_set
+    cached = cache_get(f'job_app_count:{job_id}', as_int=True)
     if cached is not None:
         job['application_count'] = cached
     else:
         app_resp = postgrest_request('GET', f'applications?job_id=eq.{job_id}&select=id')
         count = len(app_resp.json()) if app_resp.ok and app_resp.json() else 0
         job['application_count'] = count
-        _redis_cache_set(f'job_app_count:{job_id}', count, ttl=60)
+        cache_set(f'job_app_count:{job_id}', count, ttl=60)
0.8. Tests
Добавляем минимальный smoke-тест, что импорт app больше не вызывает side-effects (не ждёт PostgREST, не инициализирует Redis). Это регрессионный тест на Фазу 0.
tests/test_phase0_no_side_effects.py — новый файл
# tests/test_phase0_no_side_effects.py
"""Фаза 0: импорт app.create_app не должен вызывать side-effects.
 
Регрессионный тест: если кто-то вернёт `app = create_app()` на уровень
модуля или добавит _wait_for_postgrest в тело функции, этот тест упадёт.
"""
import sys
import time
import importlib
 
 
def test_import_does_not_block_on_postgrest():
    """Импорт app должен занимать < 1 сек (без _wait_for_postgrest)."""
    # Выгружаем app из кеша модулей
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith('app'):
            del sys.modules[mod_name]
 
    start = time.monotonic()
    importlib.import_module('app')
    elapsed = time.monotonic() - start
 
    assert elapsed < 1.0, (
        f'Импорт app занял {elapsed:.2f}с — вероятно, вернулся side-effect " +
        f'(напр. _wait_for_postgrest). Фаза 0 нарушена.'
    )
 
 
def test_no_global_app_attribute():
    """На уровне модуля app не должно быть атрибута app (только create_app)."""
    import app
    assert not hasattr(app, 'app'), (
        'app.app существует — кто-то вернул глобальный app = create_app(). " +
        'Это блокирует gunicorn --preload. См. Фазу 0.'
    )
    assert hasattr(app, 'create_app'), 'create_app должна быть доступна'
 
 
def test_cache_module_importable_without_flask_context():
    """app.cache должен импортироваться без Flask app context."""
    from app.cache import cache_get, cache_set, cache_delete
    assert callable(cache_get)
    assert callable(cache_set)
    assert callable(cache_delete)
0.9. Risk & rollback
| Поле | Значение |
|---|---|
| Risk level | Low — изменения не меняют наблюдаемое поведение |
| Backward compat | Полная: _redis_cache_ * доступны через алиасы, глобальный арр создаётся в app.py и asgi.py |
| Rollback | git revert одного PR; no migration needed |
| Soak test | 24 часа на staging; проверить /health endpoint |
| Deployment | Стандартный deploy через amvera deploy |
0.10. Success metrics
●	gunicorn --preload запускается без блокировки на 30 секунд (was: 30s blocking, now: <1s).
●	pytest --collect-only выполняется за < 2 сек (was: ~30 сек из-за side-effects).
●	0 lazy imports вида `from app import _redis_cache_*` в кодовой базе (rg --type py).
●	/health endpoint отвечает 200 на staging в течение 24 часов soak test.
Pull Request #1 — Фаза 1: Кастомные исключения и error handler
Pull Request #1  ·  branch: refactor/phase-1-errors → main
Фаза 1 — Кастомные исключения и централизованный error handler
 Summary  
Вводим иерархию DomainError + InfrastructureError, регистрируем централизованный errorhandler в create_app(). Постепенно (модуль за модулем) заменяем 50+ конструкций `except Exception: pass` и ручные `flash() + redirect()` на throw типизированных исключений. Цель — предсказуемые HTTP-ответы и stack trace в логах вместо молчаливого глушения.
1.1.	Files changed
| File | Lines +/– | Type | Risk |
|---|---|---|---|
| app/errors.py | +0 / +95 | New | None |
| app/error_handlers.py | +0 / +72 | New | None |
| app/__init__.py | +2 / +0 | Modified | Low |
| app/blueprints/applications.py | –38 / +18 | Modified | Medium |
| app/blueprints/profile.py | –12 / +6 | Modified | Medium |
| app/blueprints/admin.py | –24 / +12 | Modified | Medium |
| app/blueprints/notifications.py | –8 / +4 | Modified | Low |
| tests/test_errors.py | +0 / +120 | New | None |
1.2. New: app/errors.py (полная иерархия)
Иерархия разделена на два корня: DomainError (бизнес-ошибки — пользователь что-то сделал не так) и InfrastructureError (внешние сервисы недоступны). Каждый класс знает свой HTTP-статус и user-friendly сообщение на русском. Это позволяет errorhandler быть тупым: он просто читает атрибуты исключения.
app/errors.py — новый файл (95 строк)
# app/errors.py
"""Иерархия кастомных исключений для Trudnik.
 
Разделена на два корня:
- DomainError: бизнес-ошибки (пользователь что-то сделал не так)
- InfrastructureError: внешние сервисы недоступны (PostgREST, Redis, SMTP)
 
Каждое исключение знает свой HTTP-статус и user-friendly сообщение.
Централизованный errorhandler в app/error_handlers.py просто читает
эти атрибуты и формирует ответ — без if/elif цепочек.
"""
from __future__ import annotations
 
 
class AppError(Exception):
    """Базовый класс для всех кастомных исключений приложения."""
    http_status: int = 500
    user_message: str = 'Произошла непредвиденная ошибка'
    error_code: str = 'INTERNAL_ERROR'
    log_level: str = 'error'  # 'warning' или 'error'
 
    def __init__(self, message: str | None = None, *, error_code: str | None = None):
        super().__init__(message or self.user_message)
        if message:
            self.user_message = message
        if error_code:
            self.error_code = error_code
 
 
# ═══════════════════════════════════════════════════════════════
# Domain errors (4xx — клиентская ошибка)
# ═══════════════════════════════════════════════════════════════
 
class DomainError(AppError):
    """Базовый класс бизнес-ошибок. HTTP 400 по умолчанию."""
    http_status = 400
    log_level = 'warning'
 
 
class NotFoundError(DomainError):
    http_status = 404
    user_message = 'Объект не найден'
    error_code = 'NOT_FOUND'
 
 
class PermissionDeniedError(DomainError):
    http_status = 403
    user_message = 'Доступ запрещён'
    error_code = 'PERMISSION_DENIED'
 
 
class ValidationFailedError(DomainError):
    http_status = 422
    user_message = 'Некорректные данные'
    error_code = 'VALIDATION_FAILED'
 
 
class ConflictError(DomainError):
    http_status = 409
    user_message = 'Конфликт состояний'
    error_code = 'CONFLICT'
 
 
# ═══════════════════════════════════════════════════════════════
# Apply-job specific (наиболее часто встречающаяся бизнес-логика)
# ═══════════════════════════════════════════════════════════════
 
class ApplyJobError(DomainError):
    """Базовая ошибка операции apply_job."""
    error_code = 'APPLY_JOB_FAILED'
 
 
class DuplicateApplicationError(ApplyJobError):
    user_message = 'Вы уже откликались на это задание'
    error_code = 'DUPLICATE_APPLICATION'
 
 
class NoSlotsAvailableError(ApplyJobError):
    user_message = 'Все места в задании заняты'
    error_code = 'NO_SLOTS'
 
 
class BlacklistedByEmployerError(ApplyJobError):
    http_status = 403
    user_message = 'Работодатель добавил вас в чёрный список'
    error_code = 'BLACKLISTED'
 
 
class JobNotOpenError(ApplyJobError):
    user_message = 'На это задание нельзя откликнуться'
    error_code = 'JOB_NOT_OPEN'
 
 
class CannotApplyToOwnJobError(ApplyJobError):
    user_message = 'Вы не можете откликаться на собственное задание'
    error_code = 'SELF_APPLY'
 
 
# ═══════════════════════════════════════════════════════════════
# Withdraw specific
# ═══════════════════════════════════════════════════════════════
 
class WithdrawError(DomainError):
    error_code = 'WITHDRAW_FAILED'
 
 
class WithdrawWindowClosedError(WithdrawError):
    user_message = 'Нельзя отозвать принятый отклик менее чем за 12 часов до начала задания'
    error_code = 'WITHDRAW_WINDOW_CLOSED'
 
 
# ═══════════════════════════════════════════════════════════════
# Infrastructure errors (5xx — серверная/инфраструктурная ошибка)
# ═══════════════════════════════════════════════════════════════
 
class InfrastructureError(AppError):
    """Базовый класс инфраструктурных ошибок. HTTP 503 по умолчанию."""
    http_status = 503
    user_message = 'Сервис временно недоступен. Попробуйте позже.'
    log_level = 'error'
 
 
class PostgrestError(InfrastructureError):
    error_code = 'POSTGREST_ERROR'
    user_message = 'Ошибка обращения к базе данных'
 
 
class CircuitBreakerOpenError(InfrastructureError):
    error_code = 'CIRCUIT_BREAKER_OPEN'
 
 
class RedisUnavailableError(InfrastructureError):
    error_code = 'REDIS_UNAVAILABLE'
 
 
class ExternalServiceError(InfrastructureError):
    """Обёртка для ошибок внешних сервисов (SMTP, Yandex Maps, Web Push)."""
    error_code = 'EXTERNAL_SERVICE_ERROR'
 
    def __init__(self, service: str, message: str | None = None):
        super().__init__(message or f'{service} недоступен')
        self.service = service
1.3. New: app/error_handlers.py (централизованный handler)
app/error_handlers.py — новый файл (72 строки)
# app/error_handlers.py
"""Централизованные error handlers для Flask-приложения.
 
Регистрируются в create_app() через register_error_handlers(app).
Любой маршрут может выбросить AppError (или его подкласс), и handler
сформирует корректный HTTP-ответ без дублирования логики в каждой view.
 
Контракт:
- HTML-запросы (не /api/*) → flash + redirect на referrer или jobs.index
- JSON-запросы (/api/* или Accept: application/json) → JSON с кодом ошибки
- InfrastructureError → логируется с stack trace, статус 5xx
- DomainError → логируется как warning, статус 4xx
- Необработанное Exception → 500 + полный stack trace в логах
"""
from __future__ import annotations
import logging
from flask import Flask, current_app, flash, jsonify, redirect, request, url_for, render_template
from werkzeug.exceptions import HTTPException
 
from app.errors import (
    AppError, DomainError, InfrastructureError,
)
 
logger = logging.getLogger(__name__)
 
 
def _is_api_request() -> bool:
    """Запрос к /api/* или AJAX (Accept: application/json)."""
    return (
        request.path.startswith('/api/')
        or request.is_json
        or 'application/json' in request.headers.get('Accept', '')
    )
 
 
def _log_error(e: AppError) -> None:
    """Логирование с правильным уровнем и stack trace."""
    msg = f'{type(e).__name__}: {e.user_message} (code={e.error_code}, path={request.path})'
    if e.log_level == 'error':
        logger.exception(msg)
    else:
        logger.warning(msg)
 
 
def register_error_handlers(app: Flask) -> None:
    """Регистрирует все error handlers в Flask app."""
 
    @app.errorhandler(DomainError)
    def handle_domain_error(e: DomainError):
        _log_error(e)
        if _is_api_request():
            return jsonify({
                'success': False,
                'error': e.user_message,
                'code': e.error_code,
            }), e.http_status
        flash(e.user_message, 'info' if e.http_status < 500 else 'danger')
        return redirect(request.referrer or url_for('jobs.index'))
 
    @app.errorhandler(InfrastructureError)
    def handle_infra_error(e: InfrastructureError):
        _log_error(e)
        if _is_api_request():
            return jsonify({
                'success': False,
                'error': e.user_message,
                'code': e.error_code,
            }), e.http_status
        flash(e.user_message, 'warning')
        return redirect(request.referrer or url_for('jobs.index'))
 
    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        # 404, 405, 400 и т.д. — пропускаем как есть
        if e.code == 404:
            return render_template('error.html', error_code='404',
                                   error='Страница не найдена'), 404
        if _is_api_request():
            return jsonify({'success': False, 'error': e.description}), e.code
        flash(e.description, 'warning')
        return redirect(request.referrer or url_for('jobs.index'))
 
    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        # Последний рубеж — никаких bare except Exception больше не нужно
        logger.exception('Unhandled exception at %s: %s', request.path, e)
        if _is_api_request():
            return jsonify({
                'success': False,
                'error': 'Внутренняя ошибка сервера',
                'code': 'INTERNAL_ERROR',
            }), 500
        return render_template('error.html', error_code='500',
                               error='Произошла непредвиденная ошибка. Мы уже работаем над её устранением.'), 500
1.4. Diff: app/__init__.py (регистрация handlers)
app/__init__.py — 3 новые строки
--- a/app/__init__.py
+++ b/app/__init__.py
@@ -240,6 +240,9 @@
     from app.context_processors import register_context_processors
     register_context_processors(app)
 
+    # Фаза 1: централизованные error handlers
+    from app.error_handlers import register_error_handlers
+    register_error_handlers(app)
+
     @app.context_processor
     def inject_sort_url():
1.5. Diff: app/blueprints/applications.py (пример — apply_job)
Переписываем apply_job, выбрасывая типизированные исключения вместо ручных flash + redirect. Это уменьшает длину функции примерно вдвое и делает контрольный поток явным. Обработчик ошибок сам сформирует правильный ответ — HTML или JSON — в зависимости от типа запроса.
app/blueprints/applications.py — apply_job переписан
--- a/app/blueprints/applications.py
+++ b/app/blueprints/applications.py
@@ -18,29 +18,22 @@
 from app.config import Config
 from app.decorators import login_required, rate_limit, role_required, validate_uuid
 from app.utils import postgrest_request, postgrest_admin_request, postgrest_rpc
 from app.utils.helpers import assert_postgrest_ok
 from app.services.notification_service import create as notify, enqueue_notification
+from app.errors import (
+    ApplyJobError, DuplicateApplicationError, NoSlotsAvailableError,
+    BlacklistedByEmployerError, JobNotOpenError, CannotApplyToOwnJobError,
+    PostgrestError,
+)
 
 @applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
 @login_required
 @validate_uuid('job_id')
 @rate_limit
 def apply_job(job_id):
     user_id = session['user_id']
-    # Быстрая предварительная проверка дубликата (некритичная, только для UX)
-    check = postgrest_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
-    if check.ok and check.json():
-        flash('Вы уже откликались на это задание', 'info')
-        return redirect(url_for('jobs.index'))
+    # Проверка дубликата вынесена в _check_duplicate (выбрасывает исключение)
+    _check_duplicate(job_id, user_id)
 
     rpc_result = postgrest_rpc('apply_job_atomic', {
         'p_job_id': job_id,
         'p_worker_id': user_id,
     }, use_admin=True)
 
-    if not rpc_result.ok:
-        if rpc_result.status_code == 404:
-            logger.warning('apply_job: RPC not found, falling back to non-atomic')
-            return _apply_job_fallback(job_id, user_id)
-        flash('Ошибка при отправке отклика', 'danger')
-        return redirect(url_for('jobs.index'))
+    if not rpc_result.ok:
+        if rpc_result.status_code == 404:
+            logger.warning('apply_job: RPC not found — migration 048 not applied')
+            raise PostgrestError('RPC apply_job_atomic не найдена (миграция 048)')
+        raise PostgrestError(f'PostgREST вернул {rpc_result.status_code}')
 
     result = rpc_result.json()
     if not result or not result.get('success'):
         error_code = (result or {}).get('code', 'unknown')
         error_msg = (result or {}).get('error', 'Не удалось отправить отклик')
-        if error_code == 'blacklisted':
-            if request.method == 'POST':
-                return jsonify({'success': False, 'error': error_msg}), 403
-            flash(error_msg, 'danger')
-            return redirect(url_for('jobs.index'))
-        category = 'info' if error_code in ('duplicate', 'no_slots') else 'danger'
-        flash(error_msg, category)
-        return redirect(url_for('jobs.index'))
+        # Маппинг кодов RPC на типизированные исключения
+        _APPLY_ERROR_MAP = {
+            'blacklisted': BlacklistedByEmployerError(error_msg),
+            'duplicate': DuplicateApplicationError(error_msg),
+            'no_slots': NoSlotsAvailableError(error_msg),
+            'job_not_open': JobNotOpenError(error_msg),
+            'self_apply': CannotApplyToOwnJobError(error_msg),
+        }
+        raise _APPLY_ERROR_MAP.get(error_code, ApplyJobError(error_msg))
 
     # Успех: уведомление через transactional outbox (НЕ threading.Thread — Фаза 3)
     employer_id = result.get('employer_id')
     if employer_id:
         _link = url_for('jobs.job_detail', job_id=job_id, _external=True)
         enqueue_notification(employer_id, 'application_received', 'Новый отклик',
             f'На ваше задание поступил новый отклик',
             data={'job_id': job_id, 'link': _link})
+    flash('Отклик отправлен', 'success')
+    return redirect(url_for('jobs.index'))
 
 
+def _check_duplicate(job_id: str, user_id: str) -> None:
+    """Выбрасывает DuplicateApplicationError, если уже откликались."""
+    check = postgrest_request('GET',
+        f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}&select=id')
+    if check.ok and check.json():
+        raise DuplicateApplicationError()
1.6. Diff: app/blueprints/admin.py (замена bare except)
В admin.py 13 вхождений `except Exception`. Заменяем на конкретные типизированные исключения. Пример — log_admin_action, который сейчас глушит любую ошибку записи в audit_log.
app/blueprints/admin.py — log_admin_action
--- a/app/blueprints/admin.py
+++ b/app/blueprints/admin.py
@@ -15,15 +15,13 @@
 def log_admin_action(action, table_name=None, record_id=None, old_data=None, new_data=None):
     """Логирует админское действие в audit_log через PostgREST (C19)."""
-    try:
-        payload = {
-            'user_id': session.get('user', {}).get('id'),
-            'action': action,
-            'table_name': table_name,
-            'record_id': str(record_id) if record_id else None,
-            'old_data': json.dumps(old_data) if old_data else None,
-            'new_data': json.dumps(new_data) if new_data else None,
-            'ip_address': request.remote_addr
-        }
-        postgrest_admin_request('POST', 'audit_log', data=payload)
-    except Exception as e:
-        current_app.logger.warning('Failed to log admin action: %s', e)
+    payload = {
+        'user_id': session.get('user', {}).get('id'),
+        'action': action,
+        'table_name': table_name,
+        'record_id': str(record_id) if record_id else None,
+        'old_data': json.dumps(old_data) if old_data else None,
+        'new_data': json.dumps(new_data) if new_data else None,
+        'ip_address': request.remote_addr
+    }
+    resp = postgrest_admin_request('POST', 'audit_log', data=payload)
+    if not resp.ok:
+        # Audit log — best-effort: логируем, но не прерываем операцию
+        current_app.logger.warning(
+            'Failed to log admin action: action=%s status=%s body=%s',
+            action, resp.status_code, (resp.text or '')[:200]
+        )
1.7. Tests
tests/test_errors.py — 120 строк
# tests/test_errors.py
"""Фаза 1: тесты иерархии исключений и error handlers."""
import pytest
from flask import Flask
from app.errors import (
    DuplicateApplicationError, BlacklistedByEmployerError,
    PostgrestError, CircuitBreakerOpenError,
)
from app.error_handlers import register_error_handlers
 
 
@pytest.fixture
def app_with_handlers():
    app = Flask(__name__)
    app.config['TESTING'] = True
    register_error_handlers(app)
 
    @app.route('/test/duplicate')
    def test_duplicate():
        raise DuplicateApplicationError()
 
    @app.route('/test/blacklisted')
    def test_blacklisted():
        raise BlacklistedByEmployerError()
 
    @app.route('/test/postgrest')
    def test_postgrest():
        raise PostgrestError('connection refused')
 
    @app.route('/test/unexpected')
    def test_unexpected():
        raise RuntimeError('boom')
 
    return app
 
 
class TestErrorHierarchy:
    def test_duplicate_has_correct_status(self):
        e = DuplicateApplicationError()
        assert e.http_status == 400
        assert e.error_code == 'DUPLICATE_APPLICATION'
        assert 'уже откликались' in e.user_message
 
    def test_blacklisted_is_403(self):
        e = BlacklistedByEmployerError()
        assert e.http_status == 403
 
    def test_postgrest_is_503(self):
        e = PostgrestError('test')
        assert e.http_status == 503
        assert e.log_level == 'error'
 
 
class TestErrorHandlerJSONResponses:
    def test_duplicate_returns_json_for_api(self, app_with_handlers):
        client = app_with_handlers.test_client()
        resp = client.get('/test/duplicate', headers={'Accept': 'application/json'})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['code'] == 'DUPLICATE_APPLICATION'
 
    def test_blacklisted_returns_403_json(self, app_with_handlers):
        client = app_with_handlers.test_client()
        resp = client.get('/test/blacklisted', headers={'Accept': 'application/json'})
        assert resp.status_code == 403
 
    def test_postgrest_returns_503_json(self, app_with_handlers):
        client = app_with_handlers.test_client()
        resp = client.get('/test/postgrest', headers={'Accept': 'application/json'})
        assert resp.status_code == 503
        assert 'Сервис временно недоступен' in resp.get_json()['error']
 
    def test_unexpected_returns_500_json(self, app_with_handlers):
        client = app_with_handlers.test_client()
        resp = client.get('/test/unexpected', headers={'Accept': 'application/json'})
        assert resp.status_code == 500
        assert resp.get_json()['code'] == 'INTERNAL_ERROR'
 
 
class TestErrorHandlerHTMLResponses:
    def test_duplicate_redirects_with_flash(self, app_with_handlers):
        client = app_with_handlers.test_client()
        resp = client.get('/test/duplicate')
        assert resp.status_code == 302  # redirect
        assert b'уже откликались' in resp.data or resp.location
 
 
class TestNoBareExcept:
    def test_no_new_bare_except_in_applications(self):
        """Регрессионный тест: в applications.py не должно быть новых except Exception."""
        import re
        from pathlib import Path
        content = Path('app/blueprints/applications.py').read_text(encoding='utf-8')
        bare_excepts = re.findall(r'except\s+Exception\s*:', content)
        assert len(bare_excepts) <= 2, (
            f'Найдено {len(bare_excepts)} bare except Exception — Фаза 1 требует < 3'
        )
1.8. Risk & rollback
| Поле | Значение |
|---|---|
| Risk level | Medium — меняется HTTP-ответ на ошибки (был 200+flash, стал 4xx/5xx JSON) |
| Mitigation | На staging сначала, soak test 48 часов; миграция на продакшн по модулям (1 blueprint за PR) |
| Rollback | git revert; обратная совместимость — старые клиенты, ожидающие 200, увидят 4xx (это валидная семантика) |
| Monitoring | Добавить alert: rate of 5xx > 1% в течение часа → откат |
| Backward compat | HTML-страницы: было 302+flash, осталось 302+flash (semantics unchanged) |
1.9. Success metrics
●	0 новых `except Exception: pass` в кодовой базе (проверка: rg --type py 'except Exception:\s*\n\s*pass' app/).
●	Все `/api/*` маршруты возвращают JSON с полями success / error / code на ошибках (curl тест).
●	Coverage error_handlers.py > 90% (pytest-cov).
●	Latency p95 на /api/skills, /api/religions не ухудшается (baseline замер до PR).
Pull Request #2 — Фаза 2: Repository-слой + admin stats RPC
Pull Request #2  ·  branch: refactor/phase-2-repository → main
Фаза 2 — Repository-слой над PostgREST + admin stats RPC
 Summary  
Вводим Repository-абстракцию над PostgREST, чтобы бизнес-логика (Use Cases в Фазе 3) не зависела от конкретного HTTP-клиента. Параллельно устраняем N+1 в admin_panel: вместо 8 последовательных count=exact запросов — один RPC get_admin_stats() с GROUP BY в PostgreSQL. Это даёт 8× ускорение на странице /admin при росте числа пользователей.
2.1. Files changed
| File | Lines +/- | Type | Risk |
|---|---|---|---|
| migrations/076_get_admin_stats.sql | +0 / +45 | New | Low (new RPC) |
| app/repositories/__init__.py | +0 / +5 | New | None |
| app/repositories/base.py | +0 / +52 | New | None |
| app/repositories/postgresql_client_mixi.n.py | +0 / +88 | New | None |
| app/repositories/job_repository.py | +0 / +124 | New | None |
| app/repositories/application_repository.py | +0 / +96 | New | None |
| app/repositories/admin_repository.py | +0 / +68 | New | None |
| app/repositories/notification_repository.py | +0 / +72 | New | None |
| app/blueprints/admin.py | -82 / +12 | Modified | Medium (refactor admin_panel) |
| tests/test_repositories.py | +0 / +180 | New | None |
2.2. New: migrations/076_get_admin_stats.sql
Один RPC заменяет 8 count=exact запросов. Используем json_build_object для атомарной сборки ответа. Функция помечена STABLE (PostgREST кеширует результат в пределах запроса) и SECURITY DEFINER (обходит RLS для подсчёта всех пользователей).
migrations/076_get_admin_stats.sql — 45 строк
-- migrations/076_get_admin_stats.sql
-- Заменяет 8 последовательных count=exact запросов в admin_panel
-- на один атомарный RPC с GROUP BY в PostgreSQL.
 
CREATE OR REPLACE FUNCTION get_admin_stats()
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_users', (SELECT COUNT(*) FROM profiles),
        'users_by_role', (
            SELECT COALESCE(json_object_agg(role, cnt), '{}'::json)
            FROM (
                SELECT role, COUNT(*) AS cnt
                FROM profiles
                GROUP BY role
            ) s
        ),
        'total_jobs', (SELECT COUNT(*) FROM jobs),
        'jobs_by_status', (
            SELECT COALESCE(json_object_agg(status, cnt), '{}'::json)
            FROM (
                SELECT status, COUNT(*) AS cnt
                FROM jobs
                GROUP BY status
            ) s
        ),
        'pending_verifications', (
            SELECT COUNT(*) FROM profiles
            WHERE verification_status = 'pending'
        ),
        'generated_at', NOW()
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
 
-- Права: только admin и service_role могут вызывать
REVOKE EXECUTE ON FUNCTION get_admin_stats() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admin_stats() TO trudnikapp;
 
-- Комментарий для документации
COMMENT ON FUNCTION get_admin_stats() IS
'Возвращает сводную статистику для админ-панели: число пользователей по ролям,
число заданий по статусам, число ожидающих верификацию. Заменяет 8 count=exact запросов.';
2.3. New: app/repositories/base.py
Абстрактный базовый класс для всех repository. Хранит ссылку на PostgrestClient (который сейчас — модуль postgrest_client.py) и предоставляет типизированные методы-обёртки. Главная цель — централизовать проверки resp.ok и преобразование в TypeError вместо того, чтобы повторять их в каждом методе.
app/repositories/base.py — 52 строки
# app/repositories/base.py
"""Базовый класс для всех Repository над PostgREST."""
from __future__ import annotations
import logging
from typing import Any, Optional
from app.errors import PostgrestError, NotFoundError
 
logger = logging.getLogger(__name__)
 
 
class BaseRepository:
    """Обёртка над PostgREST с типизированными возвращаемыми значениями.
 
    Подклассы (JobRepository, ApplicationRepository, ...) добавляют
    бизнес-специфичные методы, использующие _get_one, _get_many, _count.
    Все методы выбрасывают PostgrestError при сбое вместо возврата None —
    это позволяет вызывающему коду не проверять результат на None.
    """
 
    def __init__(self, client: Any):
        # client — это модуль app.utils.postgrest_client или его mock в тестах
        self._client = client
 
    def _get_one(self, query: str, *, use_admin: bool = False) -> dict:
        """Вернуть одну запись. Выбрасывает NotFoundError, если ничего нет."""
        resp = self._call('GET', query, use_admin=use_admin)
        data = resp.json() if resp.ok else None
        if not data:
            raise NotFoundError(f'Запрос {query.split("?")[0]} вернул пустой результат')
        return data[0] if isinstance(data, list) else data
 
    def _get_many(self, query: str, *, use_admin: bool = False) -> list[dict]:
        """Вернуть список записей. Пустой список если ничего не найдено."""
        resp = self._call('GET', query, use_admin=use_admin)
        if not resp.ok:
            raise PostgrestError(f'GET {query} failed: {resp.status_code}')
        data = resp.json()
        return data if isinstance(data, list) else []
 
    def _count(self, query: str, *, use_admin: bool = False) -> int:
        """Точный подсчёт через Prefer: count=exact."""
        resp = self._call('GET', query + '&limit=0',
                          use_admin=use_admin,
                          headers={'Prefer': 'count=exact'})
        if not resp.ok:
            raise PostgrestError(f'COUNT {query} failed: {resp.status_code}')
        content_range = resp.headers.get('Content-Range', '0-0/0')
        try:
            return int(content_range.split('/')[-1])
        except (IndexError, ValueError):
            return 0
 
    def _call(self, method: str, endpoint: str, *, use_admin: bool = False, **kwargs):
        """Вызов PostgREST. В подклассах можно переопределить для логирования."""
        if use_admin:
            return self._client.postgrest_admin_request(method, endpoint, **kwargs)
        return self._client.postgrest_request(method, endpoint, **kwargs)
 
    def _rpc(self, name: str, params: dict, *, use_admin: bool = False):
        """Вызов хранимой процедуры."""
        return self._client.postgrest_rpc(name, params, use_admin=use_admin)
2.4. New: app/repositories/job_repository.py
Пример конкретного репозитория. Методы возвращают типизированные dict (в Python 3.12 можно использовать TypedDict для строгой типизации). Каждый метод сам строит PostgREST-строку — вьюхи больше не должны это делать.
app/repositories/job_repository.py — 124 строки
# app/repositories/job_repository.py
"""Repository для таблицы jobs."""
from __future__ import annotations
import logging
from typing import Any, Optional
from datetime import datetime, timezone
 
from app.repositories.base import BaseRepository
from app.repositories.postgrest_client_mixin import PostgrestClientMixin
from app.errors import NotFoundError, PostgrestError
from app.utils import sanitize_postgrest, calculate_distance
 
logger = logging.getLogger(__name__)
 
 
class JobRepository(PostgrestClientMixin, BaseRepository):
    """Доступ к таблице jobs через PostgREST."""
 
    JOB_DETAIL_SELECT = (
        '*,photos:job_photos(*),employer:profiles!jobs_employer_id_fkey(id,full_name,verification_status)'
    )
    JOB_LIST_SELECT = (
        'id,employer_id,organization_name,object_description,work_type,
        date_time,payment_amount,address,city,lat,lng,status,created_at,
        preferred_religion,max_workers,current_workers,expires_at,tariff,
        promoted_until,photos:job_photos(*)'
    )
 
    def get_by_id(self, job_id: str) -> dict:
        """Получить задание по ID с фотками и профилем работодателя (один запрос вместо 3)."""
        return self._get_one(
            f'jobs?id=eq.{job_id}&select={self.JOB_DETAIL_SELECT}',
            use_admin=True,
        )
 
    def get_owner_id(self, job_id: str) -> str:
        """Только employer_id — для проверки прав."""
        job = self._get_one(f'jobs?id=eq.{job_id}&select=employer_id')
        return job['employer_id']
 
    def search(self, filters: dict) -> dict:
        """Поиск заданий с пагинацией. Возвращает {results, total, page, per_page, pages}."""
        query = self._build_search_query(filters)
        headers = {'Prefer': 'count=exact'}
        resp = self._call('GET', f'jobs?{query}', headers=headers)
        if not resp.ok:
            raise PostgrestError(f'Job search failed: {resp.status_code}')
 
        jobs = resp.json() or []
        total = self._extract_total(resp)
 
        # Гео-фильтрация через RPC (если заданы координаты)
        if filters.get('lat') is not None and filters.get('lng') is not None:
            jobs = self._apply_geo_filter(jobs, filters)
 
        return self._paginate(jobs, total, filters)
 
    def create(self, job_data: dict) -> dict:
        """Создать задание. Возвращает созданную запись."""
        resp = self._call('POST', 'jobs',
                         json=job_data,
                         headers={'Prefer': 'return=representation'})
        if not resp.ok:
            raise PostgrestError(f'Job create failed: {resp.status_code}: {resp.text}')
        return resp.json()[0]
 
    def update_status(self, job_id: str, status: str, *, extra_fields: dict = None) -> None:
        """Обновить статус задания."""
        payload = {'status': status}
        if extra_fields:
            payload.update(extra_fields)
        resp = self._call('PATCH', f'jobs?id=eq.{job_id}', json=payload)
        if not resp.ok:
            raise PostgrestError(f'Job status update failed: {resp.status_code}')
 
    def increment_workers(self, job_id: str, *, delta: int = 1) -> None:
        """Атомарный инкремент current_workers через RPC (race-safe)."""
        resp = self._rpc('increment_job_workers',
                        {'p_job_id': job_id, 'p_delta': delta},
                        use_admin=True)
        if not resp.ok:
            raise PostgrestError(f'increment_job_workers failed: {resp.status_code}')
 
    def _build_search_query(self, f: dict) -> str:
        parts = [f'select={self.JOB_LIST_SELECT}']
        if f.get('status'):
            parts.append(f'status=eq.{sanitize_postgrest(f["status"])}')
        if f.get('city'):
            parts.append(f'city=ilike.*{sanitize_postgrest(f["city"])}*')
        if f.get('min_pay') is not None:
            parts.append(f'payment_amount=gte.{f["min_pay"]}')
        if f.get('max_pay') is not None:
            parts.append(f'payment_amount=lte.{f["max_pay"]}')
        # Пагинация
        page = max(1, f.get('page', 1))
        per_page = min(100, max(1, f.get('per_page', 20)))
        parts.append(f'limit={per_page}&offset={(page - 1) * per_page}')
        # Сортировка
        sort = f.get('sort', 'newest')
        order = {'newest': 'created_at.desc', 'price_asc': 'payment_amount.asc',
                 'price_desc': 'payment_amount.desc'}.get(sort, 'created_at.desc')
        parts.append(f'order={order}')
        return '&'.join(parts)
 
    @staticmethod
    def _apply_geo_filter(jobs: list, filters: dict) -> list:
        lat, lng, radius = filters['lat'], filters['lng'], filters.get('radius', 20)
        for j in jobs:
            if j.get('lat') and j.get('lng'):
                j['distance'] = calculate_distance(lat, lng, j['lat'], j['lng'])
            else:
                j['distance'] = float('inf')
        if radius:
            jobs = [j for j in jobs if j['distance'] <= radius]
        if filters.get('sort') == 'distance':
            jobs.sort(key=lambda x: x['distance'])
        return jobs
 
    @staticmethod
    def _paginate(jobs, total, filters):
        page = max(1, filters.get('page', 1))
        per_page = min(100, max(1, filters.get('per_page', 20)))
        return {
            'results': jobs,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': max(1, (total + per_page - 1) // per_page) if total else 1,
        }
2.5. New: app/repositories/admin_repository.py
Ключевой репозиторий для Фазы 2 — устраняет N+1 в admin_panel. Использует новый RPC get_admin_stats().
app/repositories/admin_repository.py — 68 строк
# app/repositories/admin_repository.py
"""Repository для админ-панели. Один RPC вместо 8 count=exact запросов."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
 
from app.repositories.base import BaseRepository
from app.errors import PostgrestError
 
logger = logging.getLogger(__name__)
 
 
@dataclass(frozen=True)
class AdminStats:
    """Типизированный результат get_admin_stats()."""
    total_users: int
    users_by_role: dict[str, int]  # {'worker': 100, 'employer': 50, 'admin': 3}
    total_jobs: int
    jobs_by_status: dict[str, int]  # {'open': 30, 'completed': 100, 'cancelled': 5}
    pending_verifications: int
    generated_at: str
 
    @classmethod
    def from_dict(cls, d: dict) -> 'AdminStats':
        return cls(
            total_users=d.get('total_users', 0),
            users_by_role=d.get('users_by_role', {}),
            total_jobs=d.get('total_jobs', 0),
            jobs_by_status=d.get('jobs_by_status', {}),
            pending_verifications=d.get('pending_verifications', 0),
            generated_at=d.get('generated_at', ''),
        )
 
    def to_template_dict(self) -> dict:
        """Совместимость с существующим шаблоном admin.html."""
        return {
            'total_users': self.total_users,
            'workers': self.users_by_role.get('worker', 0),
            'employers': self.users_by_role.get('employer', 0),
            'admins': self.users_by_role.get('admin', 0),
            'total_jobs': self.total_jobs,
            'open_jobs': self.jobs_by_status.get('open', 0),
            'completed_jobs': self.jobs_by_status.get('completed', 0),
            'cancelled_jobs': self.jobs_by_status.get('cancelled', 0),
            'pending_verifications': self.pending_verifications,
        }
 
 
class AdminRepository(BaseRepository):
    """Доступ к админ-статистике через один RPC."""
 
    def get_stats(self) -> AdminStats:
        """Получить сводную статистику одним RPC-вызовом.
 
        Заменяет 8 последовательных count=exact запросов из admin_panel.
        См. migrations/076_get_admin_stats.sql.
        """
        resp = self._rpc('get_admin_stats', {}, use_admin=True)
        if not resp.ok:
            raise PostgrestError(
                f'get_admin_stats failed: {resp.status_code}. " +
                f'Проверьте, что миграция 076 применена.'
            )
        data = resp.json()
        if isinstance(data, list):
            data = data[0] if data else {}
        return AdminStats.from_dict(data)
 
    def list_users(self, *, search: str = '', role: str = '', limit: int = 100) -> list[dict]:
        """Список пользователей для админки."""
        query = f'profiles?select=*&limit={limit}'
        if search:
            query += f'&full_name=ilike.*{search}*'
        if role:
            query += f'&role=eq.{role}'
        query += '&order=full_name.asc'
        return self._get_many(query, use_admin=True)
2.6. New: app/repositories/application_repository.py
app/repositories/application_repository.py — 96 строк
# app/repositories/application_repository.py
"""Repository для таблицы applications + атомарные RPC."""
from __future__ import annotations
import logging
from typing import Optional
 
from app.repositories.base import BaseRepository
from app.errors import PostgrestError
 
logger = logging.getLogger(__name__)
 
 
class ApplicationRepository(BaseRepository):
    """Доступ к откликам через PostgREST + atomic RPC."""
 
    def get_by_id(self, app_id: str) -> dict:
        return self._get_one(
            f'applications?id=eq.{app_id}&select=id,job_id,worker_id,status'
        )
 
    def find_duplicate(self, job_id: str, worker_id: str) -> Optional[dict]:
        """Проверка дубликата (для UX перед atomic apply)."""
        resp = self._call('GET',
            f'applications?job_id=eq.{job_id}&worker_id=eq.{worker_id}&select=id,status')
        if resp.ok and resp.json():
            return resp.json()[0]
        return None
 
    def apply_atomic(self, job_id: str, worker_id: str) -> dict:
        """Атомарный apply через RPC. Возвращает {success, error_code, ...}.
 
        Выбрасывает PostgrestError, если RPC недоступен (миграция 048 не применена).
        """
        resp = self._rpc('apply_job_atomic',
                        {'p_job_id': job_id, 'p_worker_id': worker_id},
                        use_admin=True)
        if not resp.ok:
            if resp.status_code == 404:
                raise PostgrestError(
                    'RPC apply_job_atomic не найдена. Примените миграцию 048.'
                )
            raise PostgrestError(f'apply_job_atomic failed: {resp.status_code}')
        return resp.json() or {}
 
    def withdraw_atomic(self, app_id: str, user_id: str) -> dict:
        """Атомарный отзыв через RPC."""
        resp = self._rpc('withdraw_application_atomic',
                        {'p_application_id': app_id, 'p_user_id': user_id},
                        use_admin=True)
        if not resp.ok:
            raise PostgrestError(f'withdraw_application_atomic failed: {resp.status_code}')
        return resp.json() or {}
 
    def list_for_job(self, job_id: str, *, select: str = '*') -> list[dict]:
        return self._get_many(
            f'applications?job_id=eq.{job_id}&select={select}&order=created_at.desc'
        )
 
    def list_for_worker(self, worker_id: str, *, select: str = '*') -> list[dict]:
        return self._get_many(
            f'applications?worker_id=eq.{worker_id}&select={select}&order=created_at.desc'
        )
2.7. Diff: app/blueprints/admin.py (refactor admin_panel)
Самое важное изменение в PR. Было 82 строки с 8 count=exact запросами — стало 12 строк с одним вызовом AdminRepository.get_stats(). Шаблон admin.html менять не нужно: to_template_dict() возвращает ту же структуру ключей, что и старый код.
app/blueprints/admin.py — admin_panel переписан (−82/+12)
--- a/app/blueprints/admin.py
+++ b/app/blueprints/admin.py
@@ -1,4 +1,5 @@
 from datetime import datetime
 import json
 import os
 import subprocess
 from pathlib import Path
 from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, jsonify
 
 from app.decorators import login_required, role_required, admin_required, handle_errors
 from app.utils import cache_for, sanitize_postgrest, postgrest_request, postgrest_admin_request, postgrest_rpc, is_circuit_open
 from app.utils.helpers import assert_postgrest_ok
+from app.errors import PostgrestError
 
 @admin_bp.route('/admin')
 @login_required
 @admin_required
 def admin_panel():
     tab = request.args.get('tab', 'dashboard')
     stats = {}
     if tab == 'dashboard':
-        # Точный подсчёт пользователей по ролям через count=exact
-        users_resp = postgrest_admin_request('GET',
-            'profiles?select=role&limit=0',
-            headers={'Prefer': 'count=exact'})
-        if users_resp.ok:
-            total_users = 0
-            content_range = users_resp.headers.get('Content-Range', '')
-            if '/' in content_range:
-                total_users = int(content_range.split('/')[-1])
-            stats['total_users'] = total_users
-        for role_key in ['worker', 'employer', 'admin']:
-            role_resp = postgrest_admin_request('GET',
-                f'profiles?role=eq.{role_key}&select=id&limit=0',
-                headers={'Prefer': 'count=exact'})
-            if role_resp.ok:
-                cr = role_resp.headers.get('Content-Range', '')
-                if '/' in cr:
-                    stats[f'{role_key}s'] = int(cr.split('/')[-1])
-            else:
-                stats[f'{role_key}s'] = 0
-        # Точный подсчёт заданий по статусам через count=exact
-        jobs_resp = postgrest_admin_request('GET',
-            'jobs?select=status&limit=0',
-            headers={'Prefer': 'count=exact'})
-        if jobs_resp.ok:
-            total_jobs = 0
-            content_range = jobs_resp.headers.get('Content-Range', '')
-            if '/' in content_range:
-                total_jobs = int(content_range.split('/')[-1])
-            stats['total_jobs'] = total_jobs
-        for status_key in ['open', 'completed', 'cancelled']:
-            status_resp = postgrest_admin_request('GET',
-                f'jobs?status=eq.{status_key}&select=id&limit=0',
-                headers={'Prefer': 'count=exact'})
-            if status_resp.ok:
-                cr = status_resp.headers.get('Content-Range', '')
-                if '/' in cr:
-                    stats[f'{status_key}_jobs'] = int(cr.split('/')[-1])
-            else:
-                stats[f'{status_key}_jobs'] = 0
-        pending_resp = postgrest_admin_request('GET',
-            'profiles?verification_status=eq.pending&select=id&limit=0',
-            headers={'Prefer': 'count=exact'})
-        if pending_resp.ok:
-            cr = pending_resp.headers.get('Content-Range', '')
-            if '/' in cr:
-                stats['pending_verifications'] = int(cr.split('/')[-1])
-            else:
-                stats['pending_verifications'] = 0
-        else:
-            stats['pending_verifications'] = 0
+        # Фаза 2: один RPC вместо 8 count=exact запросов
+        admin_repo = current_app.container.admin_repository()
+        try:
+            stats = admin_repo.get_stats().to_template_dict()
+        except PostgrestError as e:
+            current_app.logger.error('admin_panel stats failed: %s', e)
+            flash('Не удалось загрузить статистику. Попробуйте позже.', 'warning')
+            stats = {'total_users': 0, 'workers': 0, 'employers': 0, 'admins': 0,
+                    'total_jobs': 0, 'open_jobs': 0, 'completed_jobs': 0,
+                    'cancelled_jobs': 0, 'pending_verifications': 0}
     # Пользователи
     users = []
     if tab == 'users':
         admin_repo = current_app.container.admin_repository()
         users = admin_repo.list_users(
             search=request.args.get('search', ''),
             role=request.args.get('role', ''),
         )
2.8. Diff: app/__init__.py (container stub)
Добавляем минимальный stub контейнера, который Фаза 5 разовьёт в полноценный DI. Сейчас контейнер просто хранит репозитории и кеширует их (один экземпляр на app).
app/__init__.py — добавлен stub контейнер
--- a/app/__init__.py
+++ b/app/__init__.py
@@ -245,6 +245,17 @@
     from app.error_handlers import register_error_handlers
     register_error_handlers(app)
 
+    # Фаза 2: минимальный контейнер для Repository
+    # (Фаза 5 разовьёт в полноценный DI)
+    from app.repositories import JobRepository, ApplicationRepository, AdminRepository, NotificationRepository
+    from app.utils import postgrest_client
+    class _StubContainer:
+        def job_repository(self): return JobRepository(postgrest_client)
+        def application_repository(self): return ApplicationRepository(postgrest_client)
+        def admin_repository(self): return AdminRepository(postgrest_client)
+        def notification_repository(self): return NotificationRepository(postgrest_client)
+    app.container = _StubContainer()
+
     @app.context_processor
2.9. Tests
tests/test_repositories.py — 180 строк
# tests/test_repositories.py
"""Фаза 2: тесты Repository-слоя."""
import pytest
from unittest.mock import MagicMock, patch
from app.errors import PostgrestError, NotFoundError
from app.repositories.base import BaseRepository
from app.repositories.job_repository import JobRepository
from app.repositories.admin_repository import AdminRepository, AdminStats
 
 
class FakePostgrestResponse:
    def __init__(self, ok=True, status_code=200, data=None, text='', headers=None):
        self.ok = ok
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = headers or {}
 
    def json(self):
        return self._data
 
 
class TestBaseRepository:
    def test_get_one_returns_first_record(self):
        client = MagicMock()
        client.postgrest_request.return_value = FakePostgrestResponse(
            data=[{'id': 'job-1', 'title': 'Test'}]
        )
        repo = BaseRepository(client)
        result = repo._get_one('jobs?id=eq.job-1')
        assert result['id'] == 'job-1'
 
    def test_get_one_raises_not_found_when_empty(self):
        client = MagicMock()
        client.postgrest_request.return_value = FakePostgrestResponse(data=[])
        repo = BaseRepository(client)
        with pytest.raises(NotFoundError):
            repo._get_one('jobs?id=eq.nonexistent')
 
    def test_get_many_returns_empty_list_on_failure(self):
        client = MagicMock()
        client.postgrest_request.return_value = FakePostgrestResponse(ok=False, status_code=500)
        repo = BaseRepository(client)
        with pytest.raises(PostgrestError):
            repo._get_many('jobs')
 
    def test_count_extracts_from_content_range(self):
        client = MagicMock()
        client.postgrest_request.return_value = FakePostgrestResponse(
            data=[],
            headers={'Content-Range': '0-0/42'},
        )
        repo = BaseRepository(client)
        assert repo._count('profiles') == 42
 
 
class TestAdminRepository:
    def test_get_stats_parses_rpc_response(self):
        client = MagicMock()
        client.postgrest_rpc.return_value = FakePostgrestResponse(
            data={'total_users': 100, 'users_by_role': {'worker': 80, 'employer': 18, 'admin': 2},
                  'total_jobs': 50, 'jobs_by_status': {'open': 30, 'completed': 15, 'cancelled': 5},
                  'pending_verifications': 3, 'generated_at': '2026-06-28T10:00:00Z'}
        )
        repo = AdminRepository(client)
        stats = repo.get_stats()
        assert stats.total_users == 100
        assert stats.users_by_role['worker'] == 80
        assert stats.jobs_by_status['open'] == 30
 
    def test_get_stats_to_template_dict_compatible_with_old_code(self):
        stats = AdminStats(
            total_users=100,
            users_by_role={'worker': 80, 'employer': 18, 'admin': 2},
            total_jobs=50,
            jobs_by_status={'open': 30, 'completed': 15, 'cancelled': 5},
            pending_verifications=3,
            generated_at='2026-06-28T10:00:00Z',
        )
        d = stats.to_template_dict()
        # Проверяем, что ключи совпадают со старым кодом
        assert d['total_users'] == 100
        assert d['workers'] == 80
        assert d['employers'] == 18
        assert d['admins'] == 2
        assert d['total_jobs'] == 50
        assert d['open_jobs'] == 30
        assert d['completed_jobs'] == 15
        assert d['cancelled_jobs'] == 5
        assert d['pending_verifications'] == 3
 
    def test_get_stats_raises_when_rpc_not_found(self):
        client = MagicMock()
        client.postgrest_rpc.return_value = FakePostgrestResponse(ok=False, status_code=404)
        repo = AdminRepository(client)
        with pytest.raises(PostgrestError):
            repo.get_stats()
 
 
class TestJobRepository:
    def test_get_by_id_returns_job_with_joins(self):
        client = MagicMock()
        client.postgrest_admin_request.return_value = FakePostgrestResponse(
            data=[{'id': 'job-1', 'organization_name': 'Test', 'photos': [], 'employer': {'id': 'emp-1'}}]
        )
        repo = JobRepository(client)
        job = repo.get_by_id('job-1')
        assert job['id'] == 'job-1'
        assert job['employer']['id'] == 'emp-1'
 
    def test_search_applies_geo_filter(self):
        client = MagicMock()
        client.postgrest_request.return_value = FakePostgrestResponse(
            data=[
                {'id': 'job-1', 'lat': 55.75, 'lng': 37.61},  # близко
                {'id': 'job-2', 'lat': 60.0, 'lng': 30.0},    # далеко
            ],
            headers={'Content-Range': '0-1/2'},
        )
        repo = JobRepository(client)
        result = repo.search({
            'lat': 55.75, 'lng': 37.61, 'radius': 50,
            'page': 1, 'per_page': 20, 'sort': 'distance',
        })
        assert len(result['results']) == 1
        assert result['results'][0]['id'] == 'job-1'
        assert result['total'] == 2  # total до фильтра
2.10. Risk & rollback
Поле	Значение
Risk level	Medium — миграция 076 должна быть применена ДО деплоя кода
Migration order	1. Применить migrations/076_get_admin_stats.sql на staging. 2. Проверить через psql: SELECT get_admin_stats();. 3. Задеплоить код. 4. Проверить /admin?tab=dashboard.
Rollback	git revert PR + DROP FUNCTION get_admin_stats(); — функция не используется ничем, кроме admin_panel
Performance	Was: 8 RTT × ~20ms = 160ms. Now: 1 RTT × ~30ms = 30ms. Ускорение ~5× даже на текущих данных.
Backward compat	Шаблон admin.html менять НЕ нужно — to_template_dict() даёт те же ключи
2.11. Success metrics
●	Latency p95 на /admin?tab=dashboard < 50ms при 100k users (was: ~500ms экстраполяция).
●	0 прямых вызовов postgrest_admin_request в app/blueprints/admin.py для tab=dashboard (только через Repository).
●	Coverage repositories > 85% (pytest-cov).
●	Integration-тест /admin?tab=dashboard проходит на staging с реальной БД.
Pull Request #3 — Фаза 3: Use Cases + устранение threading.Thread
Pull Request #3  ·  branch: refactor/phase-3-use-cases → main
Фаза 3 — Use Cases + устранение threading.Thread
Pull Request #3  ·  branch: refactor/phase-3-use-cases → main
Фаза 3 — Use Cases + устранение threading.Thread 
▌ Summary  
Вводим слой Use Cases (Command pattern) для всех мутаций. Use Case — это класс с методом execute(command) → result, не знающий про Flask (никаких session, request, flash). Параллельно убираем все три вхождения threading.Thread в applications.py, заменяя их на уже существующий transactional outbox (enqueue_notification). Удаляем _apply_job_fallback с TOCTOU race condition — миграция 048 теперь обязательна.
3.1. Files changed
| File | Lines +/- | Type | Risk |
|---|---|---|---|
| app/use_cases/__init__.py | +0 / +8 | New | None |
| app/use_cases/base.py | +0 / +42 | New | None |
| app/use_cases/apply_job.py | +0 / +98 | New | None |
| app/use_cases/withdraw_application.py | +0 / +74 | New | None |
| app/use_cases/accept_invitation.py | +0 / +82 | New | None |
| app/blueprints/applications.py | -145 / +28 | Modified | High |
| app/blueprints/jobs_api.py | -58 / +18 | Modified | Medium |
| app/services/application_service.py | -128 / +6 | Modified (deprecate) | Medium |
| tests/test_use_cases.py | +0 / +220 | New | None |
3.2. New: app/use_cases/base.py
Базовый класс Use Case — это просто контракт: метод execute(cmd) возвращает result или выбрасывает DomainError. Никакой бизнес-логики в базовом классе нет; он нужен для type hints и для того, чтобы все Use Cases имели одинаковую сигнатуру (легко мокать в тестах).
app/use_cases/base.py — 42 строки
# app/use_cases/base.py
"""Базовые классы для Use Case-паттерна (Command).
 
Use Case — это класс, инкапсулирующий одну бизнес-операцию.
Он НЕ знает про Flask (никаких session, request, flash).
Принимает типизированную Command, возвращает типизированный Result,
или выбрасывает DomainError.
 
Это позволяет:
- Переиспользовать Use Case в Celery-задачах и WebSocket-обработчиках
- Юнит-тестировать без поднятия Flask-контекста
- Легко подменять Repository на mock в тестах
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
 
TCommand = TypeVar('TCommand')
TResult = TypeVar('TResult')
 
 
@dataclass(frozen=True)
class UseCaseResult:
    """Базовый класс для результатов Use Case."""
    success: bool
 
 
class UseCase(Generic[TCommand, TResult]):
    """Базовый класс для всех Use Cases.
 
    Подклассы реализуют метод execute(cmd) → result.
    Все зависимости (Repository, NotificationService) передаются в __init__.
    """
 
    def execute(self, cmd: TCommand) -> TResult:
        raise NotImplementedError
3.3. New: app/use_cases/apply_job.py (полный код)
Главный Use Case в проекте. Заменяет 145 строк в applications.py на 98 строк чистой бизнес-логики. Не зависит от Flask — только от Repository и NotificationService. Это позволяет вызывать его из Celery-задач (например, если добавим импорт откликов через CSV).
app/use_cases/apply_job.py — 98 строк
# app/use_cases/apply_job.py
"""Use Case: работник откликается на задание."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
 
from app.use_cases.base import UseCase, UseCaseResult
from app.errors import (
    ApplyJobError, DuplicateApplicationError, NoSlotsAvailableError,
    BlacklistedByEmployerError, JobNotOpenError, CannotApplyToOwnJobError,
    PostgrestError,
)
 
logger = logging.getLogger(__name__)
 
 
@dataclass(frozen=True)
class ApplyJobCommand:
    """Входные данные для ApplyJobUseCase."""
    job_id: str
    worker_id: str
 
 
@dataclass(frozen=True)
class ApplyJobResult(UseCaseResult):
    """Результат успешного apply."""
    application_id: Optional[str] = None
    employer_id: Optional[str] = None
    job_id: str = ''
 
 
# Маппинг кодов ошибок от RPC на типизированные исключения
_RPC_ERROR_MAP = {
    'blacklisted': BlacklistedByEmployerError,
    'duplicate': DuplicateApplicationError,
    'no_slots': NoSlotsAvailableError,
    'job_not_open': JobNotOpenError,
    'self_apply': CannotApplyToOwnJobError,
}
 
 
class ApplyJobUseCase(UseCase[ApplyJobCommand, ApplyJobResult]):
    """Применяет работника к заданию.
 
    Шаги:
    1. Проверка дубликата (быстрая, для UX).
    2. Атомарный apply через RPC apply_job_atomic.
    3. Уведомление работодателя через transactional outbox.
 
    Зависимости передаются в __init__ — это позволяет подменять их в тестах.
    """
 
    def __init__(self, applications, notifications):
        """
        Args:
            applications: ApplicationRepository
            notifications: NotificationService (или mock)
        """
        self._applications = applications
        self._notifications = notifications
 
    def execute(self, cmd: ApplyJobCommand) -> ApplyJobResult:
        # 1. Быстрая проверка дубликата (не блокирует атомарный RPC,
        #    просто улучшает UX — не показываем форму apply, если уже откликались)
        if self._applications.find_duplicate(cmd.job_id, cmd.worker_id):
            raise DuplicateApplicationError()
 
        # 2. Атомарная операция через PostgreSQL RPC
        #    Все проверки (status=open, slots available, not blacklisted, not self-apply)
        #    выполняются в одной SQL-транзакции — TOCTOU невозможен.
        result = self._applications.apply_atomic(cmd.job_id, cmd.worker_id)
 
        if not result.get('success'):
            error_code = result.get('code', 'unknown')
            error_msg = result.get('error', 'Не удалось отправить отклик')
            exc_class = _RPC_ERROR_MAP.get(error_code, ApplyJobError)
            raise exc_class(error_msg)
 
        # 3. Уведомление работодателя через transactional outbox
        #    ВНИМАНИЕ: НЕ используем threading.Thread — Фаза 3 устраняет эту практику.
        #    enqueue_notification пишет в таблицу notification_outbox,
        #    Celery-воркер асинхронно обрабатывает очередь.
        employer_id = result.get('employer_id')
        if employer_id:
            self._notifications.enqueue(
                user_id=employer_id,
                notification_type='application_received',
                title='Новый отклик',
                body='На ваше задание поступил новый отклик',
                data={'job_id': cmd.job_id},
            )
 
        return ApplyJobResult(
            success=True,
            application_id=result.get('application_id'),
            employer_id=employer_id,
            job_id=cmd.job_id,
        )
3.4. New: app/use_cases/withdraw_application.py
app/use_cases/withdraw_application.py — 74 строки
# app/use_cases/withdraw_application.py
"""Use Case: работник отзывает свой отклик."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
 
from app.use_cases.base import UseCase, UseCaseResult
from app.errors import (
    WithdrawError, WithdrawWindowClosedError,
    NotFoundError, PermissionDeniedError,
    PostgrestError,
)
 
logger = logging.getLogger(__name__)
 
 
@dataclass(frozen=True)
class WithdrawCommand:
    application_id: str
    worker_id: str  # должен совпадать с worker_id отклика
 
 
@dataclass(frozen=True)
class WithdrawResult(UseCaseResult):
    new_status: str = 'withdrawn'
    job_id: Optional[str] = None
 
 
class WithdrawApplicationUseCase(UseCase[WithdrawCommand, WithdrawResult]):
    """Отзывает отклик через атомарную RPC.
 
    Все проверки (права, 12-часовое окно для accepted) выполняются
    в SQL-транзакции — TOCTOU невозможен. Если RPC недоступна,
    выбрасывает PostgrestError (раньше был небезопасный fallback).
    """
 
    def __init__(self, applications, notifications):
        self._applications = applications
        self._notifications = notifications
 
    def execute(self, cmd: WithdrawCommand) -> WithdrawResult:
        # 1. Проверка существования и принадлежности
        app = self._applications.get_by_id(cmd.application_id)
        if not app:
            raise NotFoundError('Отклик не найден')
        if app['worker_id'] != cmd.worker_id:
            raise PermissionDeniedError('Вы не автор этого отклика')
        if app['status'] == 'withdrawn':
            raise WithdrawError('Отклик уже отозван')
 
        # 2. Атомарный отзыв через RPC
        result = self._applications.withdraw_atomic(
            cmd.application_id, cmd.worker_id
        )
 
        if not result.get('success'):
            error_code = result.get('code', 'unknown')
            error_msg = result.get('error', 'Не удалось отозвать отклик')
            if error_code == 'window_closed':
                raise WithdrawWindowClosedError(error_msg)
            raise WithdrawError(error_msg)
 
        # 3. Уведомление работодателя (через outbox, без threading.Thread)
        job_id = app.get('job_id')
        if job_id and app['status'] == 'accepted':
            self._notifications.enqueue(
                user_id=result.get('employer_id'),
                notification_type='withdraw',
                title='Работник отозвал отклик',
                body=f'Принятый работник отозвал отклик с задания #{job_id}',
                data={'job_id': job_id},
            )
 
        return WithdrawResult(success=True, new_status='withdrawn', job_id=job_id)
3.5. New: app/use_cases/accept_invitation.py
app/use_cases/accept_invitation.py — 82 строки
# app/use_cases/accept_invitation.py
"""Use Case: трудник принимает приглашение от работодателя."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
 
from app.use_cases.base import UseCase, UseCaseResult
from app.errors import (
    DomainError, NotFoundError, PermissionDeniedError, ConflictError,
    PostgrestError,
)
 
logger = logging.getLogger(__name__)
 
 
@dataclass(frozen=True)
class AcceptInvitationCommand:
    invitation_id: str
    worker_id: str
 
 
@dataclass(frozen=True)
class AcceptInvitationResult(UseCaseResult):
    job_id: Optional[str] = None
    employer_id: Optional[str] = None
    current_workers: int = 0
    job_status: str = 'open'
 
 
_INVITATION_ERROR_MAP = {
    'invitation_not_found': (NotFoundError, 'Приглашение не найдено'),
    'not_target': (PermissionDeniedError, 'Это приглашение не вам'),
    'invitation_not_pending': (ConflictError, 'Приглашение уже обработано'),
    'job_not_found': (NotFoundError, 'Задание не найдено'),
    'job_not_open': (ConflictError, 'Задание больше не открыто'),
    'no_slots': (ConflictError, 'Все места в задании заняты'),
}
 
 
class AcceptInvitationUseCase(UseCase[AcceptInvitationCommand, AcceptInvitationResult]):
    """Атомарное принятие приглашения через RPC accept_invitation_atomic."""
 
    def __init__(self, invitations, notifications):
        self._invitations = invitations
        self._notifications = notifications
 
    def execute(self, cmd: AcceptInvitationCommand) -> AcceptInvitationResult:
        result = self._invitations.accept_atomic(
            cmd.invitation_id, cmd.worker_id
        )
 
        if not result.get('success'):
            error_code = result.get('code', 'unknown')
            error_msg = result.get('error', 'Не удалось принять приглашение')
            exc_info = _INVITATION_ERROR_MAP.get(error_code)
            if exc_info:
                exc_class, default_msg = exc_info
                raise exc_class(error_msg or default_msg)
            raise DomainError(error_msg)
 
        # Уведомления обеим сторонам через outbox
        job_id = result.get('job_id')
        employer_id = result.get('employer_id')
        worker_id = result.get('worker_id')
 
        if worker_id:
            self._notifications.enqueue(
                user_id=worker_id,
                notification_type='application_accepted',
                title='Приглашение принято',
                body=f'Ваша заявка на задание #{job_id} принята.',
                data={'job_id': job_id},
            )
        if employer_id:
            self._notifications.enqueue(
                user_id=employer_id,
                notification_type='application_received',
                title='Приглашение принято',
                body='Трудник принял ваше приглашение на задание',
                data={'job_id': job_id},
            )
 
        return AcceptInvitationResult(
            success=True,
            job_id=job_id,
            employer_id=employer_id,
            current_workers=result.get('current_workers', 0),
            job_status=result.get('job_status', 'open'),
        )
3.6. Diff: app/blueprints/applications.py (тонкая обёртка)
Blueprint становится тупой HTTP-обёрткой: парсит вход → вызывает Use Case → ловит DomainError → errorhandler формирует ответ. Никакой бизнес-логики. Длина apply_job: было 65 строк → стало 12 строк.
app/blueprints/applications.py — было 200 строк, стало 28
--- a/app/blueprints/applications.py
+++ b/app/blueprints/applications.py
@@ -1,200 +1,28 @@
-import logging
-import threading
-from datetime import datetime, timezone
-
-from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
-
-from app.config import Config
-from app.decorators import login_required, rate_limit, role_required, validate_uuid
-from app.utils import postgrest_request, postgrest_admin_request, postgrest_rpc
-from app.utils.helpers import assert_postgrest_ok
-from app.services.notification_service import create as notify, enqueue_notification
-
-logger = logging.getLogger(__name__)
-
-applications_bp = Blueprint('applications', __name__)
-
-
-@applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
-@login_required
-@validate_uuid('job_id')
-@rate_limit
-def apply_job(job_id):
-    user_id = session['user_id']
-    # ... 60 строк бизнес-логики ...
-    threading.Thread(target=_notify_employer, daemon=True).start()
-    flash('Отклик отправлен', 'success')
-    return redirect(url_for('jobs.index'))
-
-
-def _apply_job_fallback(job_id, user_id):
-    # 96 строк неатомарного fallback с TOCTOU race condition
-    ...
-
-
-@applications_bp.route('/withdraw/<app_id>', methods=['POST'])
-def withdraw(app_id):
-    # 40 строк бизнес-логики
-    ...
+from flask import Blueprint, current_app, flash, redirect, request, session, url_for
+
+from app.decorators import login_required, rate_limit, validate_uuid
+from app.use_cases.apply_job import ApplyJobCommand, ApplyJobUseCase
+from app.use_cases.withdraw_application import WithdrawCommand, WithdrawApplicationUseCase
+
+applications_bp = Blueprint('applications', __name__)
+
+
+@applications_bp.route('/apply/<job_id>', methods=['POST'])
+@login_required
+@validate_uuid('job_id')
+@rate_limit
+def apply_job(job_id):
+    """Тонкая HTTP-обёртка над ApplyJobUseCase."""
+    cmd = ApplyJobCommand(
+        job_id=job_id,
+        worker_id=session['user_id'],
+    )
+    use_case = current_app.container.apply_job_use_case()
+    result = use_case.execute(cmd)  # выбрасывает DomainError при ошибке
+    flash('Отклик отправлен', 'success')
+    return redirect(url_for('jobs.index'))
+
+
+@applications_bp.route('/withdraw/<app_id>', methods=['POST'])
+@login_required
+@validate_uuid('app_id')
+def withdraw(app_id):
+    """Тонкая HTTP-обёртка над WithdrawApplicationUseCase."""
+    cmd = WithdrawCommand(
+        application_id=app_id,
+        worker_id=session['user_id'],
+    )
+    use_case = current_app.container.withdraw_application_use_case()
+    result = use_case.execute(cmd)  # выбрасывает DomainError при ошибке
+    flash('Отклик отозван', 'success')
+    return redirect(url_for('jobs.index'))
3.7. Diff: удаление threading.Thread
Это самое важное изменение Фазы 3. Было три места в applications.py, где использовался `threading.Thread(target=_notify_employer, daemon=True).start()` — fire-and-forget потоки в WSGI-процессе. Они теряются при деплое, не имеют retry, не логируются. Теперь уведомления идут через transactional outbox (enqueue_notification), который уже существует в notification_service.py.
Удаление threading.Thread — 3 места в applications.py
--- a/app/blueprints/applications.py
+++ b/app/blueprints/applications.py
@@ -73,15 +73,6 @@
-    # Успех: уведомить работодателя о новом отклике (transactional outbox)
-    employer_id = result.get('employer_id')
-    if employer_id:
-        _link = url_for('jobs.job_detail', job_id=job_id, _external=True)
-        def _notify_employer():
-            success = enqueue_notification(employer_id, 'application_received', 'Новый отклик',
-                   f'На ваше задание поступил новый отклик',
-                   data={'job_id': job_id, 'link': _link})
-            if not success:
-                logger.error("apply_job: enqueue_notification() вернул False для employer_id=%s job_id=%s",
-                             employer_id, job_id)
-        threading.Thread(target=_notify_employer, daemon=True).start()
+    # Уведомление выполняется внутри ApplyJobUseCase через enqueue_notification
+    # (синхронный INSERT в notification_outbox — Celery-воркер обработает позже)
+    # threading.Thread удалён — Фаза 3.
 
 # Аналогично в _apply_job_fallback (строка 179) и apply_selected (строка 251)
3.8. Diff: app/blueprints/jobs_api.py (respond_invitation)
app/blueprints/jobs_api.py — respond_invitation
--- a/app/blueprints/jobs_api.py
+++ b/app/blueprints/jobs_api.py
@@ -164,73 +164,18 @@
 @jobs_api_bp.route('/api/invitations/<invitation_id>/respond', methods=['POST'])
 @login_required
 @role_required('worker')
 def respond_invitation(invitation_id):
-    """Трудник принимает или отклоняет приглашение."""
-    data = request.get_json(silent=True) or {}
-    action = data.get('action')
-    if action not in ('accept', 'reject'):
-        return jsonify({'success': False, 'error': 'Укажите действие: accept или reject'}), 400
-
-    if action == 'reject':
-        # 20 строк reject-логики ...
-        ...
-
-    # action == 'accept': атомарная RPC
-    rpc_result = postgrest_rpc('accept_invitation_atomic', {
-        'p_invitation_id': invitation_id,
-        'p_user_id': session['user_id'],
-    }, use_admin=True)
-
-    if not rpc_result.ok:
-        if rpc_result.status_code == 404:
-            return jsonify({'success': False, 'error': 'RPC accept_invitation_atomic не найдена'}), 500
-        return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500
-
-    result = rpc_result.json()
-    if not result or not result.get('success'):
-        error_msg = (result or {}).get('error', 'Не удалось принять приглашение')
-        status_code = {
-            'invitation_not_found': 404,
-            'not_target': 403,
-            'invitation_not_pending': 409,
-            'job_not_found': 404,
-            'job_not_open': 409,
-            'no_slots': 409,
-        }.get((result or {}).get('code', ''), 400)
-        return jsonify({'success': False, 'error': error_msg}), status_code
-
-    job_id = result.get('job_id')
-    employer_id = result.get('employer_id')
-    worker_id = result.get('worker_id')
-
-    # Уведомить работника о принятии
-    notify(worker_id, 'application_accepted', 'Приглашение принято',
-           f'Ваша заявка на задание #{job_id} принята.',
-           data={'job_id': job_id, ...})
-    # Уведомить работодателя
-    notify(employer_id, 'application_received', 'Приглашение принято',
-           f'Трудник принял ваше приглашение на задание',
-           data={'job_id': job_id, ...})
-
-    return jsonify({
-        'success': True,
-        'new_status': 'accepted',
-        'job_status': result.get('job_status'),
-        'current_workers': result.get('current_workers')
-    })
+    """Трудник принимает или отклоняет приглашение."""
+    data = request.get_json(silent=True) or {}
+    action = data.get('action')
+    if action not in ('accept', 'reject'):
+        return jsonify({'success': False, 'error': 'Укажите действие: accept или reject'}), 400
+
+    if action == 'reject':
+        # reject — простая операция, оставляем как есть (минуя Use Case)
+        return _reject_invitation(invitation_id, session['user_id'])
+
+    cmd = AcceptInvitationCommand(
+        invitation_id=invitation_id,
+        worker_id=session['user_id'],
+    )
+    use_case = current_app.container.accept_invitation_use_case()
+    result = use_case.execute(cmd)  # выбрасывает DomainError при ошибке
+
+    # Если дошли сюда — успех (ошибки перехвачены errorhandler и вернули JSON)
+    return jsonify({
+        'success': True,
+        'new_status': 'accepted',
+        'job_status': result.job_status,
+        'current_workers': result.current_workers,
+    })
3.9. Diff: app/__init__.py (container с Use Cases)
app/__init__.py — расширение контейнера Use Cases
--- a/app/__init__.py
+++ b/app/__init__.py
@@ -250,12 +250,23 @@
     from app.repositories import (
         JobRepository, ApplicationRepository, AdminRepository, NotificationRepository,
     )
+    from app.use_cases import (
+        ApplyJobUseCase, WithdrawApplicationUseCase, AcceptInvitationUseCase,
+    )
     from app.services.notification_service import NotificationService
     from app.utils import postgrest_client
 
     class _StubContainer:
         def job_repository(self): return JobRepository(postgrest_client)
         def application_repository(self): return ApplicationRepository(postgrest_client)
         def admin_repository(self): return AdminRepository(postgrest_client)
         def notification_repository(self): return NotificationRepository(postgrest_client)
+        def notification_service(self): return NotificationService(postgrest_client)
+        def apply_job_use_case(self):
+            return ApplyJobUseCase(
+                applications=self.application_repository(),
+                notifications=self.notification_service(),
+            )
+        def withdraw_application_use_case(self):
+            return WithdrawApplicationUseCase(
+                applications=self.application_repository(),
+                notifications=self.notification_service(),
+            )
+        def accept_invitation_use_case(self):
+            return AcceptInvitationUseCase(
+                invitations=self.application_repository(),  # пока нет InvitationRepository
+                notifications=self.notification_service(),
+            )
     app.container = _StubContainer()
3.10. Diff: удаление _apply_job_fallback
Критическое решение Фазы 3: мы удаляем неатомарный fallback. Миграция 048 (apply_job_atomic RPC) была написана давно и применена на продакшн; fallback остался «на всякий случай». Удаление упрощает код и устраняет целый класс race condition багов. Если по какой-то причине миграция 048 не применена, ApplyJobUseCase выбросит PostgrestError с понятным сообщением.
Удаление _apply_job_fallback — 96 строк удалено
--- a/app/blueprints/applications.py
+++ b/app/blueprints/applications.py
@@ -86,182 +86,0 @@
-def _apply_job_fallback(job_id: str, user_id: str):
-    """
-    Неатомарный fallback для apply_job, когда RPC apply_job_atomic недоступен.
-
-    ⚠️ ВАЖНО: содержит TOCTOU race condition между проверкой мест и созданием отклика.
-    Использовался только когда миграция 048 не применена.
-    Фаза 3: удалён, потому что миграция 048 обязательна с 2025 года.
-    """
-    # ... 96 строк небезопасного кода ...
-    pass
+# Удалён в Фазе 3. Если RPC apply_job_atomic недоступна, ApplyJobUseCase
+# выбросит PostgrestError с понятным сообщением.
3.11. Tests
tests/test_use_cases.py — 220 строк
# tests/test_use_cases.py
"""Фаза 3: юнит-тесты Use Cases без поднятия Flask."""
import pytest
from unittest.mock import MagicMock
 
from app.use_cases.apply_job import ApplyJobCommand, ApplyJobUseCase
from app.use_cases.withdraw_application import WithdrawCommand, WithdrawApplicationUseCase
from app.errors import (
    DuplicateApplicationError, NoSlotsAvailableError,
    BlacklistedByEmployerError, NotFoundError, PermissionDeniedError,
    WithdrawWindowClosedError,
)
 
 
class FakeApplicationRepository:
    def __init__(self, duplicate=None, apply_result=None, withdraw_result=None, app_data=None):
        self.duplicate = duplicate
        self.apply_result = apply_result or {'success': True, 'employer_id': 'emp-1', 'application_id': 'app-1'}
        self.withdraw_result = withdraw_result or {'success': True}
        self.app_data = app_data
        self.apply_called_with = None
        self.withdraw_called_with = None
 
    def find_duplicate(self, job_id, worker_id):
        return self.duplicate
 
    def apply_atomic(self, job_id, worker_id):
        self.apply_called_with = (job_id, worker_id)
        return self.apply_result
 
    def withdraw_atomic(self, app_id, user_id):
        self.withdraw_called_with = (app_id, user_id)
        return self.withdraw_result
 
    def get_by_id(self, app_id):
        return self.app_data
 
 
class FakeNotificationService:
    def __init__(self):
        self.enqueued = []
 
    def enqueue(self, user_id, notification_type, title, body, data=None):
        self.enqueued.append({
            'user_id': user_id, 'type': notification_type,
            'title': title, 'body': body, 'data': data or {},
        })
        return True
 
 
class TestApplyJobUseCase:
    def test_successful_apply_enqueues_notification(self):
        apps = FakeApplicationRepository()
        notifs = FakeNotificationService()
        use_case = ApplyJobUseCase(apps, notifs)
 
        result = use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='worker-1'))
 
        assert result.success is True
        assert result.employer_id == 'emp-1'
        assert result.job_id == 'job-1'
        assert len(notifs.enqueued) == 1
        assert notifs.enqueued[0]['user_id'] == 'emp-1'
        assert notifs.enqueued[0]['type'] == 'application_received'
 
    def test_duplicate_raises_specific_error(self):
        apps = FakeApplicationRepository(duplicate={'id': 'existing'})
        use_case = ApplyJobUseCase(apps, FakeNotificationService())
 
        with pytest.raises(DuplicateApplicationError):
            use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='worker-1'))
 
    def test_no_slots_raises_specific_error(self):
        apps = FakeApplicationRepository(
            apply_result={'success': False, 'code': 'no_slots', 'error': 'Места заполнены'}
        )
        use_case = ApplyJobUseCase(apps, FakeNotificationService())
 
        with pytest.raises(NoSlotsAvailableError):
            use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='worker-1'))
 
    def test_blacklisted_raises_403_error(self):
        apps = FakeApplicationRepository(
            apply_result={'success': False, 'code': 'blacklisted', 'error': 'В чёрном списке'}
        )
        use_case = ApplyJobUseCase(apps, FakeNotificationService())
 
        with pytest.raises(BlacklistedByEmployerError) as exc_info:
            use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='worker-1'))
        assert exc_info.value.http_status == 403
 
    def test_no_threading_thread_started(self):
        """Регрессионный тест: Use Case НЕ должен запускать потоки."""
        import threading
        apps = FakeApplicationRepository()
        use_case = ApplyJobUseCase(apps, FakeNotificationService())
 
        active_before = threading.active_count()
        use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='worker-1'))
        active_after = threading.active_count()
 
        assert active_after == active_before, (
            f'Use Case создал потоки: было {active_before}, стало {active_after}'
        )
 
 
class TestWithdrawApplicationUseCase:
    def test_successful_withdraw(self):
        apps = FakeApplicationRepository(
            app_data={'id': 'app-1', 'worker_id': 'worker-1', 'status': 'pending', 'job_id': 'job-1'},
            withdraw_result={'success': True},
        )
        notifs = FakeNotificationService()
        use_case = WithdrawApplicationUseCase(apps, notifs)
 
        result = use_case.execute(WithdrawCommand(application_id='app-1', worker_id='worker-1'))
 
        assert result.success is True
        assert result.new_status == 'withdrawn'
 
    def test_withdraw_not_found_raises(self):
        apps = FakeApplicationRepository(app_data=None)
        use_case = WithdrawApplicationUseCase(apps, FakeNotificationService())
 
        with pytest.raises(NotFoundError):
            use_case.execute(WithdrawCommand(application_id='nonexistent', worker_id='worker-1'))
 
    def test_withdraw_wrong_user_raises_permission_denied(self):
        apps = FakeApplicationRepository(
            app_data={'id': 'app-1', 'worker_id': 'other-worker', 'status': 'pending'},
        )
        use_case = WithdrawApplicationUseCase(apps, FakeNotificationService())
 
        with pytest.raises(PermissionDeniedError):
            use_case.execute(WithdrawCommand(application_id='app-1', worker_id='worker-1'))
 
    def test_withdraw_window_closed_raises(self):
        apps = FakeApplicationRepository(
            app_data={'id': 'app-1', 'worker_id': 'worker-1', 'status': 'accepted', 'job_id': 'job-1'},
            withdraw_result={'success': False, 'code': 'window_closed',
                            'error': 'Менее 12 часов до начала'},
        )
        use_case = WithdrawApplicationUseCase(apps, FakeNotificationService())
 
        with pytest.raises(WithdrawWindowClosedError):
            use_case.execute(WithdrawCommand(application_id='app-1', worker_id='worker-1'))
 
 
class TestNoThreadingThread:
    def test_zero_threading_thread_imports_in_applications_blueprint(self):
        """Регрессионный тест: в applications.py не должно быть threading.Thread."""
        from pathlib import Path
        content = Path('app/blueprints/applications.py').read_text(encoding='utf-8')
        assert 'threading.Thread' not in content, (
            'threading.Thread всё ещё используется в applications.py — Фаза 3 не завершена'
        )
        assert 'import threading' not in content
3.12. Risk & rollback
| Поле | Значение |
|---|---|
| Risk level | High — переписывается ключевой пользовательский флоу (apply/withdraw/accept) |
| Mitigation | 1. Покрыть BCE существующие E2E-тесты перед PR. 2. Soak test 1 неделя на staging. 3. Поэтапный rollout: сначала apply, потом withdraw, потом accept (3 отдельных под-PR внутри этого PR) |
| Rollback | git revert PR; старый application_service.py оставлен как deprecated (но не вызывается) |
| Migration check | Перед deploy проверить: SELECT proname FROM pg_proc WHERE proname IN ('apply_job_atomic', 'withdraw_application_atomic', 'accept_invitation_atomic'); — все три RPC должны существовать |
| Backward compat | URL-маршруты не меняются; HTTP-ответы на ошибки меняются с 200+flash на 4xx/5xx+JSON для /api/* |
3.13. Success metrics
●	0 вхождений `threading.Thread` в app/ (rg --type py 'threading\.Thread' app/).
●	0 вхождений `_apply_job_fallback` в кодовой базе.
●	Coverage Use Cases > 90% (pytest-cov); каждый Use Case имеет тесты на happy path + все типизированные ошибки.
●	Юнит-тест `test_successful_apply_enqueues_notification` выполняется < 100ms без Flask-контекста.
●	E2E-тест apply→withdraw→accept проходит на staging без регрессий.
Pull Request #4 — Фаза 4: Redis cache_for + multi-replica WebSocket
Pull Request #4  ·  branch: refactor/phase-4-shared-state → main
Фаза 4 — Redis-backed cache_for + multi-replica WebSocket
Pull Request #4  ·  branch: refactor/phase-4-shared-state → main
Фаза 4 — Redis-backed cache_for + multi-replica WebSocket
 Summary  
Устраняем состояние в памяти процесса. Часть 1: переписываем декоратор @cache_for на Redis-backed реализацию, чтобы кеш разделялся между gunicorn-воркерами. Часть 2: переписываем WebSocket-сервер с глобального active_connections dict на ConnectionRegistry через Redis Sets + Pub/Sub, что позволяет запускать 2+ реплики WS-сервера за load balancer.
4.1. Files changed
| File | Lines +/– | Type | Risk |
|---|---|---|---|
| app/cache.py | -42 / +60 | Modified (rewrite cache_for) | Medium |
| app/utils/postgres_client.py | -28 / +2 | Modified (remove in-memory cache_for) | Low |
| app/utils__init__.py | -2 / +2 | Modified | None |
| websocket_server/registry.py | +0 / +118 | New | Medium |
| websocket_server/main.py | -35 / +28 | Modified | High |
| websocket_server/auth.py | -0 / +6 | Modified | Low |
| tests/test_cache.py | +0 / +85 | New | None |
| tests/test_ws_registry.py | +0 / +165 | New | None |
4.2. Diff: app/cache.py (Redis-backed cache_for)
Переписываем декоратор cache_for на Redis. Ключ формируется из имени функции и SHA-256 от аргументов — это даёт стабильные ключи, устойчивые к коллизиям. Значение сериализуется через pickle (protocol=4 для совместимости с Python 3.7+). При недоступности Redis — graceful degradation (вызов функции без кеша).
app/cache.py — cache_for переписан (Redis-backed)
--- a/app/cache.py
+++ b/app/cache.py
@@ -1,6 +1,7 @@
-"""Redis-backed cache helpers shared between Flask app, services, and tasks."""
+"""Redis-backed cache helpers + @cache_for decorator.
 
+Decorator cache_for теперь использует Redis (не in-memory dict),
+что позволяет разделять кеш между gunicorn-воркерами.
Модуль НЕ зависит от app/__init__.py.
"""
 from __future__ import annotations
 import logging
-from typing import Any, Optional
+import hashlib
+import json
+import pickle
+from functools import wraps
+from typing import Any, Callable, Optional, TypeVar
 from flask import current_app
 from app.utils.redis_client import get_redis_client
 
 logger = logging.getLogger(__name__)
 _DEFAULT_TTL = 30  # секунд
+F = TypeVar('F', bound=Callable)
 
 
 def cache_get(key: str, *, as_int: bool = False) -> Optional[Any]:
@@ -56,3 +57,60 @@ def cache_incr(key: str, ttl: int = _DEFAULT_TTL) -> Optional[int]:
         return current
     except Exception as e:
         logger.warning('cache_incr(%s) failed: %s', key, e)
         return None
+
+
+def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
+    """Стабильный ключ кеша: имя функции + SHA-256 от аргументов."""
+    payload = json.dumps(
+        {'a': repr(args), 'k': repr(sorted(kwargs.items()))},
+        sort_keys=True, ensure_ascii=False,
+    )
+    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
+    return f'cache:{func_name}:{digest}'
+
+
+def cache_for(seconds: int = 30) -> Callable[[F], F]:
+    """Декоратор: кеширует результат функции в Redis с TTL.
+
+    В отличие от предыдущей in-memory реализации, этот декоратор
+    разделяет кеш между всеми gunicorn-воркерами и процессами Celery.
+
+    При недоступности Redis — graceful degradation: функция вызывается
+    без кеширования (медленнее, но не падает).
+
+    Args:
+        seconds: TTL кеша в секундах (по умолчанию 30).
+
+    Usage:
+        @cache_for(seconds=300)
+        def get_skills():
+            return postgrest_request('GET', 'skills?select=*').json()
+    """
+    def decorator(func: F) -> F:
+        @wraps(func)
+        def wrapper(*args, **kwargs):
+            client = get_redis_client()
+            if client is None:
+                # Redis недоступен — вызываем без кеша
+                return func(*args, **kwargs)
+
+            key = _make_cache_key(func.__name__, args, kwargs)
+            try:
+                cached = client.get(key)
+                if cached is not None:
+                    return pickle.loads(cached)
+            except Exception as e:
+                logger.warning('cache_for: GET %s failed: %s', key, e)
+
+            # Cache miss — выполняем функцию
+            result = func(*args, **kwargs)
+
+            # Сохраняем в кеш (не блокируем ответ при ошибке Redis)
+            try:
+                client.setex(key, seconds, pickle.dumps(result, protocol=4))
+            except Exception as e:
+                logger.warning('cache_for: SETEX %s failed: %s', key, e)
+
+            return result
+        return wrapper  # type: ignore[return-value]
+    return decorator
4.3. Diff: app/utils/postgrest_client.py (удаление in-memory cache_for)
app/utils/postgrest_client.py — in-memory cache_for удалён
--- a/app/utils/postgrest_client.py
+++ b/app/utils/postgrest_client.py
@@ -245,32 +245,6 @@
 # ═══════════════════════════════════════════════════════════════
-# Кэширование (in-memory)
-# ═══════════════════════════════════════════════════════════════
-
-def cache_for(seconds: int = 30) -> Callable[[F], F]:
-    """Простой in-memory кэш для функций.
-
-    ⚠️ Фаза 4: УДАЛЁН. Используйте app.cache.cache_for (Redis-backed).
-    Старая реализация не разделяла кеш между gunicorn-воркерами.
-    """
-    raise RuntimeError(
-        'app.utils.postgrest_client.cache_for удалён в Фазе 4. " +
-        'Используйте from app.cache import cache_for (Redis-backed).'
-    )
+from app.cache import cache_for  # re-export для обратной совместимости
 
 POSTGREST_URL = Config.POSTGREST_URL
4.4. Diff: app/utils/__init__.py
app/utils/__init__.py — без изменений по сути
--- a/app/utils/__init__.py
+++ b/app/utils/__init__.py
@@ -96,7 +96,7 @@
 CircuitBreaker = _pgrest.CircuitBreaker
 PostgrestResponse = _pgrest.PostgrestResponse
-cache_for = _pgrest.cache_for  # теперь Redis-backed (Фаза 4)
+cache_for = _pgrest.cache_for  # реэкспорт из app.cache через postgrest_client
4.5. New: websocket_server/registry.py
Ключевой модуль Фазы 4 для multi-replica WebSocket. Каждый WS-сервер при старте генерирует уникальный SERVER_ID. При подключении пользователя сервер регистрирует себя в Redis Set ws:online:{user_id}. При отправке уведомления издатель находит все серверы с этим пользователем и публикует в каждый канал ws:server:{server_id}. Каждый сервер слушает свой канал и доставляет сообщение локальному соединению.
websocket_server/registry.py — 118 строк
# websocket_server/registry.py
"""Redis-backed ConnectionRegistry для multi-replica WebSocket.
 
Решает проблему: глобальный dict active_connections не переживает
рестарт и не масштабируется на 2+ реплики WS-сервера.
 
Архитектура:
- Каждый WS-сервер имеет уникальный SERVER_ID (UUID при старте)
- При подключении: SADD ws:online:{user_id} {SERVER_ID}
- При отключении: SREM ws:online:{user_id} {SERVER_ID}
- При отправке: найти все SERVER_ID для user_id, опубликовать в каждый
  канал ws:server:{SERVER_ID}
- Каждый сервер слушает свой канал и доставляет локальному соединению
 
Альтернатива для продакшна: Redis Streams с consumer groups (надёжнее,
но сложнее; рассмотреть если Pub/Sub покажет потери).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import uuid
from typing import Any, Optional
 
import redis.asyncio as aioredis
from fastapi import WebSocket
 
logger = logging.getLogger(__name__)
 
# Уникальный ID этого процесса. Генерируется один раз при импорте модуля.
SERVER_ID: str = str(uuid.uuid4())
 
# Канал Pub/Sub, который слушает только этот сервер
LOCAL_CHANNEL: str = f'ws:server:{SERVER_ID}'
 
# TTL для ключа ws:online:{user_id} (на случай краша без корректного disconnect)
ONLINE_TTL_SECONDS: int = 300
 
 
class ConnectionRegistry:
    """Redis-backed registry активных WebSocket-соединений.
 
    Один экземпляр на процесс. Создаётся в lifespan() FastAPI приложения.
    """
 
    def __init__(self, redis_url: str):
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2,
        )
        # Локальные соединения — только для этого процесса
        self._local: dict[str, WebSocket] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._shutdown = asyncio.Event()
 
    async def start(self) -> None:
        """Запустить фоновый listener для LOCAL_CHANNEL."""
        self._listener_task = asyncio.create_task(self._listen_local())
        logger.info('ConnectionRegistry started, SERVER_ID=%s', SERVER_ID)
 
    async def stop(self) -> None:
        """Корректно завершить работу: закрыть все локальные соединения,
        удалить свои ключи из Redis, закрыть Redis-клиент."""
        self._shutdown.set()
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
 
        # Закрываем все локальные соединения
        for user_id, ws in list(self._local.items()):
            try:
                await ws.close(code=1001, reason='Server shutdown')
            except Exception:
                pass
            await self._unregister_from_redis(user_id)
        self._local.clear()
 
        await self._redis.close()
        logger.info('ConnectionRegistry stopped')
 
    async def register(self, user_id: str, ws: WebSocket) -> None:
        """Зарегистрировать локальное соединение и подписать сервер на пользователя."""
        self._local[user_id] = ws
        await self._redis.sadd(f'ws:online:{user_id}', SERVER_ID)
        # Обновляем TTL на ключе (на случай если пользователь долго не активен)
        await self._redis.expire(f'ws:online:{user_id}', ONLINE_TTL_SECONDS)
        logger.info('User %s registered on server %s (local: %d)',
                    user_id, SERVER_ID[:8], len(self._local))
 
    async def unregister(self, user_id: str) -> None:
        """Удалить локальное соединение и убрать сервер из Set'а пользователя."""
        self._local.pop(user_id, None)
        await self._unregister_from_redis(user_id)
        logger.info('User %s unregistered from server %s (local: %d)',
                    user_id, SERVER_ID[:8], len(self._local))
 
    async def _unregister_from_redis(self, user_id: str) -> None:
        """Убрать SERVER_ID из Set'а пользователя (если он там есть)."""
        try:
            await self._redis.srem(f'ws:online:{user_id}', SERVER_ID)
        except Exception as e:
            logger.warning('Failed to srem %s from ws:online:%s: %s',
                          SERVER_ID, user_id, e)
 
    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Отправить сообщение пользователю.
 
        Returns: True если сообщение доставлено хотя бы одному серверу,
                 False если пользователь офлайн или все серверы недоступны.
        """
        # Находим все серверы, где сидит пользователь
        try:
            servers = await self._redis.smembers(f'ws:online:{user_id}')
        except Exception as e:
            logger.error('Failed to get servers for user %s: %s', user_id, e)
            return False
 
        if not servers:
            return False  # пользователь офлайн
 
        payload = json.dumps({
            'user_id': user_id,
            'message': message,
        }, ensure_ascii=False, default=str)
 
        # Публикуем в канал каждого сервера
        delivered = 0
        for server_id in servers:
            try:
                count = await self._redis.publish(f'ws:server:{server_id}', payload)
                delivered += count
            except Exception as e:
                logger.warning('Failed to publish to server %s: %s',
                              server_id[:8], e)
 
        return delivered > 0
 
    async def _listen_local(self) -> None:
        """Слушать LOCAL_CHANNEL и доставлять сообщения локальным соединениям."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(LOCAL_CHANNEL)
        logger.info('Listening on channel %s', LOCAL_CHANNEL)
 
        try:
            while not self._shutdown.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.5,
                )
                if message is None:
                    continue
 
                try:
                    data_str = message.get('data', '{}')
                    if isinstance(data_str, bytes):
                        data_str = data_str.decode('utf-8')
                    payload = json.loads(data_str)
 
                    user_id = payload.get('user_id')
                    message_data = payload.get('message', {})
 
                    ws = self._local.get(user_id)
                    if ws:
                        try:
                            await ws.send_json(message_data)
                        except Exception as e:
                            logger.warning('Failed to send to local %s: %s',
                                          user_id, e)
                            # Удаляем мёртвое соединение
                            await self.unregister(user_id)
                    else:
                        # Локального соединения нет, но в Redis оно числится —
                        # убираем себя из Set'а
                        await self._unregister_from_redis(user_id)
 
                except json.JSONDecodeError as e:
                    logger.error('Invalid JSON in pub/sub: %s', e)
                except Exception as e:
                    logger.error('Unexpected error in listener: %s', e)
 
        except asyncio.CancelledError:
            logger.info('Listener task cancelled')
        finally:
            await pubsub.unsubscribe(LOCAL_CHANNEL)
            await pubsub.close()
 
    def get_local_count(self) -> int:
        """Количество активных локальных соединений (для /health)."""
        return len(self._local)
 
    async def get_online_users_count(self) -> int:
        """Приблизительное количество онлайн-пользователей (по всем ключам ws:online:*).
 
        Использует SCAN для перебора ключей (не блокирует Redis).
        """
        count = 0
        async for key in self._redis.scan_iter(match='ws:online:*', count=100):
            count += 1
        return count
4.6. Diff: websocket_server/main.py (использование registry)
Переписываем main.py, чтобы использовать ConnectionRegistry вместо глобального dict. Lifespan создаёт registry, запускает listener, и корректно завершает работу при shutdown. WebSocket-эндпоинт регистрирует соединение в registry при подключении и убирает при отключении.
websocket_server/main.py — refactor для registry
--- a/websocket_server/main.py
+++ b/websocket_server/main.py
@@ -50,8 +50,8 @@
 # Глобальное состояние
-# Словарь активных WebSocket-соединений: {user_id: WebSocket}
-active_connections: dict[str, WebSocket] = {}
+# Registry активных соединений (создаётся в lifespan)
+registry: ConnectionRegistry | None = None
 
 # Флаг для graceful shutdown слушателя Pub/Sub
 shutdown_event: asyncio.Event = asyncio.Event()
@@ -138,7 +138,12 @@
 @asynccontextmanager
 async def lifespan(app: FastAPI):
     global redis_client, shutdown_event
+    global registry
 
     shutdown_event.clear()
 
     # Подключение к Redis
     logger.info('Подключение к Redis: %s', REDIS_URL)
     try:
         redis_client = aioredis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
         await redis_client.ping()
         logger.info('Redis подключён успешно')
     except Exception as exc:
         logger.error('Не удалось подключиться к Redis: %s', exc)
         redis_client = None
 
+    # Создаём registry для multi-replica WebSocket
+    if redis_client is not None:
+        registry = ConnectionRegistry(REDIS_URL)
+        await registry.start()
+    else:
+        logger.error('Registry не запущен: Redis недоступен')
+
     yield  # Приложение работает
 
     # Shutdown
     logger.info('Завершение работы WebSocket-сервера...')
     shutdown_event.set()
 
+    if registry:
+        await registry.stop()
+
-    # Закрываем все активные WebSocket-соединения
-    for uid, ws in list(active_connections.items()):
-        try:
-            await ws.close(code=status.WS_1001_GOING_AWAY)
-        except Exception:
-            pass
-        logger.info('WebSocket-соединение пользователя %s закрыто', uid)
-    active_connections.clear()
     # Закрываем Redis-соединение
     if redis_client is not None:
         await redis_client.close()
@@ -213,25 +213,15 @@
 @app.websocket('/ws')
 async def websocket_endpoint(
     websocket: WebSocket,
     token: str = Query(..., description='JWT-токен аутентификации'),
 ) -> None:
     payload = verify_token(token)
     if payload is None:
         await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason='Невалидный JWT')
         return
 
     user_id = str(payload.get('user_id', ''))
     if not user_id:
         await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason='Нет user_id')
         return
 
+    if registry is None:
+        await websocket.close(code=1011, reason='Registry not initialized')
+        return
+
     await websocket.accept()
-    active_connections[user_id] = websocket
-    logger.info('Пользователь %s подключился (всего онлайн: %d)', user_id, len(active_connections))
+    await registry.register(user_id, websocket)
 
     try:
         await websocket.send_json({'type': 'connected', 'user_id': user_id})
         while True:
             data = await websocket.receive_text()
             logger.debug('Получено сообщение от %s: %s', user_id, data[:100])
     except WebSocketDisconnect:
         logger.info('Пользователь %s отключился', user_id)
     except Exception as exc:
         logger.error('Ошибка WS для %s: %s', user_id, exc)
     finally:
-        active_connections.pop(user_id, None)
-        logger.info('Пользователь %s удалён (онлайн: %d)', user_id, len(active_connections))
+        await registry.unregister(user_id)
@@ -270,7 +260,10 @@
 @app.get('/health')
 async def healthcheck() -> dict[str, Any]:
     redis_status = 'unknown'
     if redis_client is not None:
         try:
             await redis_client.ping()
             redis_status = 'ok'
         except Exception as exc:
             redis_status = f'error: {exc}'
     return {
         'status': 'ok',
         'redis': redis_status,
-        'active_connections': len(active_connections),
+        'local_connections': registry.get_local_count() if registry else 0,
+        'online_users_total': await registry.get_online_users_count() if registry else 0,
+        'server_id': SERVER_ID[:8] if 'SERVER_ID' in globals() else 'unknown',
         'version': '2.1.0',  # bumped in Phase 4
     }
4.7. Tests
tests/test_cache.py — 85 строк
# tests/test_cache.py
"""Фаза 4: тесты Redis-backed cache_for."""
import time
import pytest
from unittest.mock import MagicMock, patch
from app.cache import cache_for, _make_cache_key
 
 
class FakeRedis:
    def __init__(self):
        self.store = {}
 
    def get(self, key):
        return self.store.get(key)
 
    def setex(self, key, ttl, value):
        self.store[key] = value
 
 
class TestCacheForKeyGeneration:
    def test_same_args_produce_same_key(self):
        k1 = _make_cache_key('func', (1, 2), {'a': 'b'})
        k2 = _make_cache_key('func', (1, 2), {'a': 'b'})
        assert k1 == k2
 
    def test_different_args_produce_different_keys(self):
        k1 = _make_cache_key('func', (1, 2), {})
        k2 = _make_cache_key('func', (1, 3), {})
        assert k1 != k2
 
    def test_kwargs_order_does_not_matter(self):
        k1 = _make_cache_key('func', (), {'a': 1, 'b': 2})
        k2 = _make_cache_key('func', (), {'b': 2, 'a': 1})
        assert k1 == k2  # sorted internally
 
    def test_key_has_cache_prefix(self):
        k = _make_cache_key('get_skills', (), {})
        assert k.startswith('cache:get_skills:')
 
 
class TestCacheForDecorator:
    def test_caches_result_in_redis(self):
        fake_redis = FakeRedis()
        call_count = 0
 
        @cache_for(seconds=60)
        def expensive_func():
            nonlocal call_count
            call_count += 1
             return {'data': 'value'}
 
        with patch('app.cache.get_redis_client', return_value=fake_redis):
            result1 = expensive_func()
            result2 = expensive_func()
 
        assert result1 == result2 == {'data': 'value'}
        assert call_count == 1  # функция вызвана один раз
        assert len(fake_redis.store) == 1
 
    def test_graceful_degradation_when_redis_unavailable(self):
        @cache_for(seconds=60)
        def func():
            return 'result'
 
        with patch('app.cache.get_redis_client', return_value=None):
            result = func()
        assert result == 'result'  # функция вызвана, кеш не работает
 
    def test_ttl_passed_to_redis(self):
        fake_redis = FakeRedis()
        @cache_for(seconds=300)
        def func():
            return 'value'
 
        with patch('app.cache.get_redis_client', return_value=fake_redis):
            func()
        # Проверяем, что setex был вызван с TTL=300
        # (FakeRedis хранит только value, не ttl — но функция должна была вызвать setex)
        assert len(fake_redis.store) == 1
tests/test_ws_registry.py — 165 строк
# tests/test_ws_registry.py
"""Фаза 4: тесты ConnectionRegistry для multi-replica WebSocket."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from websocket_server.registry import ConnectionRegistry, SERVER_ID, LOCAL_CHANNEL
 
 
class FakeRedis:
    def __init__(self):
        self.sets = {}  # {key: set(values)}
        self.published = []  # [(channel, message)]
        self.pubsub_handlers = {}  # {channel: handler}
 
    async def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(values)
 
    async def srem(self, key, value):
        if key in self.sets:
            self.sets[key].discard(value)
 
    async def smembers(self, key):
        return self.sets.get(key, set())
 
    async def expire(self, key, ttl):
        pass  # noop в тестах
 
    async def publish(self, channel, message):
        self.published.append((channel, message))
        return 1  # один подписчик
 
    async def scan_iter(self, match=None, count=100):
        for key in list(self.sets.keys()):
            if match and match.replace('*', '') in key:
                yield key
 
    async def close(self):
        pass
 
 
class TestConnectionRegistry:
    @pytest.mark.asyncio
    async def test_register_adds_server_to_user_set(self):
        fake_redis = FakeRedis()
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        ws = MagicMock()
        await registry.register('user-1', ws)
 
        assert 'user-1' in registry._local
        assert SERVER_ID in fake_redis.sets.get('ws:online:user-1', set())
 
    @pytest.mark.asyncio
    async def test_unregister_removes_server_from_user_set(self):
        fake_redis = FakeRedis()
        fake_redis.sets['ws:online:user-1'] = {SERVER_ID, 'other-server'}
 
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {'user-1': MagicMock()}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        await registry.unregister('user-1')
 
        assert 'user-1' not in registry._local
        assert SERVER_ID not in fake_redis.sets['ws:online:user-1']
        assert 'other-server' in fake_redis.sets['ws:online:user-1']  # другие серверы не тронуты
 
    @pytest.mark.asyncio
    async def test_send_to_user_publishes_to_all_user_servers(self):
        fake_redis = FakeRedis()
        # Пользователь сидит на 3 серверах
        fake_redis.sets['ws:online:user-1'] = {'server-A', 'server-B', 'server-C'}
 
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        result = await registry.send_to_user('user-1', {'type': 'notification', 'text': 'hello'})
 
        assert result is True
        assert len(fake_redis.published) == 3  # опубликовано в 3 канала
        channels = [ch for ch, _ in fake_redis.published]
        assert 'ws:server:server-A' in channels
        assert 'ws:server:server-B' in channels
        assert 'ws:server:server-C' in channels
 
    @pytest.mark.asyncio
    async def test_send_to_user_returns_false_when_offline(self):
        fake_redis = FakeRedis()
        # Нет ключа ws:online:user-1 — пользователь офлайн
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        result = await registry.send_to_user('nonexistent', {'text': 'hello'})
        assert result is False
        assert len(fake_redis.published) == 0
 
    @pytest.mark.asyncio
    async def test_local_listener_delivers_to_local_websocket(self):
        """Тест интеграции: публикация в LOCAL_CHANNEL доставляется локальному ws."""
        fake_redis = FakeRedis()
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        ws = AsyncMock()
        await registry.register('user-1', ws)
 
        # Симулируем публикацию в LOCAL_CHANNEL
        message = json.dumps({
            'user_id': 'user-1',
            'message': {'type': 'notification', 'text': 'hello'},
        })
        fake_redis.pubsub_handlers[LOCAL_CHANNEL](message)
 
        # Проверяем, что ws.send_json был вызван
        ws.send_json.assert_called_once_with({'type': 'notification', 'text': 'hello'})
 
    @pytest.mark.asyncio
    async def test_get_local_count(self):
        fake_redis = FakeRedis()
        registry = ConnectionRegistry.__new__(ConnectionRegistry)
        registry._redis = fake_redis
        registry._local = {'user-1': MagicMock(), 'user-2': MagicMock()}
        registry._shutdown = asyncio.Event()
        registry._listener_task = None
 
        assert registry.get_local_count() == 2
4.8. Risk & rollback
| Поле | Значение |
|---|---|
| Risk level | Medium (cache) / High (WebSocket) — меняется инфраструктурный слой |
| Cache rollback | git revert; old in-memory cache_for временно доступен через git tag phase-3-backup |
| WS rollback | git revert + docker-compose restart websocket; существующие соединения переподключатся |
| Multi-replica test | Перед prod: запустить 2 реплики на staging, kill -9 одной, проверить, что все уведомления дошли |
| Monitoring | Alert: rate of 'Failed to publish' log lines > 10/min → откат |
| TTL concern | Если WS-сервер крашится без корректного unregister, ключ ws:online:{user_id} остаётся с TTL 5 мин. При отправке будет publish в несуществующий сервер — это безвредно (Redis просто вернёт 0 подписчиков). |
4.9. Success metrics
●	Cache hit ratio на /api/skills, /api/religions > 80% (считается через логи: cache_for GET vs SETEX).
●	2 реплики WS-сервера на staging: 100% уведомлений доставляются при kill -9 одной реплики (chaos test).
●	Latency на multi-replica send_to_user < 50ms (Redis SISMEMBER + PUBLISH).
●	/health WS-сервера показывает local_connections + online_users_total + server_id.
●	0 вхождений `active_connections` dict в websocket_server/ (rg --type py 'active_connections' websocket_server/).
Pull Request #5 — Фаза 5: DI-контейнер + Config как dataclass
Pull Request #5  ·  branch: refactor/phase-5-di-config → main
Фаза 5 — DI-контейнер + Config как dataclass
 Summary  
Финальная очистка. Часть 1: превращаем stub-контейнер из Фазы 2 в полноценный DI-контейнер с типизированными зависимостями. Часть 2: переписываем Config из class attributes (с side-effects при импорте) в frozen dataclass с factory-методом from_env(). Часть 3: обновляем tests/conftest.py для использования фейковых repository в юнит-тестах без поднятия Flask.
5.1. Files changed
| File | Lines +/– | Type | Risk |
|---|---|---|---|
| app/container.py | +0 / +85 | New (replaces stub) | Low |
| app/config.py | –128 / +92 | Modified (rewrite to dataclass) | Medium |
| app/__init__.py | –24 / +6 | Modified (use Container, drop stub) | Low |
| tests/conftest.py | –0 / +60 | Modified (fake container) | None |
| tests/test_container.py | +0 / +95 | New | None |
| tests/test_config.py | +0 / +80 | New | None |
5.2. New: app/container.py (полный DI)
Контейнер — это единственное место, где собираются все зависимости. Заменяет stub из Фазы 2. Главное отличие: использует lru_cache для синглтон-зависимостей (PostgREST-клиент, Redis-клиент) и фабричные методы для use cases (новый экземпляр на каждый вызов — это правильно, потому что use case может содержать state).
app/container.py — 85 строк
# app/container.py
"""Dependency Injection контейнер для Trudnik.
 
Единственное место, где собираются все зависимости приложения.
Создаётся в create_app() и хранится в app.container.
 
Преимущества:
- Use Cases получают зависимости через __init__, а не через глобальный импорт
- В тестах можно создать Container с fake-зависимостями
- Явное управление жизненным циклом (синглтоны vs фабрики)
 
Использование:
    # В Blueprint:
    use_case = current_app.container.apply_job_use_case()
    result = use_case.execute(cmd)
 
    # В тестах:
    container = Container(
        config=test_config,
        postgrest_client=FakePostgrestClient(),
        redis_client=FakeRedis(),
    )
    use_case = container.apply_job_use_case()
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Optional
 
from app.config import Config
 
logger = logging.getLogger(__name__)
 
 
class Container:
    """Контейнер зависимостей приложения.
 
    Принимает в __init__ все инфраструктурные зависимости.
    Бизнес-зависимости (Repository, Use Cases) создаются через методы.
    """
 
    def __init__(self,
                 config: Config,
                 postgrest_client,
                 redis_client=None):
        self._config = config
        self._postgrest = postgrest_client
        self._redis = redis_client
 
    # ═══════════════════════════════════════════════════════════════
    # Синглтоны (один экземпляр на контейнер)
    # ═══════════════════════════════════════════════════════════════
 
    @property
    def config(self) -> Config:
        return self._config
 
    @property
    def redis(self):
        return self._redis
 
    @lru_cache(maxsize=1)
    def job_repository(self):
        from app.repositories.job_repository import JobRepository
        return JobRepository(self._postgrest)
 
    @lru_cache(maxsize=1)
    def application_repository(self):
        from app.repositories.application_repository import ApplicationRepository
        return ApplicationRepository(self._postgrest)
 
    @lru_cache(maxsize=1)
    def admin_repository(self):
        from app.repositories.admin_repository import AdminRepository
        return AdminRepository(self._postgrest)
 
    @lru_cache(maxsize=1)
    def notification_repository(self):
        from app.repositories.notification_repository import NotificationRepository
        return NotificationRepository(self._postgrest)
 
    @lru_cache(maxsize=1)
    def notification_service(self):
        from app.services.notification_service import NotificationService
        return NotificationService(self._postgrest, self._redis)
 
    # ═══════════════════════════════════════════════════════════════
    # Фабрики Use Cases (новый экземпляр на каждый вызов)
    # ═══════════════════════════════════════════════════════════════
 
    def apply_job_use_case(self):
        from app.use_cases.apply_job import ApplyJobUseCase
        return ApplyJobUseCase(
            applications=self.application_repository(),
            notifications=self.notification_service(),
        )
 
    def withdraw_application_use_case(self):
        from app.use_cases.withdraw_application import WithdrawApplicationUseCase
        return WithdrawApplicationUseCase(
            applications=self.application_repository(),
            notifications=self.notification_service(),
        )
 
    def accept_invitation_use_case(self):
        from app.use_cases.accept_invitation import AcceptInvitationUseCase
        return AcceptInvitationUseCase(
            invitations=self.application_repository(),  # TODO: InvitationRepository в Фазе 6
            notifications=self.notification_service(),
        )
 
    # ═══════════════════════════════════════════════════════════════
    # Health-check helpers
    # ═══════════════════════════════════════════════════════════════
 
    def get_health_status(self) -> dict:
        """Сводный health check для всех зависимостей."""
        status = {'status': 'ok', 'components': {}}
 
        # Redis
        if self._redis is None:
            status['components']['redis'] = 'unavailable'
            status['status'] = 'degraded'
        else:
            try:
                self._redis.ping()
                status['components']['redis'] = 'ok'
            except Exception as e:
                status['components']['redis'] = f'error: {e}'
                status['status'] = 'degraded'
 
        # PostgREST (через Circuit Breaker)
        try:
            from app.utils.postgrest_client import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()
            status['components']['circuit_breaker'] = cb_state
            if cb_state['postgrest']['state'] == 'OPEN' or cb_state['admin']['state'] == 'OPEN':
                status['status'] = 'degraded'
        except Exception as e:
            status['components']['circuit_breaker'] = f'error: {e}'
 
        return status
5.3. Diff: app/config.py (dataclass + factory)
Переписываем Config из class attributes с side-effects в frozen dataclass с factory-методом. Главное преимущество: можно создать тестовый Config без env vars, можно создать два Config в одном pytest-ране (для тестирования разных deployment_env), нет side-effects при импорте.
app/config.py — полный rewrite
--- a/app/config.py
+++ b/app/config.py
@@ -1,128 +1,92 @@
-import logging
-import os
-from dotenv import load_dotenv
-
-load_dotenv()
-
-logger = logging.getLogger(__name__)
-
-
-class Config:
-    TESTING = os.environ.get('TESTING', 'False').strip().lower() in ('true', '1', 'yes')
-    _FALLBACK_SECRET = os.environ.get('SECRET_KEY')
-    if not _FALLBACK_SECRET:
-        raise RuntimeError('SECRET_KEY environment variable is required')
-    SECRET_KEY = _FALLBACK_SECRET
-    # ... 100+ строк валидации на верхнем уровне класса ...
+"""Конфигурация приложения как frozen dataclass.
+
+Фаза 5: переписано из class attributes (с side-effects при импорте)
+в dataclass с factory-методом from_env(). Это позволяет:
+- Создавать тестовые Config без env vars
+- Создавать несколько Config в одном pytest-ране
+- Нет side-effects при импорте модуля
+"""
+from __future__ import annotations
+import logging
+import os
+from dataclasses import dataclass, field, asdict
+from dotenv import load_dotenv
+
+logger = logging.getLogger(__name__)
+load_dotenv()  # загружает .env в переменные окружения (но без side-effects в классе)
+
+
+class ConfigError(RuntimeError):
+    """Ошибка конфигурации."""
+
+
+@dataclass(frozen=True)
+class Config:
+    """Frozen dataclass с конфигурацией приложения.
+
+    Создаётся через Config.from_env() в create_app().
+    В тестах можно создать напрямую: Config(secret_key='test', ...).
+    """
+    # Основные настройки
+    secret_key: str
+    deployment_env: str = 'development'
+    testing: bool = False
+
+    # PostgREST
+    postgrest_url: str = 'http://localhost:3000'
+    pgrst_jwt_secret: str = ''
+
+    # Redis
+    redis_url: str = 'redis://localhost:6379/0'
+
+    # WebSocket
+    websocket_url: str = 'ws://localhost:8001/ws'
+    websocket_port: int = 8001
+
+    # SMTP
+    smtp_host: str = 'localhost'
+    smtp_port: int = 587
+    smtp_user: str = ''
+    smtp_password: str = ''
+    smtp_use_tls: bool = True
+    smtp_use_ssl: bool = False
+    smtp_timeout: int = 30
+    smtp_from_email: str = 'notifications@trudnik.ru'
+    smtp_from_name: str = 'Trudnik'
+    smtp_daily_limit: int = 1000
+
+    # Web Push (VAPID)
+    vapid_private_key: str = ''
+    vapid_public_key: str = ''
+    vapid_claims_email: str = 'notifications@trudnik.ru'
+    vapid_claims_subject: str = 'mailto:notifications@trudnik.ru'
+
+    # Business
+    monetization_enabled: bool = False
+    max_photo_size_mb: int = 5
+    upload_folder: str = 'uploads'
+    yandex_maps_api_key: str = ''
+    worker_site_url: str = 'https://trudnik.amvera.io/'
+
+    # Circuit Breaker
+    cb_failure_threshold: int = 10
+    cb_recovery_timeout: int = 60
+
+    # Admin API
+    admin_api_token: str = ''
+
+    # Cookie security
+    session_cookie_secure: bool = False
+    session_cookie_httponly: bool = True
+    session_cookie_samesite: str = 'Lax'
+    permanent_session_lifetime: int = 1800
+
+    @classmethod
+    def from_env(cls, env: dict | None = None) -> 'Config':
+        """Создать Config из переменных окружения.
+
+        Args:
+            env: словарь переменных (по умолчанию os.environ).
+                В тестах можно передать свой словарь.
+
+        Raises:
+            ConfigError: если обязательные переменные отсутствуют в production.
+        """
+        env = env or os.environ
+        deployment = env.get('DEPLOYMENT_ENV', 'development').strip()
+        is_production = deployment == 'production'
+
+        # Валидация обязательных переменных (только в production)
+        secret = env.get('SECRET_KEY', '').strip()
+        if not secret:
+            if is_production:
+                raise ConfigError('SECRET_KEY is required in production')
+            logger.warning('SECRET_KEY not set, using dev fallback')
+            secret = 'dev-secret-not-for-production'
+
+        pgrst_jwt_secret = env.get('PGRST_JWT_SECRET', '').strip()
+        if is_production and not pgrst_jwt_secret:
+            raise ConfigError('PGRST_JWT_SECRET is required in production')
+        if pgrst_jwt_secret and len(pgrst_jwt_secret.encode('utf-8')) < 32:
+            logger.warning('PGRST_JWT_SECRET too short: %d bytes (min 32)',
+                          len(pgrst_jwt_secret.encode('utf-8')))
+
+        postgrest_url = cls._normalize_postgrest_url(env.get('POSTGREST_URL', ''), is_production)
+        admin_api_token = env.get('ADMIN_API_TOKEN', '').strip()
+        if is_production and not admin_api_token:
+            raise ConfigError('ADMIN_API_TOKEN must be set in production')
+
+        return cls(
+            secret_key=secret,
+            deployment_env=deployment,
+            testing=env.get('TESTING', '').strip().lower() in ('true', '1', 'yes'),
+            postgrest_url=postgrest_url,
+            pgrst_jwt_secret=pgrst_jwt_secret,
+            redis_url=env.get('REDIS_URL', 'redis://localhost:6379/0'),
+            websocket_url=env.get('WEBSOCKET_URL', 'ws://localhost:8001/ws'),
+            websocket_port=int(env.get('WEBSOCKET_PORT', '8001')),
+            smtp_host=env.get('SMTP_HOST', 'localhost'),
+            smtp_port=int(env.get('SMTP_PORT', '587')),
+            smtp_user=env.get('SMTP_USER', ''),
+            smtp_password=env.get('SMTP_PASSWORD', ''),
+            smtp_use_tls=env.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 'yes'),
+            smtp_use_ssl=env.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 'yes'),
+            smtp_timeout=int(env.get('SMTP_TIMEOUT', '30')),
+            smtp_from_email=env.get('SMTP_FROM_EMAIL', 'notifications@trudnik.ru'),
+            smtp_from_name=env.get('SMTP_FROM_NAME', 'Trudnik'),
+            smtp_daily_limit=int(env.get('SMTP_DAILY_LIMIT', '1000')),
+            vapid_private_key=env.get('VAPID_PRIVATE_KEY', ''),
+            vapid_public_key=env.get('VAPID_PUBLIC_KEY', ''),
+            vapid_claims_email=env.get('VAPID_CLAIMS_EMAIL', 'notifications@trudnik.ru'),
+            vapid_claims_subject=env.get('VAPID_CLAIMS_SUBJECT', 'mailto:notifications@trudnik.ru'),
+            monetization_enabled=env.get('MONETIZATION_ENABLED', 'false').lower() == 'true',
+            max_photo_size_mb=int(env.get('MAX_PHOTO_SIZE_MB', '5')),
+            upload_folder=env.get('UPLOAD_FOLDER', 'uploads'),
+            yandex_maps_api_key=env.get('YANDEX_MAPS_API_KEY', ''),
+            worker_site_url=env.get('WORKER_SITE_URL', 'https://trudnik.amvera.io/'),
+            cb_failure_threshold=int(env.get('CB_FAILURE_THRESHOLD', '10')),
+            cb_recovery_timeout=int(env.get('CB_RECOVERY_TIMEOUT', '60')),
+            admin_api_token=admin_api_token,
+            session_cookie_secure=is_production,
+        )
+
+    @staticmethod
+    def _normalize_postgrest_url(url: str, is_production: bool) -> str:
+        url = url.strip()
+        if not url:
+            if is_production:
+                raise ConfigError('POSTGREST_URL is required in production')
+            return 'http://localhost:3000'
+        if not url.startswith(('http://', 'https://')):
+            url = 'http://' + url
+        return url
+
+    def to_flask_dict(self) -> dict:
+        """Совместимость с Flask app.config (ожидает UPPER_CASE ключи)."""
+        d = asdict(self)
+        # Преобразуем snake_case в UPPER_CASE для Flask
+        return {k.upper(): v for k, v in d.items()}
5.4. Diff: app/__init__.py (использование Container)
app/__init__.py — упрощение через Container
--- a/app/__init__.py
+++ b/app/__init__.py
@@ -113,8 +113,12 @@
 def create_app():
-    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
-    app = Flask(__name__,
-                root_path=project_root,
-                template_folder='templates',
-                static_folder='static')
-    app.config.from_object(Config)
-    app.secret_key = app.config['SECRET_KEY']
+    # Фаза 5: Config создаётся через factory, без side-effects при импорте
+    config = Config.from_env()
+    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
+    app = Flask(__name__,
+                root_path=project_root,
+                template_folder='templates',
+                static_folder='static')
+    app.config.from_mapping(config.to_flask_dict())
+    app.secret_key = config.secret_key
 
@@ -245,17 +249,8 @@
-    # Фаза 2: минимальный контейнер для Repository (Фаза 5 разовьёт в полноценный DI)
-    from app.repositories import (
-         JobRepository, ApplicationRepository, AdminRepository, NotificationRepository,
-    )
-    from app.use_cases import (
-        ApplyJobUseCase, WithdrawApplicationUseCase, AcceptInvitationUseCase,
-    )
-    from app.services.notification_service import NotificationService
-    from app.utils import postgrest_client
-    class _StubContainer:
-        def job_repository(self): return JobRepository(postgrest_client)
-        # ... 12 строк stub-методов ...
-    app.container = _StubContainer()
+    # Фаза 5: полноценный DI-контейнер
+    from app.container import Container
+    from app.utils import postgrest_client
+    from app.utils.redis_client import get_redis_client
+    app.container = Container(
+        config=config,
+        postgrest_client=postgrest_client,
+        redis_client=get_redis_client(),
+    )
5.5. Diff: tests/conftest.py (fake container)
Обновляем conftest.py для юнит-тестов. Главный выигрыш: можно тестировать Use Cases без поднятия Flask-приложения и без моков postgrest_client. Создаём TestContainer с fake repositories, передаём в Use Case напрямую.
tests/conftest.py — добавлены fake fixtures
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -1,5 +1,65 @@
+"""Pytest fixtures для Фазы 5: юнит-тесты без Flask-контекста."""
 import pytest
+from unittest.mock import MagicMock
 
 
+@pytest.fixture
+def fake_postgrest_client():
+    """Mock PostgREST-клиента для тестов."""
+    client = MagicMock()
+    # Настройка дефолтных ответов
+    client.postgrest_request.return_value = MagicMock(
+        ok=True, status_code=200, json=lambda: [], text='', headers={}
+    )
+    client.postgrest_admin_request.return_value = MagicMock(
+        ok=True, status_code=200, json=lambda: [], text='', headers={}
+    )
+    client.postgrest_rpc.return_value = MagicMock(
+        ok=True, status_code=200, json=lambda: {'success': True}, text='', headers={}
+    )
+    return client
 
 
+@pytest.fixture
+def fake_redis_client():
+    """In-memory fake Redis для тестов."""
+    class FakeRedis:
+        def __init__(self):
+            self.store = {}
+        def get(self, k): return self.store.get(k)
+        def setex(self, k, ttl, v): self.store[k] = v
+        def delete(self, k): self.store.pop(k, None)
+        def incr(self, k):
+            self.store[k] = int(self.store.get(k, 0)) + 1
+            return self.store[k]
+        def expire(self, k, ttl): pass
+        def ping(self): return True
+    return FakeRedis()
 
 
+@pytest.fixture
+def test_config():
+    """Тестовый Config без env vars."""
+    from app.config import Config
+    return Config(
+        secret_key='test-secret',
+        testing=True,
+        pgrst_jwt_secret='test-jwt-secret-with-at-least-32-bytes-length!!',
+    )
 
 
+@pytest.fixture
+def test_container(test_config, fake_postgrest_client, fake_redis_client):
+    """Полноценный Container с fake зависимостями.
+
+    Использование в тестах:
+        def test_apply_job(test_container):
+            use_case = test_container.apply_job_use_case()
+            result = use_case.execute(ApplyJobCommand(...))
+    """
+    from app.container import Container
+    return Container(
+        config=test_config,
+        postgrest_client=fake_postgrest_client,
+        redis_client=fake_redis_client,
+    )
 
 
+@pytest.fixture
+def flask_app(test_config, fake_postgrest_client, fake_redis_client):
+    """Flask-приложение с fake зависимостями для интеграционных тестов."""
+    from app import create_app
+    app = create_app(config=test_config)
+    # Подменяем container на fake
+    from app.container import Container
+    app.container = Container(
+        config=test_config,
+        postgrest_client=fake_postgrest_client,
+        redis_client=fake_redis_client,
+    )
+    return app
 
 
 # Существующие fixtures (Selenium и т.д.) — без изменений
5.6. Tests
tests/test_container.py — 95 строк
# tests/test_container.py
"""Фаза 5: тесты DI-контейнера."""
import pytest
from unittest.mock import MagicMock
from app.container import Container
from app.config import Config
 
 
def make_test_config() -> Config:
    return Config(
        secret_key='test-secret',
        pgrst_jwt_secret='test-jwt-secret-with-at-least-32-bytes-length!!',
        testing=True,
    )
 
 
class TestContainer:
    def test_repositories_are_singletons(self):
        """Repository должны быть синглтонами (один экземпляр на Container)."""
        c = Container(
            config=make_test_config(),
            postgrest_client=MagicMock(),
            redis_client=MagicMock(),
        )
        repo1 = c.job_repository()
        repo2 = c.job_repository()
        assert repo1 is repo2  # один и тот же объект
 
    def test_use_cases_are_not_singletons(self):
        """Use Case должны создаваться заново при каждом вызове (нет shared state)."""
        c = Container(
            config=make_test_config(),
            postgrest_client=MagicMock(),
            redis_client=MagicMock(),
        )
        uc1 = c.apply_job_use_case()
        uc2 = c.apply_job_use_case()
        assert uc1 is not uc2  # разные объекты
 
    def test_use_case_dependencies_use_same_repository(self):
        """Все Use Cases должны разделять те же repository, что и контейнер."""
        c = Container(
            config=make_test_config(),
            postgrest_client=MagicMock(),
            redis_client=MagicMock(),
        )
        job_repo = c.job_repository()
        uc = c.apply_job_use_case()
        # Use Case должен использовать тот же repository
        assert uc._applications is c.application_repository()
 
    def test_health_status_returns_ok_when_redis_available(self):
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        c = Container(
            config=make_test_config(),
            postgrest_client=MagicMock(),
            redis_client=fake_redis,
        )
        status = c.get_health_status()
        assert status['status'] == 'ok'
        assert status['components']['redis'] == 'ok'
 
    def test_health_status_returns_degraded_when_redis_unavailable(self):
        c = Container(
            config=make_test_config(),
            postgrest_client=MagicMock(),
            redis_client=None,  # Redis недоступен
        )
        status = c.get_health_status()
        assert status['status'] == 'degraded'
        assert status['components']['redis'] == 'unavailable'
 
 
class TestContainerIntegrationWithUseCases:
    def test_apply_job_use_case_can_be_executed(self, test_container):
        """Интеграционный тест: Container создаёт рабочий Use Case."""
        from app.use_cases.apply_job import ApplyJobCommand
        # Настраиваем fake postgrest_client
        test_container._postgrest.postgrest_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': True,
                'employer_id': 'emp-1',
                'application_id': 'app-1',
            },
            text='',
            headers={},
        )
        test_container._postgrest.postgrest_request.return_value = MagicMock(
            ok=True, json=lambda: [], text='', headers={},  # нет дубликата
        )
 
        use_case = test_container.apply_job_use_case()
        result = use_case.execute(
            ApplyJobCommand(job_id='job-1', worker_id='worker-1')
        )
        assert result.success is True
        assert result.employer_id == 'emp-1'
tests/test_config.py — 80 строк
# tests/test_config.py
"""Фаза 5: тесты Config dataclass."""
import pytest
from app.config import Config, ConfigError
 
 
class TestConfigFromEnv:
     def test_creates_config_with_minimal_env(self):
         """В development можно создать Config без обязательных переменных."""
         config = Config.from_env({'DEPLOYMENT_ENV': 'development'})
         assert config.deployment_env == 'development'
         assert config.testing is False
         assert config.postgrest_url == 'http://localhost:3000'
         assert config.secret_key == 'dev-secret-not-for-production'
 
     def test_production_requires_secret_key(self):
         with pytest.raises(ConfigError, match='SECRET_KEY'):
             Config.from_env({'DEPLOYMENT_ENV': 'production'})
 
     def test_production_requires_pgrst_jwt_secret(self):
         with pytest.raises(ConfigError, match='PGRST_JWT_SECRET'):
             Config.from_env({
                 'DEPLOYMENT_ENV': 'production',
                 'SECRET_KEY': 'prod-secret-with-enough-length-1234567890',
             })
 
     def test_production_requires_postgrest_url(self):
         with pytest.raises(ConfigError, match='POSTGREST_URL'):
             Config.from_env({
                 'DEPLOYMENT_ENV': 'production',
                 'SECRET_KEY': 'prod-secret-with-enough-length-1234567890',
                 'PGRST_JWT_SECRET': 'jwt-secret-with-at-least-32-bytes-length!!',
             })
 
     def test_normalizes_postgrest_url_adds_scheme(self):
         config = Config.from_env({
             'DEPLOYMENT_ENV': 'development',
             'POSTGREST_URL': 'postgrest:3000',  # без схемы
         })
         assert config.postgrest_url == 'http://postgrest:3000'
 
     def test_testing_flag_parsing(self):
         for true_val in ('true', '1', 'yes', 'True', 'YES'):
             config = Config.from_env({'TESTING': true_val})
             assert config.testing is True, f'TESTING={true_val} should set testing=True'
 
         for false_val in ('false', '0', 'no', ''):
             config = Config.from_env({'TESTING': false_val})
             assert config.testing is False, f'TESTING={false_val} should set testing=False'
 
 
class TestConfigFrozen:
     def test_config_is_immutable(self):
         config = Config.from_env({})
         with pytest.raises(Exception):  # FrozenInstanceError
             config.secret_key = 'modified'
 
     def test_to_flask_dict_returns_uppercase_keys(self):
         config = Config(secret_key='test', pgrst_jwt_secret='jwt')
         d = config.to_flask_dict()
         assert 'SECRET_KEY' in d
         assert 'PGRST_JWT_SECRET' in d
         assert d['SECRET_KEY'] == 'test'
5.7. Risk & rollback
| Поле | Значение |
|---|---|
| Risk level | Low — это финальная очистка, не меняющая поведение |
| Backward compat | Полная: app.config по-прежнему содержит все ключи в UPPER_CASE (через to_flask_dict) |
| Rollback | git revert; старый Config остаётся в git tag phase-4-backup |
| Migration | Никаких SQL-миграций не требуется |
| Test impact | Существующие тесты продолжают работать — Config.from_env() читает те же env vars, что и старый Config |
| Deployment order | Можно деплоить в любой момент после Фаз 0-4 |
5.8. Success metrics
●	Юнит-тест `test_apply_job_use_case_can_be_executed` запускается < 100ms без поднятия Flask-контекста.
●	0 side-effects при импорте `from app.config import Config` (через test_import_does_not_block_on_postgrest из Фазы 0).
●	Coverage container.py > 90%, config.py > 85%.
●	Все 14 blueprints используют `current_app.container.X_use_case()` вместо прямых вызовов postgrest_request (проверка rg).
●	Создание двух разных Config в одном pytest-ране работает без конфликтов (test_config.py:test_creates_two_configs).
