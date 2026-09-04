# Справочник REST-эндпоинтов «Трудник»

Дата: 2026-09-04 (мультирольность). Источник: статический разбор `@*_bp.route` в `app/blueprints/*.py` (146 маршрутов, 20 blueprints). Назначения — из docstring view-функций.

**ЛЕГЕНДА Role (мультирольность 2026-09-04):** guest — без аутентификации; **all — любой авторизованный** (роль НЕ барьер: создавать задания и откликаться может каждый); owner — только владелец ресурса (проверка `job.employer_id == user_id` / участник application в коде или RPC); admin — сессия администратора; admin (X-Admin-Token) — по заголовку вместо сессии. Бывшие role_required('worker'/'employer') удалены — доступ определяется владением/участием; `profiles.worker_visibility` управляет лишь каталогом `/workers` и приглашениями.

**Легенда CSRF:** все POST/PUT/PATCH/DELETE проверяются CSRF-middleware (X-CSRF-Token header или _csrf_token в form/JSON), ИСКЛЮЧЕНИЯ: `/messenger/webhook/*` (внешние webhook'и, middleware.py), `/admin/reset-circuit-breaker` (X-Admin-Token), `/api/client-error` (sendBeacon, токен в теле JSON).

⚠️ Примечание безопасности: `/admin/health` доступен без аутентификации (диагностика, только timestamp — задокументированное решение); `/uploads/avatars/*` публичный, `/uploads/verification-docs/*` — только авторизованные. `/messenger/diagnose` закрыт admin_required с 2026-08-16 (ранее был публичным).


## admin_dashboard — админ-дашборд

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/health` | GET | guest (публичный) | Проверка работоспособности приложения | — | JSON |
| `/admin` | GET | admin | Админ-панель: дашборд, пользователи, задания, верификация | — | HTML |

## admin_diagnostics — админ-диагностика

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/job-stats` | GET | admin | Статистика заданий для админ-дашборда | — | JSON |
| `/admin/migrations-status` | GET | admin (X-Admin-Token) | Return the list of applied migrations from _migrations tracking table | — | JSON |
| `/admin/reset-circuit-breaker` | POST | admin (X-Admin-Token) | Сбросить Circuit Breaker PostgREST-клиента в состояние CLOSED | X-Admin-Token | JSON |

## admin_dictionaries — справочники (навыки/религии)

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/skills` | GET | admin |  | — | JSON |
| `/admin/skills` | POST | admin |  | да | JSON |
| `/admin/skills/reorder` | POST | admin |  | да | JSON |
| `/admin/skills/<skill_id>` | PUT | admin |  | да | JSON |
| `/admin/skills/<skill_id>` | DELETE | admin |  | да | JSON |
| `/admin/bulk-delete-skills` | POST | admin |  | да | JSON |
| `/admin/religions` | GET | admin |  | — | JSON |
| `/admin/religions` | POST | admin |  | да | JSON |
| `/admin/religions/reorder` | POST | admin |  | да | JSON |
| `/admin/religions/<religion_id>` | PUT | admin |  | да | JSON |
| `/admin/religions/<religion_id>` | DELETE | admin |  | да | JSON |
| `/admin/bulk-delete-religions` | POST | admin |  | да | JSON |

## admin_jobs — админ-управление заданиями

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/jobs/<job_id>/status` | POST | admin | Изменить статус задания (admin) | да | REDIR |
| `/admin/jobs/<job_id>/delete` | POST | admin |  | да | REDIR |
| `/admin/bulk-delete-jobs` | POST | admin |  | да | JSON |

## admin_users — админ-управление пользователями

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/users/<user_id>/role` | POST | admin |  | да | REDIR |
| `/admin/users/<user_id>/delete` | POST | admin |  | да | REDIR |
| `/admin/users/<user_id>/unsuspend` | POST | admin | Phase 3: ручная разморозка пользователя администратором | да | REDIR |
| `/admin/complaints` | GET | admin | Phase 3: очередь жалоб для ручной модерации администратором | — | HTML |
| `/admin/complaints/<report_id>/review` | POST | admin | Рассмотреть жалобу: block (заморозить) или dismiss (отклонить) | да | REDIR |
| `/admin/bulk-delete-users` | POST | admin |  | да | JSON |
| `/admin/test-user` | GET,POST | admin | Создание тестового пользователя с подтверждённым email (без реальной почты) | да | HTML |
| `/admin/content/<slug>` | GET,POST | admin | Редактирование текста /terms или /privacy (хранится в site_pages) | да | HTML |

## admin_verification — верификация работодателей (админ)

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/admin/approve/<user_id>` | POST | admin |  | да | REDIR |
| `/admin/reject/<user_id>` | POST | admin |  | да | REDIR |

## applications — отклики

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/apply/<job_id>` | POST | all (авториз.) |  | да | JSON |
| `/apply-selected` | POST | worker |  | да | REDIR |
| `/unapply/<job_id>` | POST | all (авториз.) | Отзыв отклика по job_id (редирект на withdraw_application_atomic) | да | REDIR |
| `/unapply-selected` | POST | all (авториз.) | Массовый отзыв откликов через withdraw_application_atomic | да | REDIR |
| `/api/applications/<app_id>/withdraw` | POST | all (авториз.) | Отзыв отклика работником (автором) | да | JSON |
| `/my-applications` | GET | employer | Отображение откликов на задания работодателя (с пагинацией) | — | HTML |
| `/api/applications/<app_id>/accept` | POST | all (авториз.) |  | да | REDIR |
| `/api/applications/<app_id>/reject` | POST | all (авториз.) |  | да | REDIR |
| `/api/applications/<app_id>/reopen` | POST | all (авториз.) |  | да | REDIR |
| `/api/applications/batch` | POST | all (авториз.) | Массовая операция над откликами (принять / отклонить / повторно принять) | да | JSON |
| `/application/<app_id>/cancel` | POST | all (авториз.) | Отмена принятого работника | да | JSON |

## auth — аутентификация

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/login` | GET,POST | guest (публичный) |  | да | HTML |
| `/register` | GET,POST | guest (публичный) |  | да | HTML |
| `/logout` | POST | guest (публичный) |  | да | REDIR |
| `/password-reset/request` | GET,POST | guest (публичный) | Форма запроса сброса пароля: отправка ссылки с токеном на email | да | HTML |
| `/password-reset/confirm/<token>` | GET,POST | guest (публичный) | Форма нового пароля после перехода по ссылке из email | да | HTML |
| `/verify-email/<token>` | GET | guest (публичный) | Подтверждение email по токену из письма | — | REDIR |
| `/verify-email/resend` | GET,POST | guest (публичный) | Повторная отправка письма подтверждения email | да | HTML |

## blacklist — чёрный список

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/blacklist` | GET | all (авториз.) |  | — | HTML |
| `/blacklist/<user_id>` | POST | all (авториз.) |  | да | JSON |
| `/unblock/<user_id>` | POST | all (авториз.) |  | да | JSON |

## chat — чат и сообщения

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/chats` | GET | all (авториз.) | Список чатов пользователя: все принятые заявки, где он участник | — | HTML |
| `/chat/<application_id>` | GET | all (авториз.) | Чат по заявке (application_id) | — | HTML |
| `/chat/new/<worker_id>` | GET | employer | Поиск существующего чата с работником (по accepted-заявке) или редирект на список чатов | — | REDIR |
| `/api/send_message` | POST | all (авториз.) | Отправить сообщение в чат заявки | да | JSON |
| `/api/messages/<application_id>/poll` | GET | all (авториз.) | Polling-эндпоинт: вернуть сообщения новее указанного ID | — | JSON |
| `/api/delete-chats` | POST | all (авториз.) | Удаление одного или нескольких чатов (application_id). Доступно работодателю и труднику | да | JSON |

## core — системные (health/статика/редиректы)

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/metrics` | GET | guest (публичный) | Prometheus metrics endpoint (Задача 10-2) | — | REDIR |
| `/health` | GET | guest (публичный) | Проверка работоспособности приложения | — | JSON |
| `/ready` | GET | guest (публичный) | Readiness check: возвращает 503 если PostgREST или Redis недоступен | — | JSON |
| `/health/circuit-breaker` | GET | guest (публичный) | Детальная информация о состоянии Circuit Breaker | — | JSON |
| `/health/postgrest` | GET | guest (публичный) | Прямая проверка доступности PostgREST | — | JSON |
| `/uploads/avatars/<path:filename>` | GET | guest (публичный) | Аватары — публичные | — | FILE |
| `/uploads/verification-docs/<path:filename>` | GET | all (авториз.) | Документы верификации — только админ или владелец | — | FILE |
| `/sw.js` | GET | guest (публичный) | Service Worker для PWA (кроме TESTING) | — | REDIR |
| `/offline` | GET | guest (публичный) | Offline fallback page for PWA service worker | — | HTML |
| `/.well-known/assetlinks.json` | GET | guest (публичный) | Digital Asset Links for Trusted Web Activity (Google Play) | — | FILE |
| `/favicon.ico` | GET | guest (публичный) |  | — | REDIR |
| `/jobs` | GET | guest (публичный) |  | — | REDIR |
| `/search` | GET | guest (публичный) |  | — | REDIR |
| `/static/` | GET | guest (публичный) | Запрос /static/ без имени файла → 404 вместо 500 | — | REDIR |
| `/terms` | GET | guest (публичный) | Страница «Условия использования» (редактируется админом через site_pages) | — | REDIR |
| `/privacy` | GET | guest (публичный) | Страница «Политика конфиденциальности» (редактируется админом через site_pages) | — | REDIR |
| `/api/client-error` | POST | guest (публичный) | Приём отчётов об ошибках от frontend JavaScript | да (_csrf_token в JSON body) | JSON |

## employers — работодатели

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/employers` | GET | all (авториз.) | Список всех работодателей с пагинацией, поиском и фильтрацией | — | HTML |
| `/employers/<employer_id>` | GET | all (авториз.) | Профиль работодателя + его открытые задания | — | HTML |
| `/employers/<employer_id>/favorite` | POST | all (авториз.) | Toggle избранного работодателя (form-based) | да | REDIR |
| `/api/employers/favorites/add` | POST | all (авториз.) |  | да | JSON |
| `/api/employers/favorites/remove` | POST | all (авториз.) |  | да | JSON |
| `/api/employers/favorites/check` | POST | all (авториз.) |  | да | JSON |

## favorites — избранное

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/favorites` | GET | all (авториз.) |  | — | HTML |
| `/favorite/<target_id>` | POST | employer |  | да | REDIR |
| `/unfavorite/<target_id>` | POST | employer |  | да | REDIR |
| `/api/favorites/add` | POST | employer |  | да | JSON |
| `/api/favorites/remove` | POST | employer |  | да | JSON |
| `/api/favorites/check` | POST | employer |  | да | JSON |
| `/api/favorites/remove-selected` | POST | employer |  | да | JSON |

## jobs — задания (страницы и действия)

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/` | GET | guest (публичный) |  | — | HTML |
| `/workers` | GET | guest (публичный) |  | — | HTML |
| `/jobs/<job_id>` | GET | guest (публичный) | Детальная страница задания | — | HTML |
| `/pricing` | GET | guest (публичный) | Страница с тарифами для работодателей | — | HTML |
| `/job/new` | GET,POST | employer | Создание задания (единственный маршрут, заменяет /create-job) | да | HTML |
| `/my-jobs` | GET | employer |  | — | HTML |
| `/my-jobs/action` | POST | employer | Bulk-операции над заданиями (cancel/restore/delete/duplicate) | да | REDIR |
| `/repost-job/<job_id>` | POST | employer |  | да | JSON |
| `/cancel-job/<job_id>` | POST | employer |  | да | JSON |
| `/restore-job/<job_id>` | POST | employer |  | да | JSON |
| `/api/jobs/<job_id>/force-complete` | POST | employer | Принудительное завершение задания работодателем | да | JSON |
| `/delete-job/<job_id>` | POST | all (авториз.) |  | да | JSON |
| `/invitations` | GET | all (авториз.) | HTML-страница приглашений (использует унифицированный сервис) | — | HTML |
| `/api/invitations/reject-all` | POST | all (авториз.) | Отклонить все ожидающие приглашения текущего пользователя | да | JSON |
| `/jobs/<job_id>/edit` | GET,POST | employer |  | да | HTML+JSON |
| `/favorite-job/<job_id>` | POST | all (авториз.) |  | да | REDIR |
| `/unfavorite-job/<job_id>` | POST | all (авториз.) |  | да | REDIR |

## jobs_api — JSON API заданий/навыков/приглашений

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/api/skills` | GET | guest (публичный) | Получить список навыков (JSON) | — | REDIR |
| `/api/invite/<job_id>/<worker_id>` | POST | employer | Работодатель приглашает трудника на задание | да | JSON |
| `/api/invitations` | GET | all (авториз.) | JSON API: список приглашений (использует унифицированный сервис) | — | JSON |
| `/api/invitations/<invitation_id>/respond` | POST | worker | Трудник принимает или отклоняет приглашение | да | JSON |

## messenger_verify — верификация через MAX/Telegram (Phase 3A)

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/messenger/start/<platform>` | GET | all (авториз.) | Генерирует deep-link для подтверждения через мессенджер (AJAX) | — | JSON |
| `/messenger/diagnose` | GET | admin | Диагностика outbound-доступности API мессенджеров с прода (закрыт admin_required с 2026-08-16) | — | JSON |
| `/messenger/webhook/max` | POST | guest (публичный) | Принимает события от MAX бота (bot_started с payload = наш токен) | exempt (внешн.) | JSON |
| `/messenger/webhook/telegram` | POST | guest (публичный) | Принимает обновления от Telegram бота (/start <token>) | exempt (внешн.) | JSON |

## notifications — уведомления и push

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/api/ws/token` | GET | all (авториз.) | Выдать короткоживущий JWT для подключения к WebSocket-серверу | — | JSON |
| `/notifications` | GET | all (авториз.) |  | — | HTML |
| `/api/notifications/unread-count` | GET | all (авториз.) |  | — | JSON |
| `/api/notifications` | GET | all (авториз.) |  | — | JSON |
| `/api/notifications/read-all` | POST | all (авториз.) |  | да | JSON |
| `/api/notifications/<notification_id>/delete` | POST | all (авториз.) | Удалить одно уведомление | да | JSON |
| `/api/notifications/delete-all` | POST | all (авториз.) | Удалить все уведомления пользователя (кроме приглашений) | да | JSON |
| `/notification/<notification_id>/read` | POST | all (авториз.) |  | да | REDIR |
| `/notifications/settings` | GET | all (авториз.) | Страница настроек уведомлений | — | HTML |
| `/api/notifications/preferences` | GET | all (авториз.) | Получить настройки уведомлений пользователя | — | JSON |
| `/api/notifications/preferences` | POST | all (авториз.) | Сохранить одну настройку уведомления | да | JSON |
| `/push/vapid-public-key` | GET | guest (публичный) | Возвращает публичный VAPID-ключ для фронтенда | — | JSON |
| `/notifications/push/vapid-public-key` | GET | guest (публичный) |  | — | REDIR |
| `/push/subscription` | POST | all (авториз.) | Подписка на push-уведомления | да | JSON |
| `/push/subscription` | DELETE | all (авториз.) | Отписка от push-уведомлений | да | JSON |
| `/push/subscription` | GET | all (авториз.) | Получение списка активных push-подписок пользователя | — | JSON |

## profile — профиль

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/profile` | GET | all (авториз.) |  | — | HTML |
| `/profile/update` | POST | all (авториз.) |  | да | REDIR |
| `/profile/delete-photo` | POST | all (авториз.) |  | да | REDIR |
| `/profile/delete-account` | POST | all (авториз.) |  | да | REDIR |
| `/profile/export-data` | GET | all (авториз.) | 152-ФЗ ст.14/15: право субъекта на доступ/копию своих персональных данных | — | REDIR |
| `/profile/change-password` | POST | all (авториз.) |  | да | REDIR |
| `/verify-employer` | GET,POST | all (авториз.) |  | да | HTML |
| `/profile/<user_id>` | GET | guest (публичный) |  | — | HTML |
| `/profile/<user_id>/report` | POST | all (авториз.) | Подать жалобу на пользователя (антифрод: основа авто-заморозки Phase 3) | да | JSON |

## ratings — оценки и отзывы

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/api/ratings/<job_id>` | GET | guest (публичный) | Получить все оценки для задания | — | JSON |
| `/api/ratings/user/<user_id>` | GET | guest (публичный) | Получить агрегированный рейтинг пользователя | — | JSON |
| `/api/ratings` | POST | all (авториз.) | Создать или обновить оценку (один пользователь — одна оценка на задание) | да | JSON |
| `/api/ratings/completed-jobs/<target_user_id>` | GET | all (авториз.) | Вернуть список завершённых заданий, в которых участвовали оба пользователя | — | JSON |
| `/api/ratings/user/<user_id>/details` | GET | guest (публичный) | Получить все детальные оценки пользователя с отзывами | — | JSON |
| `/ratings/user/<user_id>` | GET | guest (публичный) | Страница со списком всех оценок пользователя | — | HTML |
| `/jobs/<job_id>/rate-workers` | GET | employer | Страница оценки всех принятых работников задания | — | HTML |

## seo — robots/sitemap

| URL | Method | Role | Назначение | CSRF | Ответ |
|-----|--------|------|------------|------|-------|
| `/robots.txt` | GET | guest (публичный) |  | — | REDIR |
| `/sitemap.xml` | GET | guest (публичный) |  | — | HTML |

---

## Сводка

- Всего эндпоинтов: **146**
- По ролям: admin-сессия 27, admin по X-Admin-Token 2, employer 18, worker 2, все авторизованные 56, публичные 41
- По типу ответа: JSON 70, HTML-страницы 32, прочие (редиректы/файлы) 44
- Мутирующих (CSRF-проверяемых): 83, из них exempt: 2 (+client-error с токеном в body)
