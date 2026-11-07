# Внутренний error tracking (R039/R040, 152-ФЗ-safe)

**Дата:** 2026-11-07
**Статус:** R039 (таблица + middleware) и R040 (админка) — готово, тесты в `core.tests.test_error_events`.

## Зачем свой контур, а не Sentry

Sentry SaaS и аналоги отправляют стектрейсы (в них бывают email, телефоны,
URL с query, фрагменты данных) на зарубежную инфраструктуру. Для 152-ФЗ это
трансграничная передача ПДн и лишний риск. Поэтому события необработанных
ошибок складываются в **свою БД PostgreSQL** и смотрятся в **своей админке**.
Никаких новых внешних сервисов и SDK не добавляется.

## Что хранится

Таблица `error_events` (`migrations/163_error_events.sql`):

| Поле | Тип | Что содержит |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` |
| `created_at` | timestamptz | момент события, индекс `created_at DESC` |
| `exception_type` | varchar(200) | только имя класса исключения, напр. `ValueError` |
| `path` | varchar(500) | путь **без query string**, напр. `/jobs/42` |
| `method` | varchar(10) | `GET`, `POST`, … |
| `status_code` | int | всегда `500` |
| `user_id` | uuid FK `profiles` ON DELETE SET NULL | кто был авторизован (id, не email) |
| `frames` | jsonb | последние 20 фреймов: `{file, line, func}` |

Сознательно **не хранятся**: текст исключения и `str(exception)`, тело запроса,
заголовки (включая `Cookie`, `User-Agent`, `Referer`), query string (там бывают
email/телефоны в ссылках), IP-адрес, email и любые ПДн из сообщения ошибки.
`file` во фреймах — только `basename` (`views.py`), без абсолютных путей сервера.

## Как работает middleware

`core.middleware.ErrorEventMiddleware` (`djadmin/core/middleware.py`) стоит
в `MIDDLEWARE` сразу после `AuthenticationMiddleware` — к моменту `process_exception`
`request.user` уже определён.

- `Http404`, `PermissionDenied`, `ValidationError` — штатные ответы, событие
  не пишется. Оговорка: необработанный `ValidationError` в view Django отдаёт
  как 500, и такое событие будет потеряно (известное ограничение R039; в
  текущем коде валидация форм перехватывается до view).
- Любое другое исключение из view → одна строка в `error_events`, затем
  `return None`: обработка ошибки Django продолжается как обычно (500-страница).
- Любой сбой записи (нет таблицы, БД недоступна, кривой JSON) ловится: пишется
  `logger.exception("Не удалось сохранить ErrorEvent")`, исходный 500 не ломается.
  Это осознанный fail-open для диагностики: недоступность логгера не должна
  превращать одну ошибку в каскад.

## Ротация и объём

Таблица растёт только на необработанных 500 (не на 404). Для тестового контура
это единицы строк. В админке есть действие **«Удалить события старше 90 дней»**
(кнопка в списке, `action_purge_old`): удаляет только `created_at < now − 90d`,
свежие события не трогает. Автоматического расписания нет — очистка запускается
вручную, чтобы инцидент не «исчез» во время разбора. `delete_selected` убран,
чтобы нельзя было снести всё одним кликом.

## Доступ

- Запись — приложением (`trudnik_dj`): `GRANT SELECT, INSERT, DELETE`.
- Просмотр — staff/superuser в `/admin/core/errorevent/`: read-only список
  (`created_at`, `exception_type`, `method`, `path`, `status_code`, `user_id`),
  фильтры по типу/методу/дате, поиск по `path`, фреймы в `<pre>` (автоэкранирование).
  Правка и добавление запрещены (`has_add_permission=False`,
  `has_change_permission=False`).
- В админке нет email/full_name: показывается только `user_id` (UUID). Ссылка на
  раздел — на главной `/admin/` в группе «Платформа».
- RLS не включается: email/имени/текста в таблице нет, `user_id` — псевдоним
  (UUID без контактов); доступ ограничен ролью приложения и staff-правами Django.
  Выгрузок во внешние сервисы нет.

## Проверки

R039/R040: `core.tests.test_error_events` + `test_flows/test_admin/test_public_views`
(контракт: событие создаётся, 404/403 — нет, текст/query/email не сохраняются,
сбой записи не ломает 500, в админке нет email/full_name). Локально и в CI —
`manage.py test core --keepdb`.

## Эксплуатация

1. После деплоя миграции `163` проверить `\d error_events` и пустой `SELECT count(*)`.
2. При 500 в проде: админка → «События ошибок» → фильтр по дате/типу → `path` +
   `frames` обычно достаточны, чтобы найти view и строку.
3. Если событий нет, а 500 есть — смотреть `getRunLogs` Amvera: значит, сбой
   произошёл до/вне middleware (например, в самом middleware) или запись
   ErrorEvent не удалась (в логе будет `Не удалось сохранить ErrorEvent`).
