# Restore drill (J137)

## Локальная проверка — пройдена

**Дата:** 2026-11-03
**Команда:** `.venv\Scripts\python.exe scripts\restore_drill.py --drop-target`

Скрипт копирует локальную БД `trudnik` в одноразовую `trudnik_restore_drill`
внутри того же Docker-контейнера `trudnik-db`, восстанавливает дамп и сравнивает
данные/схему. Прод при этом не затрагивается.

Результат:

| Проверка | Source | Target |
|---|---:|---:|
| profiles | 70 | 70 |
| jobs | 313 | 313 |
| applications | 42 | 42 |
| messages | 7 | 7 |
| notifications | 0 | 0 |
| site_pages | 0 | 0 |
| skills | 154 | 154 |
| PostGIS extension | — | OK |
| RLS на `profiles` | — | OK |
| RPC `apply_job_atomic` / `accept_application` / `withdraw_application_atomic` | — | 3 |

Дамп: 525 KiB. Одноразовая БД удалена (`--drop-target`).

## Правила безопасности скрипта

- Целевая БД обязана содержать `drill` в имени; совпадение с source запрещено.
- Source не изменяется.
- Если target уже существует — нужен явный `--recreate-target`.
- Пароль берётся из Django settings и передаётся в `docker exec` через env,
  в лог не выводится.
- Скрипт локальный (Docker `trudnik-db`). Для прода он не предназначен:
  никогда не запускайте его с прод-БД в качестве target.

## Восстановление прода (владелец)

1. В панели Amvera проверить доступные бэкапы/точки восстановления PostgreSQL
   и их срок хранения (политика провайдера).
2. Создать **отдельный временный** Postgres/PostGIS-кластер. Не восстанавливать
   поверх прод-БД.
3. Восстановить дамп нативным `pg_restore` (или средствами Amvera).
4. Прогнать те же проверки:
   - counts `profiles`, `jobs`, `applications`, `messages`, `notifications`, `site_pages`, `skills`;
   - `postgis` в `pg_extension`;
   - `relrowsecurity` у `profiles`;
   - наличие RPC `apply_job_atomic`, `accept_application`, `withdraw_application_atomic`.
5. Поднять staging-копию приложения на временной БД, проверить `/health`,
   `/jobs`, вход и создание тестового отклика.
6. Зафиксировать RTO (время от начала до здорового staging), удалить временный
   кластер и дамп.

## Staging

Отдельный staging-проект Amvera не создан — это платное решение владельца.
Локальный аналог: dev-БД + `scripts/e2e/run_critical_flows.sh` (6 E2E-проверок).
