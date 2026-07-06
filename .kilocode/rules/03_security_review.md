@rule reviewОБЯЗАТЕЛЬНО проверяй:

XSS: innerHTML с динамическими данными ДОЛЖЕН быть через escapeHtml() или заменён на textContent.
Datetime: НЕ должно быть datetime.now() без timezone.utc или datetime.utcnow().
PostgREST: Все ответы должны парситься через PostgrestResponse, никаких raw requests.
CSRF: fetch monkey-patch должен добавлять X-CSRF-Token только для same-origin POST/PUT/PATCH/DELETE.
Secrets: Запрещены flash(f'...: {resp.text}'), только safe_error_message(resp).