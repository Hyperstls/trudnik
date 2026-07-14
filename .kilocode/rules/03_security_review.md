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
```