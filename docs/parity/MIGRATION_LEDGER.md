# Migration ledger — P1-13 / DB-default P1-10

**Дата:** 2026-10-31
**Статус:** **локальный dev исправлен**; production (Amvera) — pending deploy-window.

## Было

- `_migrations`: 37 записей, максимум `122_fix_outbox_grants.sql`.
- В БД уже были объекты поздних миграций (`change_password(text,text)` 149, `job_photos` 142,
  `trudnik_dj` 148, RLS/grants 123–133), но ledger их не знал.
- Pending по ledger: 123–149 (27 файлов). `profiles.email_verified` default: `true`.

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

## Production (Amvera) — что сделать в окно

`Dockerfile.djadmin` содержит gated hook: при `MIGRATIONS_ENABLED=true` контейнер до старта
выполняет `apply_migrations.py --dry-run` → `apply_migrations.py` → `check_migrations.py`;
без флага старт обычный. Это позволяет применить миграции одноразовым деплоем без чтения
секретов из UI.

1. Снапшот/бэкап БД Amvera (или `pg_dump`).
2. `MIGRATIONS_ENABLED=true DATABASE_ADMIN_URL=... python scripts/apply_migrations.py`
   (роль с DDL-правами; миграция 130 теперь идемпотентна).
3. `DATABASE_ADMIN_URL=... python scripts/check_migrations.py` → exit 0.
4. Деплой Django; проверить `change_password` reset и `email_verified` default.
5. При откате — restore снапшота; ledger восстанавливается вместе с БД.

**Production не трогался.** Локальный dev и rehearsal подтверждают процедуру; прод требует
своего окна/бэкапа.
