# Migration ledger — P1-13 / DB-default P1-10

**Дата:** 2026-11-03
**Статус:** dev и production приведены к **73/73** (150 + 151–158); прод RUNNING, `/health` 200,
`/privacy`, `/terms`, `/safety` — 200. Флаги `MIGRATIONS_ENABLED` и
`MIGRATIONS_RECONCILE` на проде — **false**.

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
