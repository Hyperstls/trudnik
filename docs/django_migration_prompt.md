# Спека: перенос Trudnik на Django (улучшенный промт)

> Это улучшенная версия исходного промта:
> «Глубоко проанализируй приложение trudnik и перенеси его на Django с удобной админкой.
> Установи все необходимые MCP, навыки и плагины для качественной разработки, тестирования
> и деплоя на Amvera. Обрати внимание на Amvera MCP и всё, что можешь делать с Amvera».
>
> Улучшение = замена расплывчатой цели на исполнимую спецификацию: зафиксированные факты о системе,
> архитектурные решения с обоснованием, пофазный объём, критерии приёмки и команды верификации.

---

## 0. Краткая промт-версия (для нового чата)

> Ветка `main-jango`. Портируй Trudnik на Django 5.2 LTS по спецификации
> `docs/django_migration_prompt.md` (прочитай её целиком, включая §2 «Критерии приёмки»
> и §6 «Верификация»). Django-проект живёт в `djadmin/`, работает поверх СУЩЕСТВУЮЩЕЙ
> схемы PostgreSQL (unmanaged-модели, SQL-миграции остаются источником истины схемы),
> бизнес-атомика вызывается через существующие SECURITY DEFINER RPC. Фаза 1 = полная
> админка + публичные read-only страницы + деплой-конфиг Amvera. Схему БД и карту RPC
> см. в §1. Не выдумывай факты — сверяйся с БД (`docker exec trudnik-db psql ...`)
> и кодом Flask.

---

## 1. Зафиксированные факты (сверено с живой БД и кодом 2026-10-29)

### 1.1. БД и роли
- Прод: Amvera CNPG `trudnik-db` (PostgreSQL 17 + PostGIS, регион **msk1**),
  хост внутри Амстеры: `amvera-hyperstls-cnpg-trudnik-db-rw:5432`, БД `trudnik`.
  Локально: docker-compose `trudnik-db` (postgis 15-3.4, порт 5433, юзер/бд `trudnik`).
- **Таблица пользователей = `profiles`** (email уникален по `lower(email)`, `password_hash`
  bcrypt `$2b$`/`$2a$` 12 раундов — совместим с `crypt()` pgcrypto и с Django `BCryptPasswordHasher`).
  `role` ∈ {worker, employer, admin} — «ориентация», НЕ барьер доступа (см. AGENTS.md).
- 30 бизнес-таблиц. Особенности: составные PK `user_skills(user_id, skill_id)` и
  `job_skills(job_id, skill_id)`; строковый PK `site_pages.slug`; `messages.id` — IDENTITY;
  jsonb-колонки (`notification_prefs`, `data`, `old_data/new_data`, `receipt_json`);
  массив `jobs.photo_urls` (легаси, актуальные фото в `job_photos`).
- Триггеры в БД: `updated_at` (profiles/jobs/applications/employer_subscriptions),
  tsvector-триггеры поиска, `recompute_profile_rating()` на ratings. **Пересчёт рейтинга
  в коде НЕ дублировать — его делает триггер.**
- Роли: `anon` / `authenticated` (RLS по GUC `request.jwt.claims`) / `service_role` (BYPASSRLS) /
  `trudnikapp` (NOINHERIT-обёртка) / `trudnik` (superuser, владелец).
- SQL-миграции `migrations/NNN_*.sql` — источник истины схемы; применяются вручную
  `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py` (rule 04).

### 1.2. Бизнес-атомика = RPC (SECURITY DEFINER)
`register_user`, `login_user`, `change_password`, `apply_job_atomic`, `accept_application`,
`reject_application`, `withdraw_application_atomic`, `cancel_worker_atomic`,
`update_job_status_atomic`, `cancel_job_atomic`, `restore_job_atomic`, `force_complete_job`,
`delete_job_cascade`, `delete_user_cascade`, `delete_skill_cascade`, `rate_user_atomic`,
`suspend_user`, `unsuspend_user`, `resolve_user_atomic`, `file_report`, `review_complaint`,
`users_exceeding_reports`, `expire_unfilled_jobs`, `verify_via_messenger`,
`accept_invitation_atomic`, `get_job_stats`, `get_admin_dashboard_stats`, `nearby_jobs`.

### 1.3. RLS-правила, которые обязан воспроизводить прямой доступ (Django без JWT-RLS)
- `jobs` публично виден только со статусом `open | completed | cancelled`.
- `profiles`: скрыты admin-профили; каталог трудников — только `worker_visibility=true`.
- Владение: `job.employer_id`, `application.worker_id`/владелец job, участники application в чатах.
- Мутирующие действия — только RPC (см. 1.2), не прямые UPDATE мимо атомарности.

### 1.4. Существующая админка (то, что воспроизводит Django Admin)
users (поиск/фильтры/смена роли с запретом себе и другим админам, suspend/unsuspend,
delete через `delete_user_cascade`, bulk ≤ 20 без админов, verification approve/reject,
email_verified), jobs (фильтр статуса, смена статуса с запретом completed→open при ratings,
delete через `delete_job_cascade`, bulk ≤ 50), skills/religions (CRUD + sort_order),
complaints (очередь + `review_complaint` block|dismiss), site_pages (редактор /terms /privacy),
audit_log на каждое действие, дашборд (`get_admin_dashboard_stats`, `get_job_stats`).

### 1.5. Amvera
- MCP: `https://openmcp.msk1.amvera.ru/mcp`, Bearer из ЛК (подключён в ZCode user-config,
  работает с новой сессии). Инструменты: listProjects/getProject/createProject/deleteProject,
  listTariffs/listConfigurations/getAmveraConfigTemplate, uploadFiles/downloadFiles/listFiles/deleteFiles,
  getCommitHistory/getBuildLogs/getRunLogs/getEventLogs, rebuildProject/restartProject/stopBuild/
  scaleProject/freezeProject, listEnvVars/createEnvVars/updateEnvVar/deleteEnvVar,
  listDomains/createDomain/deleteDomain. CLI-креды — в локальном `.env` (AMVERA_USER/PASSWORD/CLI).
- Манифест: `amvera.yaml` (toolchain docker, persistenceMount `/data`, containerPort 8000).
  Всё runtime-изменяемое — только под `/data`. Healthcheck: внешний `/health`, внутренний `/ready`.
- Новый сервис обязан жить в регионе msk1 (внутренний DNS БД работает только внутри региона).

---

## 2. Цель фазы 1 и критерии приёмки

**Цель:** Django-приложение `djadmin/` — компаньон поверх той же БД: полноценная админка
(замена 6 admin-blueprint'ов Flask) + публичные read-only страницы (лента заданий, карточка
задания, каталог трудников, публичный профиль) + health. Пишущая пользовательская логика
(отклики/чат/push/celery/WS) остаётся на Flask до фаз 2–3.

**Критерии приёмки (все обязательны):**
1. `python djadmin/manage.py check` — 0 ошибок; `makemigrations --check --dry-run` — без дрейфа.
2. Тесты: `python scripts/dj_test_clone.py && python djadmin/manage.py test core --keepdb -v 1`
   (клон dev-БД как тестовой) — все зелёные. Покрыто: маппинг моделей на колонки БД,
   auth-бридж (bcrypt + suspended/email_verified), RLS-видимость лент, вызов RPC,
   доступ к админке (superuser да / не-staff нет), публичные страницы.
3. `python scripts/pre_deploy_check.py` — 0 проблем (Flask-часть репо не затронута).
4. Flask-приложение не изменилось ни на строчку кода; `git diff main -- app/ templates/ static/`
   на ветке пуст (кроме нового `djadmin/`, `Dockerfile.djadmin`, конфигов и доков).
5. В админке доступны все сущности из §1.4 с бизнес-правилами (RPC-удаления, лимиты bulk,
   запреты смены роли/статуса) и записью audit_log.
6. `Dockerfile.djadmin` собирается, контейнер поднимается, `/health` отвечает 200
   (локальная проверка против docker-compose БД).
7. Никаких секретов в коммитах (detect-secrets pre-commit).

## 3. Не-цели фазы 1 (осознанно отложено)
- Перенос пишущих пользовательских флоу: отклики, приглашения, чат (WS + Redis pubsub),
  уведомления/push/email-рассылка, капча-регистрация, password reset. → фаза 2.
- Выключение Flask-приложения, перенос Celery-задач. → фаза 3.
- Django-миграции схемы: **запрещены в фазе 1**; схема управляется только `migrations/NNN_*.sql`.

---

## 4. Архитектурные решения (ADR)

- **ADR-1. Unmanaged-модели поверх существующей схемы.** `managed=False` у всех бизнес-моделей;
  источником истины схемы остаются SQL-миграции. Системные таблицы Django
  (`django_*`, `auth_group*`, `auth_permission`) создаются `manage.py migrate` в схеме `public`
  (инертны, гранты только роли Django; PostgREST-роли их не видят).
- **ADR-2. Прямое подключение к PostgreSQL** (psycopg2), а не через PostgREST. Бизнес-атомика —
  вызовами существующих RPC (`SELECT fn(...)`), наследуя их SECURITY DEFINER-инварианты.
  Мутации мимо RPC — только там, где Flask сам делает прямой PATCH (verification, email_verified, role).
- **ADR-3. Отдельная роль БД `trudnik_dj`** (миграция `148_django_admin_role.sql`):
  LOGIN + BYPASSRLS + гранты DML/EXECUTE. Админка обязана видеть все строки; компенсация —
  п. ADR-4. На проде создаётся через `apply_migrations.py` с DATABASE_ADMIN_URL.
- **ADR-4. RLS-эмуляция в ORM:** менеджеры/QuerySet-методы `visible_public()` у Job и Profile
  воспроизводят правила §1.3 и применяются во ВСЕХ публичных view. В админке — полный доступ.
- **ADR-5. Auth-бридж:** кастомный `AUTH_USER_MODEL=core.Profile` (unmanaged):
  `USERNAME_FIELD=email`, `password` ← `password_hash` (Django BCrypt-хэшер первым),
  `is_active = NOT suspended`, `is_staff/is_superuser = (role=='admin')` (свойства),
  `last_login` — свойство (сигнал `update_last_login` отключён, колонки в БД нет).
  Свой бэкенд: bcrypt-проверка + отказ при `suspended`/не-`email_verified`; лок-аут 5 неудач
  → экспоненциальный бэкоф (в памяти процесса; админ-масштаб), опциональный IP-allowlist
  `DJANGO_ADMIN_ALLOWED_IPS`.
- **ADR-6. Размещение кода:** `djadmin/` (config + core-приложение), точка входа
  `djadmin/manage.py`, gunicorn `config.wsgi`. Образ `Dockerfile.djadmin`; `amvera.yaml`
  на ветке указывает на него (main-ветка продолжает деплоить Flask-образ без изменений).
- **ADR-7. Статика/шаблоны:** свои лаконичные шаблоны в `djadmin/core/templates/core/`
  с классами уже скомпилированного `static/css/tailwind.min.css` (без пересборки Tailwind,
  freshness-гейт Flask не затрагивается — он сканирует только корневые `templates/` и `static/js/`).
  `/uploads/…` в публичных страницах абсолютизируется через `WORKER_SITE_URL` (файлы лежат
  в volume сервиса Flask).
- **ADR-8. Тесты против клона dev-БД** (`scripts/dj_test_clone.py`: `CREATE DATABASE trudnik_test
  TEMPLATE trudnik`), `manage.py test --keepdb`: в клоне живут триггеры и RPC — тестируется
  реальное поведение, включая SECURITY DEFINER. CI (`django.yml`) без БД: `manage.py check`
  + smoke импортов; полные DB-тесты — локально/pre-deploy.

## 5. Объём фазы 1 (чек-лист реализации)

- [x] `migrations/148_django_admin_role.sql` — роль `trudnik_dj` (идемпотентно).
- [x] `djadmin/`: settings (env: DATABASE_URL/PG*, SECRET_KEY, DJANGO_ALLOWED_HOSTS,
      CSRF_TRUSTED_ORIGINS, WORKER_SITE_URL), urls, wsgi.
- [x] `core/models.py` — все бизнес-таблицы (unmanaged, TextChoices, JSONField, ArrayField,
      составные PK через unique_together + fk-поля), включая `user_skills`/`job_skills`
      как through-модели.
- [x] `core/managers.py` — RLS-видимость (`Job.objects.public()`, `Profile.objects.public_workers()`).
- [x] `core/auth_backend.py` + сигнал-off + лок-аут + allowlist-мидлварь.
- [x] `core/rpc.py` — вызов RPC и чтение jsonb-ответов; `core/audit.py` — примесь аудита.
- [x] `core/admin/` — Profile (действия: role/suspend/unsuspend/delete-RPC/bulk≤20/
      verify approve-reject/email_verified, инлайн employer_details), Job (status-guard,
      delete-RPC, bulk≤50, инлайн job_photos), UserReport (review_complaint),
      Skill/Religion (CRUD + delete-RPC + sort_order), SitePage, Notification(+outbox,
      retry-action), Message (RO), Rating, Invitation, Favorites/Blacklist, JobPayment,
      Receipt, EmailLog, PushSubscription, Monetization/Tariff settings, AuditLog (RO),
      дашборд-вью `get_admin_dashboard_stats` + `get_job_stats`.
- [x] Редактор навыков пользователя: custom admin-view (DELETE+INSERT в транзакции).
- [x] Публичные view: `/health`, `/` (redirect /jobs), `/jobs` (+фильтры q/city/payment/status),
      `/jobs/<id>`, `/workers` (+q), `/workers/<id>` — только RLS-видимые данные.
- [x] Тесты (`core/tests/`): schema-mapping, auth, visibility, rpc, admin, public views.
- [x] `scripts/dj_test_clone.py`, `scripts/dj_deploy.sh` (CLI/MCP-деплой на новый slug
      `trudnik-dj`, регион msk1), `.github/workflows/django.yml`.
- [x] Доки: `djadmin/README.md` (локальный запуск/тесты/деплой), обновление этой спеки.

## 6. Верификация (команды)

```bash
# локально (db из docker-compose должен быть поднят)
.venv/Scripts/python.exe -m pip install -r djadmin/requirements.txt
.venv/Scripts/python.exe djadmin/manage.py check
.venv/Scripts/python.exe scripts/dj_test_clone.py
.venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1
.venv/Scripts/python.exe scripts/pre_deploy_check.py          # Flask-часть не сломана
# сборка образа
docker build -f Dockerfile.djadmin -t trudnik-dj:local .
```

## 7. Деплой (Amvera, msk1)
1. (однократно) Создать проект `trudnik-dj` (compute, Docker): MCP `createProject` +
   `createEnvVars` (DATABASE_URL с ролью trudnik_dj, SECRET_KEY, DJANGO_ALLOWED_HOSTS,
   CSRF_TRUSTED_ORIGINS, WORKER_SITE_URL) или веб-ЛК.
2. Применить миграцию 148 на прод-БД (DATABASE_ADMIN_URL): `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py`.
3. `bash scripts/dj_deploy.sh` — push ветки main-jango в проект + rebuild + логи.
4. Первый запуск: `python djadmin/manage.py migrate` (системные таблицы) + `collectstatic`
   (в образе/entrypoint автоматически).
5. Проверка: `https://trudnik-dj-hyperstls.amvera.io/health` → 200, `/admin/` → логин
   профилем с role=admin.

## 8. Дорога дальше (фазы 2–3)

- **Фаза 2а (выполнена 2026-10-29, тем же днём):** вход/выход на публичном сайте
  (тот же auth-бридж: lockout, fail-closed), создание/редактирование заданий
  (+ job_skills raw-SQL), «Мои задания» с действиями cancel/restore/force-complete/
  delete через RPC, отклики apply/unapply/accept/reject/reopen/cancel/withdraw — все
  через атомарные RPC (user_id только из сессии, IDOR невозможен), страницы
  «Мои отклики»/«Отклики на задание» (владелец|admin), избранное заданий.
  Тесты: test_flows.py (20 шт), всего 56.
- **Фаза 2б (выполнена 2026-10-30, после код-ревью):** регистрация (honeypot,
  consent 152-ФЗ, intent→роль, RPC register_user, письмо-верификация),
  /verify-email/<token> (+resend, cooldown 120с), /password-reset/request
  (cooldown 300с, единый ответ) и /confirm/<token> (B11: гашение токенов).
  Контрактная проверка вскрыла баг Flask (reset звал несуществующую перегрузку
  change_password(p_email, p_new_password)) — миграция 149 добавляет её.
  Токены itsdangerous кросс-совместимы с Flask в обе стороны. Тестов всего 87.
- **Фаза 2в (выполнена 2026-10-30):** /profile (анкета + навыки raw-SQL +
  смена пароля RPC change_password(uuid,old,new) c password_changed_at-штампом,
  паритет B10), избранное людей + чёрный список (toggle/страницы), приглашения
  (инвайт с карточки трудника: только своё OPEN-задание и видимый трудник;
  дубль через savepoint; принятие RPC accept_invitation_atomic; decline;
  входящие/исходящие). Тестов всего 103.
- **Фаза 2г (выполнена 2026-10-30):** оценки после завершённого задания в обе
  стороны (работодатель→принятый работник, работник→работодатель; upsert
  (rater,job) по миграции 145, пересчёт профиля — триггером БД; контрактная
  сверка показала: RPC rate_user_atomic строже — только трудник→трудник, общий
  случай Flask реализует проверками+upsert — зеркалировано) и чат: комнаты по
  заявке (доступ = участие, паритет chat_access), отправка с идемпотентностью
  client_message_id (savepoint), JSON-poll ?after=<id>, список чатов. Тестов 115.
- **Фаза 2д (выполнена 2026-10-30):** web-уведомления — /notifications (только
  свои, пагинация), отметить прочитанным/все, удалить, JSON
  /api/notifications/unread-count, бейдж в навигации (context processor).
  Вставок djadmin не делает — уведомления создаёт Flask-конвейер (RLS:
  INSERT только service_role). Тестов 123.
- Фаза 2е (осталось): мессенджер-верификация MAX/Telegram — ТРЕБУЕТ решений:
  кэш/Redis для одноразовых токенов (Django CACHES: RedisCache при REDIS_URL
  либо DB-cache), webhook-эндпоинт без CSRF с секретом MAX_WEBHOOK_SECRET,
  RPC verify_via_messenger; фаза 3 — WS/push/Celery/выключение Flask.
- MCP-окружение ZCode (2026-10-30): amvera (msk1), redis (local docker),
  postgres (read-only dev-БД), context7 (доки). Осознанно НЕ ставились:
  filesystem/playwright/git/github/sequentialthinking — перекрываются
  нативными инструментами, плагином browser-use, Bash+gh CLI.
- Фаза 3: WebSocket (channels), PWA/push, перенос Celery-задач, выключение Flask,
  RLS per-request (`SET LOCAL request.jwt.claims` в транзакции запроса — строгий
  паритет с PostgREST).
