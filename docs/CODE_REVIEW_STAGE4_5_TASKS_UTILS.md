# Этапы 4-5: Ревью Celery-задач и утилит

Дата: 2026-06-22 / Ветка: main / Файлов: 5
Контекст: Flask + Celery + Redis + Supabase, проект Trudnik

---

---

## Часть 1: Celery-задачи

### 1. [app/tasks/celery_app.py](app/tasks/celery_app.py)

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|-------------|----------|--------|--------------|
| 1 | MEDIUM | broker_connection_retry_on_startup -- устаревший параметр в Celery 5.3+; переименован в broker_connection_retry | 66 | Заменить на broker_connection_retry=True |
| 2 | MEDIUM | beat_schedule задан в float-секундах (3600.0, 86400.0) -- менее читаемо, чем timedelta | 81,89 | Использовать schedule=timedelta(hours=1) |
| 3 | MEDIUM | cleanup-expired-push-subscriptions: expires=3000 (50 мин) при schedule=3600 -- малый запас | 83 | Увеличить expires до 3300 (55 минут) |
| 4 | LOW | Отсутствует task_create_missing_queues -- кастомные очереди упадут с UnknownQueue | 48-68 | Добавить task_create_missing_queues=True |
| 5 | LOW | task_time_limit=300 может быть мало для cleanup_expired_subscriptions | 58-59 | Per-task time_limit для cleanup (600 сек) |
| 6 | LOW | broker_connection_max_retries=10 без broker_connection_retry_delay -- 10 попыток без backoff | 67 | Добавить broker_connection_retry_delay=2 |


### 2. [app/tasks/email_tasks.py](app/tasks/email_tasks.py)

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
|1|HIGH|send_batch_email_notifications запускает .delay() в синхронном цикле for -- при 1000 получателей блокирует worker|264-282|celery.group(send_email_notification.s(...) for r in recipients).apply_async()|
|2|HIGH|Fallback HTML при ошибке рендеринга: f-строки с user_name и notification_text без экранирования -- XSS-вектор|151-162|html.escape() / markupsafe.escape() для пользовательских данных|
|3|HIGH|results[chr(39)deadchr(39)] = 0 инициализирован, но никогда не увеличивается -- счётчик всегда 0|262|Убрать неиспользуемый ключ dead|
|4|MEDIUM|_log_to_db ловит исключения и возвращает False, но вызывающий код НЕ проверяет возвращаемое значение|80-82,193-203|logger.warning при возврате False из _log_to_db|
|5|MEDIUM|Дублирование retry-логики: блоки except Exception (172-203) и else: not success (223-239) почти идентичны|172-239|Извлечь общий _handle_retry_or_dead(self, ...)|
|6|MEDIUM|send_email_notification создаёт новый EmailService() на каждый вызов -- каждый экземпляр открывает новый SMTP-коннект (Stage3 Finding 4)|115|Передавать EmailService как параметр задачи или синглтон с connection pooling|
|7|MEDIUM|cleanup_old_email_logs парсит Content-Range хрупким способом -- при изменении формата заголовка сломается|303-311|HEAD + Content-Range для предварительного подсчёта|
|8|LOW|_log_to_db требует notification_id: int, но для системных уведомлений без ID -- потенциальная FK-ошибка|49|Сделать notification_id опциональным (Optional[int])|
|9|LOW|import os и from datetime import date внутри тела функции -- нарушение PEP 8|113,127|Вынести импорты на уровень модуля|

### 3. push_tasks.py

| # | Серьёзность | Проблема | Строка | Рекомендация |
|1|MEDIUM|cleanup_expired_subscriptions загружает ВСЕ подписки -- worker заблокирован|72-100|Пагинация limit=100 + time.sleep|
|2|MEDIUM|user_id: str vs int inconsistency|16|Унифицировать как str|
|3|MEDIUM|retry без проверки не-повторяемых ошибок|48-55|410 Gone - подписку|
|4|LOW|default_retry_delay переопределяется|15,54|Убрать из декоратора|
|5|LOW|нет MaxRetriesExceededError|58|autoretry_for|
