# API Reference — Трудник (Trudnik)

> ⚠️ **ДОКУМЕНТ УСТАРЕЛ (архивный снимок 2026-06-17).** Содержит несуществующие
> эндпоинты (`/api/search/jobs`, `/api/search/workers` — фантомы; реальный
> поиск — HTML-каталог `/` и `/workers`) и не отражает изменения после
> 2026-08 (удаление Telegram-верификации, Turnstile → Yandex SmartCaptcha,
> admin-only `/messenger/diagnose`, новая страница `/faq`).
>
> **Актуальный справочник: docs/API_ENDPOINTS.md** (сгенерирован из кода,
> 146 маршрутов, 2026-08-16). Дополнительные источники: docs/RPC_REGISTRY.md
> (RPC-функции), docs/BUTTON_REGISTRY.md (UI-привязки).
> Оставлен для истории; НЕ использовать как источник истины.

> Полный справочник HTTP-эндпоинтов, AJAX-вызовов, кодов ошибок и контекстных переменных шаблонов.
> **Актуализировано:** 2026-06-17 | **Ветка:** `main`

---

## Общая информация

| Параметр | Значение |
|----------|----------|
| **Базовый URL** | Определяется окружением (локально `http://localhost:8000`, на проде — домен Amvera) |
| **Формат ответов** | HTML (страницы) / JSON (API-эндпоинты). API возвращает `application/json` |
| **Аутентификация** | JWT-токены нативной аутентификации (Amvera/PostgREST). Токен хранится в сессии Flask (`session['access_token']`), передаётся в заголовке `Authorization: Bearer <token>` при запросах к PostgREST REST API (Amvera). Supabase не используется |
| **CSRF-защита** | Глобальная проверка для всех мутирующих запросов (кроме `/login`, `/register`). Токен в `X-CSRF-Token` (AJAX) или `_csrf_token` (форма/JSON) |
| **Content-Security-Policy** | Строгая CSP с nonce-механизмом для inline-скриптов. `connect-src` разрешает `ws://localhost:* wss://*` для WebSocket |
| **Rate Limiting** | 10 POST-запросов в минуту с одного IP (in-memory) |
| **Circuit Breaker** | 10 последовательных ошибок → разрыв цепи на 60 секунд (HTTP 403 НЕ размыкает цепь) |

**Ключевые файлы:**
- [`app/__init__.py`](../app/__init__.py:1) — регистрация блюпринтов, security headers, CSRF, контекст-процессоры
- [`app/config.py`](../app/config.py:7) — бизнес-константы (лимиты, пороги)

---

## Таблица всех маршрутов по блюпринтам

Легенда уровней доступа:
- 🔓 **public** — без аутентификации
- 👤 **worker** — только трудник
- 🏢 **employer** — только работодатель
- 👑 **admin** — только администратор
- 🔒 **auth** — любой аутентифицированный пользователь

---

### auth ([`app/blueprints/auth.py`](../app/blueprints/auth.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/login` | 🔓 public | Форма входа |
| POST | `/login` | 🔓 public | Аутентификация через нативный JWT PostgREST (Amvera). Сохраняет `access_token`, `refresh_token`, `user_id`, `role` в сессию. Редирект: employer → `/my-jobs`, worker → `/`. Supabase не используется |
| GET | `/register` | 🔓 public | Форма регистрации |
| POST | `/register` | 🔓 public | Регистрация через нативную аутентификацию (Amvera). Создаёт профиль с ролью, навыками (через `user_skills`), ИНН (для worker), контактами. Валидация: обязательные поля, ИНН (12 цифр). Supabase Auth не используется |
| GET | `/logout` | 🔒 auth | Очистка сессии, редирект на `/login` |

---

### jobs ([`app/blueprints/jobs.py`](../app/blueprints/jobs.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/` | 🔓 public | Главная страница: список заданий с фильтрами (город, оплата, радиус, навыки, религия, сортировка). Исключает задания от заблокировавших работодателей |
| GET | `/workers` | 🔓 public | Список трудников с фильтрами (город, радиус, навыки, рейтинг, сортировка). Исключает заблокированных |
| GET | `/jobs/<id>` | 🔓 public | Детали задания: описание, фото, карта (Яндекс), отклики (для владельца), кнопки действий |
| GET | `/job/new` | 🏢 employer | Форма создания задания |
| POST | `/job/new` | 🏢 employer | Создание задания. Валидация: стоп-слова, обязательные поля, геокодирование адреса (Яндекс). `is_paid=True`, `status='open'` |
| GET | `/job/<id>/edit` | 🏢 employer | Форма редактирования. Проверка владельца через `check_job_owner()` |
| POST | `/job/<id>/edit` | 🏢 employer | Сохранение изменений. Валидация стоп-слов, геокодирование при смене адреса |
| GET | `/my-jobs` | 🏢 employer | Список заданий работодателя с фильтрацией по статусу |
| GET | `/invitations` | 🔒 auth | Список приглашений (отправленных и полученных) |
| POST | `/favorite-job/<id>` | 🔒 auth | Добавить задание в избранное |
| POST | `/job/<id>/toggle-status` | 🏢 employer | Смена статуса задания (open ↔ completed). Проверка владельца |
| POST | `/job/<id>/duplicate` | 🏢 employer | Дублирование задания. Копирует поля через `copy_job()`, сбрасывает `current_workers=0`, `status='open'` |
| GET | `/job/<id>/workers` | 🏢 employer | Список принятых трудников на задании (для отправки чеков) |

---

### jobs_api ([`app/blueprints/jobs_api.py`](../app/blueprints/jobs_api.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/api/skills` | 🔓 public | Список навыков из справочника `skills` (JSON) |
| GET | `/api/religions` | 🔓 public | Список религий из справочника `religions` (JSON) |
| GET | `/api/search/jobs` | 🔓 public | Поиск заданий (JSON). Поддерживает: `q` (FTS), `city`, `status`, `min_pay`, `max_pay`, `date_from`, `date_to`, `available_slots`, `skills`, `religion`, `page`, `per_page`, `sort`, `lat`, `lng`, `radius` |
| GET | `/api/search/workers` | 🔓 public | Поиск трудников (JSON). Поддерживает: `q` (FTS), `skills`, `rating_min`, `city`, `lat`, `lng`, `radius`, `page`, `per_page`, `sort` |
| POST | `/api/invite` | 🏢 employer | Пригласить трудника на задание. Создаёт запись в `invitations` (status=pending). Отправляет уведомление. Проверки: дубликат приглашения, владелец задания, статус задания |
| GET | `/api/invitations/<id>` | 🔒 auth | Детали приглашения (JSON). Проверка: участник приглашения |

---

### applications ([`app/blueprints/applications.py`](../app/blueprints/applications.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| POST | `/apply/<job_id>` | 👤 worker | Отклик на задание. Проверки: дубликат, владелец (не свой), чёрный список, статус=open, свободные места (`current_workers < max_workers`). Создаёт заявку (status=pending). Отправляет уведомление работодателю |
| POST | `/apply-selected` | 👤 worker | Массовый отклик на выбранные задания (из чекбоксов на странице) |
| GET | `/my-applications` | 👤 worker | Список откликов трудника с фильтрацией по статусу |
| POST | `/api/applications/batch` | 🏢 employer | Массовое действие над заявками: accept/reject. Вызывает `accept_application`/`reject_application` RPC для каждой |
| POST | `/cancel-application/<id>` | 👤 worker | Отменить отклик (status=withdrawn). Проверка: владелец отклика, окно отзыва (12 часов до начала) через `check_withdraw_window()` |

---

### API на app ([`app/__init__.py`](../app/__init__.py:273))

Вынесены на объект `app` (исторически — из-за проблем с blueprint-роутингом на production/Amvera).

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| POST | `/api/applications/<id>/accept` | 🏢 employer | Принять отклик. Вызывает RPC `accept_application` (атомарно: обновляет статус заявки + `current_workers`). Отправляет уведомление труднику |
| POST | `/api/applications/<id>/reject` | 🏢 employer | Отклонить отклик. Вызывает RPC `reject_application`. Отправляет уведомление труднику |
| POST | `/api/applications/<id>/reopen` | 🏢 employer | Переоткрыть ранее принятую/отклонённую заявку (status=pending). Без rate-limit (административное действие) |

---

### admin_* (6 блюпринтов: admin_dashboard / admin_users / admin_jobs / admin_verification / admin_dictionaries / admin_diagnostics) ([`app/blueprints/admin_dashboard.py`](../app/blueprints/admin_dashboard.py:1))

> Отдельного `admin.py` НЕТ — функции расщеплены по 6 blueprint'ам `admin_*`.

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/admin` | 👑 admin | Админ-панель: дашборд (статистика пользователей/заданий/верификаций), управление пользователями, заданиями, справочниками. Параметр `?tab=` (dashboard/users/jobs/verification/dictionaries) |
| GET | `/admin/users` | 👑 admin | Управление пользователями: поиск, фильтрация по роли |
| POST | `/admin/users` | 👑 admin | Создание/редактирование пользователя (admin) |
| GET | `/admin/jobs` | 👑 admin | Управление заданиями: поиск, фильтрация по статусу |
| POST | `/admin/jobs` | 👑 admin | Создание/редактирование задания (admin) |
| GET | `/admin/dictionaries` | 👑 admin | Управление справочниками (навыки, религии) |
| POST | `/admin/dictionaries` | 👑 admin | Добавление/редактирование записей справочников |
| POST | `/admin/verify-employer/<id>` | 👑 admin | Верификация работодателя (установка `verification_status='verified'`) |
| POST | `/admin/delete-user/<id>` | 👑 admin | Каскадное удаление пользователя через RPC `delete_user_cascade` |
| GET | `/api/health` | 👑 admin | Health check для админ-панели (JSON) |

---

### profile ([`app/blueprints/profile.py`](../app/blueprints/profile.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/profile` | 🔒 auth | Просмотр профиля. Для работодателя: показывает статистику, статус верификации |
| GET | `/profile/update` | 🔒 auth | Форма редактирования профиля |
| POST | `/profile/update` | 🔒 auth | Сохранение профиля: имя, город, навыки, контакты, фото, ИНН, самозанятость. Загрузка фото через локальное хранилище (Amvera). Supabase Storage не используется |
| POST | `/verify-employer` | 🏢 employer | Запрос верификации работодателя (`verification_status='pending'`) |
| POST | `/profile/delete-account` | 🔒 auth | Удаление аккаунта. Требует подтверждения паролем. Вызывает RPC `delete_user_cascade` |

---

### chat ([`app/blueprints/chat.py`](../app/blueprints/chat.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/chats` | 🔒 auth | Список чатов: все accepted-заявки, где пользователь участник |
| GET | `/chat/<application_id>` | 🔒 auth | Чат по заявке. Проверка: пользователь — участник (worker_id или employer_id через job). Загружает историю сообщений |
| GET | `/chat/new/<worker_id>` | 🏢 employer | Поиск существующего accepted-чата с работником → редирект |
| POST | `/api/send_message` | 🔒 auth | Отправить сообщение. Валидация: длина ≤ 2000 символов. XSS-санитизация через `html.escape()`. Публикация в Redis для WebSocket-доставки. Отправка уведомления собеседнику |
| GET | `/api/messages/poll` | 🔒 auth | Long-polling сообщений (GET-параметр `after` — временная метка). Возвращает новые сообщения с момента `after` |
| POST | `/api/delete-chats` | 🔒 auth | Удаление выбранных чатов (application_id) — очистка сообщений |

---

### employers ([`app/blueprints/employers.py`](../app/blueprints/employers.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/employers` | 🔓 public | Список работодателей с фильтрами (город, радиус, поиск, верификация, сортировка) |
| GET | `/employers/<id>` | 🔓 public | Детали работодателя: профиль, статистика, активные задания, отзывы |
| POST | `/api/employers/favorite` | 🔒 auth | Добавить работодателя в избранное |
| DELETE | `/api/employers/favorite` | 🔒 auth | Убрать работодателя из избранного |

---

### favorites ([`app/blueprints/favorites.py`](../app/blueprints/favorites.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/favorites` | 🔒 auth | Страница избранного: задания и работодатели |
| POST | `/favorite/<type>/<id>` | 🔒 auth | Добавить в избранное. `type`: `job` или `employer`. `id`: UUID задания или работодателя |
| POST | `/unfavorite/<type>/<id>` | 🔒 auth | Убрать из избранного |
| GET | `/api/favorites/status` | 🔒 auth | Статусы избранного для списка ID (JSON). Параметр `?ids=uuid1,uuid2&type=job` |

---

### notifications ([`app/blueprints/notifications.py`](../app/blueprints/notifications.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/notifications` | 🔒 auth | Список уведомлений с пагинацией |
| POST | `/api/notifications/read` | 🔒 auth | Отметить уведомление прочитанным (`is_read=true`). Тело: `{"id": "uuid"}` |
| POST | `/api/notifications/read-all` | 🔒 auth | Отметить все уведомления прочитанными |
| GET | `/api/notifications/settings` | 🔒 auth | Получить настройки уведомлений (JSON) |
| POST | `/api/notifications/settings` | 🔒 auth | Сохранить настройки уведомлений (какие типы включены, email_enabled, push_enabled) |
| POST | `/api/push/subscribe` | 🔒 auth | Подписка на Web Push. Сохраняет `endpoint`, `keys` (p256dh, auth) в `push_subscriptions` |
| POST | `/api/push/unsubscribe` | 🔒 auth | Отписка от Web Push. Удаляет запись подписки |

---

### ratings ([`app/blueprints/ratings.py`](../app/blueprints/ratings.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| POST | `/api/ratings` | 🔒 auth | Создать/обновить оценку (UPSERT). Тело: `{"rated_user_id": "uuid", "rating": 1-5, "comment": "text", "job_id": "uuid"}`. Проверки: нельзя оценить себя, участие в задании |
| GET | `/ratings/user/<id>` | 🔓 public | Оценки пользователя (список отзывов) |
| GET | `/jobs/<id>/rate-workers` | 🏢 employer | Форма оценки трудников после завершения задания |

---

### blacklist ([`app/blueprints/blacklist.py`](../app/blueprints/blacklist.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/blacklist` | 🔒 auth | Чёрный список пользователя (заблокированные) |
| POST | `/blacklist/<id>` | 🔒 auth | Заблокировать пользователя. Проверка: не себя, не дубликат |
| POST | `/unblock/<id>` | 🔒 auth | Разблокировать пользователя. Проверка: запись существует и принадлежит текущему пользователю |

---

### seo ([`app/blueprints/seo.py`](../app/blueprints/seo.py:1))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/robots.txt` | 🔓 public | Файл robots.txt для поисковых роботов |
| GET | `/sitemap.xml` | 🔓 public | Карта сайта (XML) |

---

### Прочие маршруты (в [`app/__init__.py`](../app/__init__.py:296))

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/sw.js` | 🔓 public | Service Worker для PWA (раздаётся как статический файл) |
| GET | `/offline` | 🔓 public | Офлайн-страница (fallback при отсутствии сети) |
| GET | `/.well-known/assetlinks.json` | 🔓 public | Digital Asset Links для Trusted Web Activity (Google Play верификация) |
| GET | `/health` | 🔓 public | Health check: проверка подключения к БД. Возвращает `{"status": "healthy", "database": "connected"}` или `503` |

---

## AJAX-эндпоинты

Сводка вызовов fetch/AJAX из фронтенда (источники указаны по blueprint'ам):

| Источник (Blueprint) | Метод | URL | Назначение |
|----------------------|-------|-----|------------|
| `app/blueprints/jobs_api.py` | GET | `/api/search/jobs` | AJAX-поиск заданий (фильтры, FTS, гео) |
| `app/blueprints/jobs_api.py` | GET | `/api/search/workers` | AJAX-поиск трудников |
| `app/blueprints/chat.py` | POST | `/api/send_message` | Отправка сообщения в чате |
| `app/blueprints/chat.py` | GET | `/api/messages/poll` | Long-polling новых сообщений |
| `app/blueprints/notifications.py` | POST | `/api/notifications/read` | Отметить одно уведомление |
| `app/blueprints/notifications.py` | POST | `/api/notifications/read-all` | Отметить все уведомления |
| `app/blueprints/notifications.py` | GET/POST | `/api/notifications/settings` | Настройки уведомлений |
| `app/blueprints/notifications.py` | POST | `/api/push/subscribe` | Подписка на push |
| `app/blueprints/notifications.py` | POST | `/api/push/unsubscribe` | Отписка от push |
| `app/__init__.py` | POST | `/api/applications/<id>/accept` | Принять отклик |
| `app/__init__.py` | POST | `/api/applications/<id>/reject` | Отклонить отклик |
| `app/__init__.py` | POST | `/api/applications/<id>/reopen` | Переоткрыть отклик |
| `app/blueprints/applications.py` | POST | `/api/applications/batch` | Массовое действие |
| `app/blueprints/favorites.py` | POST | `/favorite/<type>/<id>` | Добавить в избранное |
| `app/blueprints/favorites.py` | POST | `/unfavorite/<type>/<id>` | Убрать из избранного |
| `app/blueprints/favorites.py` | GET | `/api/favorites/status` | Статусы избранного |
| `app/blueprints/employers.py` | POST | `/api/employers/favorite` | Избранное (работодатели) |
| `app/blueprints/employers.py` | DELETE | `/api/employers/favorite` | Убрать из избранного |
| `app/blueprints/jobs_api.py` | POST | `/api/invite` | Пригласить трудника |
| `app/blueprints/ratings.py` | POST | `/api/ratings` | Создать/обновить оценку |
| `app/blueprints/admin_verification.py` | POST | `/admin/verify-employer/<id>` | Верификация работодателя |
| `app/blueprints/admin_users.py` | POST | `/admin/delete-user/<id>` | Удаление пользователя |
| `app/blueprints/admin_dashboard.py` | GET | `/api/health` | Health check админ-панели |
| `app/blueprints/chat.py` | POST | `/api/delete-chats` | Удаление чатов |

---

## HTTP-коды ошибок

| Код | Название | Когда возвращается |
|-----|----------|-------------------|
| **400** | Bad Request | CSRF-токен отсутствует или недействителен; невалидный JSON; слишком длинное сообщение в чате (>2000 символов) |
| **401** | Unauthorized | Недействительный/истёкший токен. Автоматически пробуется обновление через `refresh_access_token()` |
| **403** | Forbidden | Недостаточно прав (не та роль); отклик заблокирован (чёрный список); попытка доступа к чужому ресурсу |
| **404** | Not Found | Страница/ресурс не найден. Кастомная страница `error.html` |
| **409** | Conflict | Дубликат: уже откликались, уже в избранном, уже приглашены, уже в ЧС |
| **429** | Too Many Requests | Превышен лимит запросов (rate limiting: 10 POST/60 сек с одного IP) |
| **500** | Internal Server Error | Необработанное исключение. Кастомная страница `error.html` |
| **503** | Service Unavailable | Circuit Breaker разомкнут; PostgREST (Amvera) недоступен; ошибка соединения с БД. Кастомная страница `error.html`. Supabase не используется |

---

## Контекстные процессоры

Переменные, доступные во всех шаблонах Jinja2:

| Переменная | Тип | Источник | Описание |
|------------|-----|----------|----------|
| `current_user_id` | `str\|None` | [`app/__init__.py:22`](../app/__init__.py:22) | UUID текущего пользователя из сессии |
| `csrf_token` | `str` | [`app/__init__.py:26`](../app/__init__.py:26) | CSRF-токен для форм (`session['_csrf_token']`) |
| `csp_nonce` | `str` | [`app/__init__.py:33`](../app/__init__.py:33) | Случайный nonce для inline-скриптов (CSP) |
| `trudnik_ws_config` | `dict` | [`app/__init__.py:98`](../app/__init__.py:98) | Конфигурация WebSocket: `wsUrl`, `wsPort`, `pushEnabled`, `jwtToken` |
| `unread_notifications` | `int` | [`app/__init__.py:127`](../app/__init__.py:127) | Счётчик непрочитанных уведомлений (кеш 30 сек). Исключает приглашения |
| `pending_invitations` | `int` | [`app/__init__.py:156`](../app/__init__.py:156) | Счётчик непрочитанных приглашений для трудника (кеш 30 сек) |
| `git_version` | `str` | [`app/__init__.py:204`](../app/__init__.py:204) | Хеш последнего git-коммита (кешируется при старте) |
| `sort_url` | `callable` | [`app/__init__.py:208`](../app/__init__.py:208) | Функция `sort_url(sort_value)` для построения URL сортировки с сохранением параметров |
| `pending_app_count` | `int` | [`app/blueprints/jobs.py:38`](../app/blueprints/jobs.py:38) | Количество pending-откликов для работодателя |
| `current_user_role` | `str\|None` | [`app/blueprints/jobs.py:49`](../app/blueprints/jobs.py:49) | Роль текущего пользователя (`worker`/`employer`/`admin`) |

### Jinja2-фильтры

| Фильтр | Источник | Описание |
|--------|----------|----------|
| `format_date` | [`app/__init__.py:257`](../app/__init__.py:257) | Форматирование ISO-даты в человеко-читаемый вид на русском: «16 июня 2026, 00:47», «Сегодня, 14:30», «Вчера, 09:15» |
