@rule code
Доступ к данным через PostgREST. Реализация: app/utils/postgrest_client.py.

ПРИНЦИП: данные — через эти функции; НЕТ ORM и raw SQL для бизнес-логики (см. 01_db_access.md).

⚠️ КРИТИЧЕСКИЕ ПАТТЕРНЫ (PostgREST v14 + миграция 132):
  - profiles ограничена COLUMN-LEVEL SELECT (132): password_hash/email/inn/phone/verification_doc_url НЕ читаются клиентом.
  - Чтения profiles БЕЗ select= → 401 (PostgREST пытается вернуть все колонки). ВСЕГДА указывай select=<публичные поля>.
  - PATCH/POST на profiles: postgrest_client._normalize_endpoint() АВТОМАТИЧЕСКИ добавляет select=public. НЕ отключай.
  - Новые RPC (из миграций) НЕВИДИМЫ PostgREST (404 PGRST202) до NOTIFY pgrst 'reload schema'. Self-heal делает это автоматически (шаг 1g).

Класс ответа — PostgrestResponse (НЕ Pydantic, НЕ requests.Response):
  resp.ok: bool
  resp.status_code: int
  resp.json() -> dict | list | None   (приоритет: предзагруженные data, иначе json.loads(text))
  resp.text: str
  resp.headers: Mapping
  resp.circuit_open: bool              (True если ответ — заглушка от разомкнутого Circuit Breaker)

Функции:
  postgrest_request(method, endpoint, **kwargs) -> PostgrestResponse
    Пользовательский JWT (роль из session). Авто-refresh access_token при 401.
    method ∈ {GET, POST, PATCH, DELETE}; endpoint напр. 'jobs?status=eq.open'. Timeout 30с.
  postgrest_admin_request(method, endpoint, **kwargs) -> PostgrestResponse
    JWT role='service_role' — ОБХОД RLS. Только серверная сторона (blueprints/services/tasks/scripts).
    НИКОГДА не вызывать из шаблонов Jinja2. Есть ограничение по вызывающему модулю (_ADMIN_ALLOWED_PREFIXES). Timeout 30с.
  postgrest_rpc(function_name, params: dict, use_admin=False) -> PostgrestResponse
    Вызов PL/pgSQL RPC (напр. accept_application, apply_job_atomic). use_admin=True → service_role. Timeout 60с.

Заголовки:
  get_service_role_headers() / get_user_headers(user_id=None)
  Оба добавляют X-Request-ID из g.request_id (если есть) для сквозной трассировки.

Circuit Breaker (CircuitBreaker):
  - Два инстанса: _cb_postgrest (польз.), _cb_admin.
  - failure_threshold=CB_FAILURE_THRESHOLD (default 10), recovery_timeout=CB_RECOVERY_TIMEOUT (default 60).
  - 403 НЕ размыкает цепь (проблема прав, не доступности сервиса).
  - В состоянии OPEN выполняется прямой health-check GET {POSTGREST_URL}/health.html (в обход CB) для быстрого восстановления.
  - is_circuit_open(resp) — проверить, что ответ — заглушка разомкнутой цепи.
  - get_circuit_breaker_state() — состояние обоих CB (для мониторинга/admin-дашборда).

Мок (тесты): при _is_mock_enabled() запросы идут в in-memory мок (app/testing/mock_postgrest.py), реальный HTTP/PostgreSQL не выполняется.
