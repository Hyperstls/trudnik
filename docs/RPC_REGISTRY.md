# Реестр RPC-функций проекта «Трудник»

Дата обновления: 2026-08-15 (ревизия: удалены неподтверждённые записи)  
Источник: все миграции 067–139  
Всего функций: 30 RPC + 4 trigger-функции (уникальных по сигнатуре)

---

## Группировка по категориям

### 🔐 Auth (аутентификация)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `login_user` | `p_email text, p_password text` | `TABLE(user_id uuid, role text, full_name text, email_verified boolean)` | Проверка пароля через pgcrypto, возврат пользователя | Да | 067, 075, 082, 130 | Да (auth_service.py fallback) |
| `register_user` | `p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'` | `uuid` | Регистрация пользователя, bcrypt 12 rounds | Да | 067, 075, 080 | Да (auth.py) |
| `change_password` | `p_user_id uuid, p_old_password text, p_new_password text` | `boolean` | Смена пароля с проверкой старого | Да | 067, 075, 130 | Да (profile.py) |
| `verify_via_messenger` | `p_user_id uuid, p_provider text, p_messenger_uid text DEFAULT NULL` | `boolean` | Подтверждение профиля через мессенджер (Phase 3A) | Да | 137 | Да (messenger_verify.py) |

### 💼 Jobs (задания)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `apply_job_atomic` | `p_job_id uuid, p_worker_id uuid` | `jsonb` | Атомарный отклик на задание с проверками | Да | 067, 069, 075, 088, 091, 099 | Да (jobs.py, jobs_api.py) |
| `accept_application` | `p_job_id uuid, p_app_id uuid` | `jsonb` | Принятие отклика работодателем | Да | 067, 069, 075, 077, 091, 099, 120 | Да (applications.py) |
| `reject_application` | `p_job_id uuid, p_app_id uuid` | `jsonb` | Отклонение отклика работодателем | Да | 067, 069, 075, 077, 091, 099, 120 | Да (applications.py) |
| `cancel_job_atomic` | `p_job_id uuid, p_user_id uuid` | `jsonb` | Отмена задания работодателем | Да | 067, 091 | Да (jobs.py) |
| `force_complete_job` | `p_job_id uuid, p_user_id uuid` | `jsonb` | Принудительное завершение набора | Да | 067, 075, 091 | Да (jobs.py) |
| `restore_job_atomic` | `p_job_id uuid, p_user_id uuid` | `jsonb` | Восстановление отменённого задания | Да | 075, 077, 085, 099 | Да (jobs.py) |
| `update_job_status_atomic` | `p_job_id uuid, p_new_status text, p_user_id uuid` | `jsonb` | Изменение статуса задания | Да | 067 | Нет |
| `delete_job_cascade` | `p_job_id uuid` | `jsonb` | Каскадное удаление задания и связанных данных | Да | 067, 069, 075, 077, 086, 091, 099, 128 | Да (admin_jobs.py, jobs.py) |
| `nearby_jobs` | `p_lat double precision, p_lng double precision, p_radius_meters double precision DEFAULT 5000` | `TABLE(...)` | Поиск заданий по геолокации (PostGIS) | Да | 067, 075, 127, 129 | Да (jobs.py, jobs_api.py) |
| `get_job_stats` | — | `JSONB` | Статистика по заданиям | Да | 067 | Да (admin_dashboard.py) |
| `expire_unfilled_jobs` | — | `integer` | Авто-истечение просроченных заданий без откликов | Да | 136 | Да (maintenance_tasks.py) |

> ⚠️ **ОБНАРУЖЕННАЯ АНОМАЛИЯ**: `app/services/job_service.py:604` вызывает `postgrest_rpc('create_job', payload)` и `job_service.py:646` — `postgrest_rpc('update_job', payload)`, однако **НИ ОДНА миграция 067–139 не содержит `CREATE FUNCTION create_job/update_job`** (проверено grep по всем файлам миграций). Если эти RPC не были созданы вручную вне миграций, вызовы вернут 404 PGRST202 в проде. Требует проверки схемы БД (`\df public.create_job`) и, при отсутствии, — создания миграции или перехода на прямой POST/PATCH /jobs.

### 📝 Applications (отклики)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `withdraw_application_atomic` | `p_application_id uuid, p_user_id uuid` | `jsonb` | Отзыв отклика работником (с 12-ч окном) | Да | 067, 084 | Да (applications.py) |
| `cancel_worker_atomic` | `p_application_id uuid, p_user_id uuid` | `jsonb` | Отмена принятого работника работодателем | Да | 067, 069, 075 | Да (applications.py) |
| `accept_invitation_atomic` | `p_invitation_id uuid, p_user_id uuid` | `jsonb` | Принятие приглашения работником | Да | 067, 075, 077 | Да (invitations.py) |

### ⭐ Ratings (оценки)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `rate_user_atomic` | `p_job_id uuid, p_rater_user_id uuid, p_rated_user_id uuid, p_rating int, p_comment text DEFAULT '', p_rating_type text DEFAULT 'worker', p_target_type text DEFAULT 'worker'` | `jsonb` | Сохранение оценки с пересчётом рейтинга профиля | Да | 067, 069, 075 | Да (ratings.py) |
| `recompute_profile_rating` | — (trigger function) | `TRIGGER` | Триггер авто-пересчёта рейтинга при изменении ratings | Да | 101 | Нет (авто через триггер) |

### 🔔 Notifications (уведомления)

*В этой категории НЕТ RPC-функций. `drain_notification_outbox` — это Celery-задача (app/tasks/notification_tasks.py), а не PL/pgSQL-функция: она читает таблицу notification_outbox через PostgREST и вызывает notification_service.create().*

### 👤 Users/Profiles (пользователи)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `delete_user_cascade` | `p_user_id uuid` | `jsonb` | Каскадное удаление пользователя и всех данных | Да | 067, 069, 075, 077, 091, 092, 099, 131 | Да (admin_users.py, profile.py) |
| `resolve_user_atomic` | `p_user_id uuid` | `jsonb` | Получение публичных данных пользователя | Да | 067 | Нет |
| `file_report` | `p_reported uuid, p_reason text DEFAULT ''` | `jsonb` | Подача жалобы на пользователя (Phase 3B) | Да | 135 | Да (profile.py) |
| `review_complaint` | `p_report_id uuid, p_action text, p_admin_id uuid DEFAULT NULL` | `jsonb` | Модерация жалобы админом (block/dismiss) | Да | 135 | Да (admin_users.py) |
| `users_exceeding_reports` | `p_threshold int DEFAULT 3, p_hours int DEFAULT 24` | `TABLE(reported_id uuid, report_count bigint)` | Кандидаты на заморозку (≥ порога жалоб) | Да | 135 | Да (maintenance_tasks.py) |
| `suspend_user` | `p_user_id uuid, p_reason text` | `boolean` | Заморозка пользователя | Да | 135 | Да (maintenance_tasks.py) |
| `unsuspend_user` | `p_user_id uuid` | `boolean` | Разморозка пользователя | Да | 135 | Да (admin_users.py) |

### 🛠 Admin/Internal (админ/системные)

| Функция | Параметры | Возврат | Назначение | SECURITY DEFINER | Миграция | Вызывается в коде |
|---------|-----------|---------|------------|------------------|----------|-------------------|
| `get_admin_dashboard_stats` | — | `JSON` | Статистика для админ-дашборда (1 запрос вместо 9) | Да (STABLE) | 090 | Да (admin_dashboard.py) |
| `exec_sql` | `sql_query text` | `JSONB` | Выполнение произвольного SQL (только service_role) | Да | 067, 078 | Нет (CLI only) |
| `delete_skill_cascade` | `p_skill_id uuid` | `jsonb` | Удаление навыка с очисткой связей | Да | 075 | Да (admin_dictionaries.py) |
| `pgrst_pre_request` | — | `void` | Pre-request хук для materialize JWT claims (PostgREST) | Да | 124 | Нет (авто PostgREST) |
| `jobs_geom_update` | — (trigger function) | `TRIGGER` | Автообновление geom из lat/lng | Да | 075, 127 | Нет (авто через триггер) |
| `profiles_search_update` | — (trigger function) | `TRIGGER` | Обновление search_vector для profiles | Да | 067, 126 | Нет (авто через триггер) |
| `update_updated_at_column` | — (trigger function) | `TRIGGER` | Автообновление updated_at | Нет | 093, 138, 139 | Нет (авто через триггер) |

---

## DEPRECATED / Удалённые функции

| Функция | Статус | Причина |
|---------|--------|---------|
| `handle_new_user` | DROPPED (067) | Устарел, заменён на register_user |
| `execute_sql` | DROPPED (067, 078) | Устарел, заменён на exec_sql |
| `apply_job_atomic` (старая сигнатура) | REPLACED | Обновлена в 088 (добавлена expires_at) |
| `accept_application` (старая сигнатура) | REPLACED | Исправлена в 069, 075, 077, 099, 120 |
| `reject_application` (старая сигнатура) | REPLACED | Исправлена в 069, 075, 077, 099, 120 |
| `delete_job_cascade` (старая) | REPLACED | Исправлена в 069, 075, 077, 086, 099, 128 |
| `delete_user_cascade` (старая) | REPLACED | Исправлена в 069, 075, 077, 091, 092, 099, 131 |
| `nearby_jobs` (старая) | REPLACED | Исправлена в 075, 127, 129 |
| `restore_job_atomic` (старая) | REPLACED | Исправлена в 075, 077, 085, 099 |
| `cancel_worker_atomic` (старая) | REPLACED | Исправлена в 069, 075 |
| `rate_user_atomic` (старая) | REPLACED | Исправлена в 069, 075 |
| `login_user` (старая) | REPLACED | Исправлена в 075, 082, 130 |
| `register_user` (старая) | REPLACED | Исправлена в 075, 080 |
| `change_password` (старая) | REPLACED | Исправлена в 075, 130 |

---

## Выводы по grep проверке

```bash
# Всего CREATE FUNCTION в миграциях 067-139:
grep -c "CREATE.*FUNCTION" migrations/*.sql
# Результат: 58 (включая переопределения и trigger-функции)

# Уникальных RPC-функций в реестре: 30 (плюс 4 trigger-функции)
# Trigger-функций: 4 (jobs_geom_update, profiles_search_update, recompute_profile_rating, update_updated_at_column)
# Удалённых (DROP FUNCTION): 12 уникальных имен
```

---

## Примечания

1. **SECURITY DEFINER** — все бизнес-RPC имеют этот флаг для обхода RLS
2. **search_path** — большинство используют `SET search_path = ''` или `pg_catalog, public` (для PostGIS/pgcrypto)
3. **GRANT** — все функции имеют `REVOKE ... FROM PUBLIC; GRANT ... TO authenticated, service_role` (или anon для auth)
4. **PostgREST schema cache** — новые RPC невидимы до `NOTIFY pgrst, 'reload schema'` (self-heal делает это каждые 120с)
5. **Вызов в коде** — проверено через `grep -r "postgrest_rpc" app/ --include="*.py"`