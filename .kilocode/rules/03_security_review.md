@rule review
При ревью кода ОБЯЗАТЕЛЬНО проверяй:

1. XSS: Весь динамический контент в innerHTML должен проходить через escapeHtml() или использовать textContent.
2. CSRF: Все мутирующие запросы (POST/PUT/PATCH/DELETE) должны содержать X-CSRF-Token заголовок.
3. SQL-инъекции: Не должно быть format() или f-string с пользовательским вводом в SQL-запросах.
4. Утечки секретов: Не должно быть hardcoded SECRET_KEY, PGRST_JWT_SECRET, паролей.
5. Open Redirect: Не использовать redirect(request.referrer) без safe_redirect().
6. Раскрытие ошибок: Не использовать flash(f'...: {resp.text}') — использовать safe_error_message().
7. Race conditions: Проверять атомарность RPC (FOR UPDATE в PL/pgSQL).
8. Соединения с БД: Везде, где используется psycopg2, должен быть finally: conn.close().
9. Email: Везде должен быть .lower() после .strip().
10. Datetime: Не должно быть datetime.utcnow() или datetime.now() без timezone.utc.
11. Rate Limiting: sensitive-эндпоинты (login, register, reset password, OTP) должны быть ограничены (Config: RATE_LIMIT_MAX=10 / RATE_LIMIT_WINDOW=60).
12. Circuit Breaker: все вызовы PostgREST идут через CircuitBreaker (CB_FAILURE_THRESHOLD=10, CB_RECOVERY_TIMEOUT=60; 403 НЕ размыкает цепь). Не обходи CB прямыми requests вне postgrest_client.
13. CSP: инлайн-<script>/<style> требуют CSP nonce. Не вставляй инлайн-скрипты без nonce; динамические данные — через data-* атрибуты или отдельные JS-файлы.
14. Uploads: проверяй размер (MAX_PHOTO_SIZE_MB=5 → MAX_UPLOAD_SIZE) и MIME/расширение; защищайся от path traversal в именах файлов (не доверяй user-supplied filename для пути).
15. JWT app_role: app_role должен браться из сессии/БД (session['role'] в get_user_headers), НЕ из клиентского ввода. Проверяй, что role нельзя подменить с клиента.
16. Внешние ключи: TURNSTILE_SECRET_KEY, YANDEX_GEOCODER_KEY, VAPID_PRIVATE_KEY — только из env; не хардкодить, не логировать, не возвращать клиенту (VAPID_PUBLIC_KEY — можно).
```