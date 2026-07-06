@rule code
При работе с уведомлениями:

1. enqueue_notification() пишет в notification_outbox (таблица).
2. drain_notification_outbox (Celery Beat, 10 сек) читает outbox и вызывает notification_service.create().
3. notification_service.create() отправляет через:
   - Redis Pub/Sub → WebSocket (мгновенно)
   - Celery email_tasks.send_email_notification (email)
   - Celery push_tasks.send_push_notification (push)
4. НЕ используй threading.Thread для уведомлений — только Celery.
5. Проверяй prefs.get(type, True) — пользователь мог отключить уведомление.
```