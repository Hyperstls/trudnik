# Migration ledger — P1-13 / DB-default P1-10

**Дата:** 2026-11-09
**Статус:** dev и production — **82/82** (150–167); миграция 167 применена на проде
2026-11-09 17:13 MSK (`files=82 applied=82 pending=0`), флаг `MIGRATIONS_ENABLED` возвращён в `false`; миграция 166 применена на проде
2026-11-09 14:25 MSK (`files=81 applied=81 pending=0`), флаг `MIGRATIONS_ENABLED` возвращён в `false`; миграция 165 применена на проде
2026-11-09 10:49 MSK (run-лог: files=80, applied=80, pending=0), флаг `MIGRATIONS_ENABLED`
возвращён в `false`; на момент 165 `/privacy` отдавала «Редакция … (версия 1.4)»; прод RUNNING, `/health` 200,
`/privacy`, `/terms`, `/safety` — 200. Флаги `MIGRATIONS_ENABLED` и
`MIGRATIONS_RECONCILE` на проде — **false**.

## Журнал 159–167 (2026-11-06…09)

| # | Файл | Дата применения | Что |
|---|---|---|---|
| 159 | `159_two_factor.sql` | 2026-11-06 | 2FA + метаданные сессий |
| 160 | `160_announcements.sql` | 2026-11-06 | Объявления /info |
| 161 | `161_application_responded_at.sql` | 2026-11-06 | Время ответа работодателя |
| 162 | `162_rating_appeals.sql` | 2026-11-06 | Апелляции на отзывы |
| 163 | `163_error_events.sql` | 2026-11-07 | Внутренний error tracking |
| 164 | `164_drop_religion_columns.sql` | 2026-11-08 18:25 MSK | DROP religion_id/preferred_religion |
| 165 | `165_privacy_policy_v14.sql` | dev 2026-11-09 10:37 MSK; прод — 10:49 MSK | `site_pages.privacy` → политика v1.4 (Web Push отключён); INSERT если нет, UPDATE только v1.2/v1.3 |
| 166 | `166_announcement_sort_order.sql` | dev 2026-11-09 10:58 UTC; прод 14:25 MSK | `announcements.sort_order` — ручной порядок объявлений /info (админка: закрепить/активно/порядок) |
| 167 | `167_privacy_policy_v15.sql` | dev 16:49 MSK; прод 17:13 MSK | `site_pages.privacy` → политика v1.5: MAX только верификация, уведомления email/in-app |

165 (dev): `apply_migrations.py` → «Миграция 165_privacy_policy_v14.sql успешно применена»,
ledger 80/80; `site_pages.privacy` содержит «версия 1.4»; повторный прогон идемпотентен
(UPDATE 0, content/updated_at не меняются). SHA256 165 —
`80bd856aaa5bd82ec1b7454d2db3181430e68da9c6fa9b746809007ce493c0f3`
(prod, LF; локальный CRLF-файл даёт `f01f5752…`, содержимое идентично).
Прод-процедура 165: временно `MIGRATIONS_ENABLED=true` (env id 76937) → redeploy → в run-логе
NOTICE `165_privacy_policy_v14: privacy pages at v1.4 = 1` → вернуть флаг `false` → проверить
`/privacy` (на момент 165 страница из БД отдавала v1.4).
166 (LF, prod): `188c199003138186921f503d127dbff43e09f6ee5f5a3e4a97716545d9b412c2`;
dev-файл (CRLF) — `47f223d60727d121dc507855f31a426e06df0a99ce2ab6aac788fa7777ab5616`.
167 (LF, prod): `eeaf8719925d842dbc9df14fba6fae991545b4beb1254aeb8469e96b1435fd39`;
dev-файл (CRLF) — `d0b9616c5eb2b42dbf80b88ecd38d1214d9309dc18b3922ae523bfa6ce0bc5d1`.

Источник записи 159–164: run-логи Amvera (метки контейнера — UTC; для 164 `15:25:22Z` = 18:25 MSK) (`apply_migrations.py` → «Миграция … успешно применена»,
`check_migrations.py` → `files=79, applied=79, pending=0`, RESULT OK; SHA256 164 —
`31a5da05e31aaea4e9ab39621cf71fc963bf043e80cee72c5fef1b799c015759`). Прод-миграции
применяются только при `MIGRATIONS_ENABLED=true` на старте контейнера; после применения флаг
возвращён в `false`.

### Процессный дефект 164 (признан)

Необратимый `DROP COLUMN` (спецкатегория ПДн, 152-ФЗ ст.10) применён к проду **без
предварительного read-only замера прод-данных**: проверка «0 non-null» делалась только на dev,
прод обоснован тезисом «тестовый режим без реальных пользователей». Если в проде были
legacy-значения, они утрачены безвозвратно. Правило на будущее: необратимые миграции
применяются после явного замера целевой БД (count/выборка через админ-доступ), результат
замера фиксируется в этом журнале до включения `MIGRATIONS_ENABLED`.

## Было

- `_migrations`: 37 записей, максимум `122_fix_outbox_grants.sql`.
- В БД уже были объекты поздних миграций (`change_password(text,text)` 149, `job_photos` 142,
  `trudnik_dj` 148, RLS/grants 123–133), но ledger их не знал.
- Pending по ledger: 123–149 (27 файлов). `profiles.email_verified` default: `true`.
- **Production был bootstrapped out-of-band**: ledger пуст (`applied_before=0`), а схема
  уже содержала объекты 067–149.

## Rehearsal на клоне (Docker Desktop, локально)

1. Клон `trudnik_migtest` создан через `pg_dump -Fc` + `pg_restore` (24 MB → 22 MB,
   37 записей `_migrations`, 70 профилей).
2. `apply_migrations.py --dry-run` → 27 pending.
3. Первый apply упал на **130**: `function public.register_user(text,text,text,text)
   does not exist` — в БД уже 5-арг версия (075/080/141), 4-арг удалена 143.
4. **Исправление 130:** `DO`-блок с `to_regprocedure` и `ALTER FUNCTION` для 4-арг/5-арг
   `register_user`; остальные функции — как были. Миграция стала идемпотентной на
   dump-restored БД.
5. Повторный apply на клоне: 123–149 успешно (7 предыдущих + 20), затем 150.
6. Клон: **65/65**, `email_verified default=false`, `change_password(text,text)` present,
   `register_user` 5-арг, `sync_user_skills` present.

## Dev `trudnik`

- **Бэкап:** `/tmp/trudnik_pre_p113.dump` (513.6 KB, custom format) внутри `trudnik-db`.
- Применено **28 миграций** (123–150), все успешно.
- Итог: **65/65**, `email_verified default=false`, `change_password(text,text)` present.
- Gate: `scripts/check_migrations.py` → `RESULT: OK`, exit 0.
- `trudnik_test` (Django test clone) не мигрировался этим прогоном; тесты используют
  ORM-модель `default=False` (P110) и отдельный clone. Для полного соответствия тест-клона
  можно применить 150 отдельно; на тесты это не влияет.

## Gate

`scripts/check_migrations.py`:
- читает `migrations/*.sql` и `_migrations`;
- проверяет `profiles.email_verified default=false`;
- проверяет `change_password(text,text)`;
- читает `.env` (если env не задан) и remap `db`→`localhost:5433` как Django settings;
- exit 0/1/2, секреты не печатает.

Использование:
```bash
python scripts/check_migrations.py
# prod/CI:
DATABASE_ADMIN_URL=postgresql://... python scripts/check_migrations.py
```

## Production (Amvera) — выполнено 2026-10-31

`Dockerfile.djadmin` содержит gated hook. Обычный деплой ничего не применяет; миграции
запускаются только при явном флаге:

- `MIGRATIONS_ENABLED=true` — `apply_migrations.py --dry-run` → `apply_migrations.py` →
  `check_migrations.py`; ошибка любого шага останавливает контейнер (`exit 1`).
- `MIGRATIONS_RECONCILE=true` — одноразовая сверка ledger: `reconcile_migrations.py`
  (8 sentinel-объектов, вставка недостающих 067–149 с checksum, `ON CONFLICT DO NOTHING`)
  → apply → check. Нужен только для БД, bootstrapped вне ledger.

### Ход работ и восстановление после сбоя

1. Бэкап `trudnik-db` сделан владельцем до окна.
2. Первый деплой с `MIGRATIONS_ENABLED=true` упал: ledger пуст, `067_bootstrap_amvera.sql`
   не применился (`cannot change return type of existing function login_user`); приложение
   ушло в `RUN_PROBLEM`.
3. Восстановление: `MIGRATIONS_ENABLED=false` → restart → `RUNNING`; затем добавлен
   `scripts/reconcile_migrations.py` и ветка `MIGRATIONS_RECONCILE` в `Dockerfile.djadmin`.
4. Деплой с `MIGRATIONS_RECONCILE=true`:
   `RECONCILE: files=65 applied_before=0 inserted_067_149=64 deferred_150_plus=['150_email_verified_default_false.sql']`
   → `RECONCILE: OK` → apply 150 → `RESULT: OK`.
5. Флаги возвращены в `false`; следующий restart — обычный, без миграций.
6. Проверено: ledger **65/65**, `profiles.email_verified default=false`,
   `change_password(text,text)` present; `/health` 200, проект `RUNNING`.
7. Дополнительно в прод задеплоены E001 (маскирование секретов на `/admin/env/`) и
   L001 (`/privacy`, `/terms`, `/safety` → 200).

### Правила на будущее

- Перед миграциями — бэкап БД; после — `check_migrations.py` (exit 0).
- Не оставлять `MIGRATIONS_ENABLED=true` / `MIGRATIONS_RECONCILE=true` между деплоями.
- `MIGRATIONS_RECONCILE` — только для сверки bootstrapped-ledger; для обычных миграций
  использовать `MIGRATIONS_ENABLED`.
- Откат — restore снапшота; ledger восстанавливается вместе с БД.
