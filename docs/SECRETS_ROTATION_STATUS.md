# Статус ротации секретов, утёкших в git-историю

> GitGuardian обнаружил 8 инцидентов. Ниже — что именно утекло, в каких
> коммитах, и текущий статус каждого секрета. Отметьте инциденты как
> «Revoked» в GitGuardian для тех, где ротация завершена.

## Утёкшие секреты

| # | Секрет | Где в истории | Ротация | Статус |
|---|--------|---------------|---------|--------|
| 1 | **SMTP_PASSWORD** (`lvszpk...`) | `.env.amvera` (ee881ea, af3704e, b416c72), `scripts/env_trudnik_app.env` (38c2725) | Новое значение `wirdw...` установлено в Amvera env 2026-10-30 | ✅ **ROTATED** — старый пароль недействителен |
| 2 | **VAPID_PRIVATE_KEY** (`JcuSS...`) | `.env.amvera` (ee881ea, af3704e, f1480d5) | Новая пара сгенерирована и установлена в Amvera env 2026-10-31 | ✅ **ROTATED** — старые ключи недействительны |
| 3 | **VAPID_PUBLIC_KEY** (`BClxC...`) | `.env.amvera` (f1480d5) | — || ✅ **ROTATED** (вместе с private) |
| 4 | **YANDEX_MAPS_API_KEY** (`09ff2...`) | `.env.amvera`, `scripts/env_trudnik_app.env` | Не проверено | ⚠️ **ДЕЙСТВИЕ ВЛАДЕЛЬЦА**: проверить в [console.cloud.yandex.ru](https://console.cloud.yandex.ru) → API-ключи; если активен — отозвать и выпустить новый |
| 5 | **SECRET_KEY** (PLACEHOLDER) | `.env.amvera` | Новое значение установлено 2026-10-30 (рандомный token_urlsafe) | ✅ **ROTATED** |
| 6 | **PGRST_JWT_SECRET** | `.env.amvera`, `archive/env_trudnik_pr.env` | Значение в Amvera env проекта trudnik-pr — не менялось через нас | ⚠️ **ДЕЙСТВИЕ ВЛАДЕЛЬЦА**: сменить в ЛК trudnik-pr → env |
| 7 | **Пароль БД** (`Jf9jp...`) | `.env.amvera`, `archive/env_*.env` | Пользователь взял ответственность на себя (2026-10-30) | ⚠️ **НА ВЛАДЕЛЬЦЕ** |
| 8 | **Пароль Redis** | `.env.amvera`, `archive/env_*.env` | Пользователь взял ответственность на себя | ⚠️ **НА ВЛАДЕЛЬЦЕ** |

## Ложные срабатывания (не требуют действий)

| # | Что | Почему |
|---|-----|--------|
| 1 | `tests/test_security.py` — пароли `weakp@ss1`, `Abc1!` | Тестовые данные для валидатора паролей; файл удалён из main (Flask-тесты) |
| 2 | `.env.example` — `change-me-*` | Шаблон с заглушками, не секреты |
| 3 | `scripts/env_trudnik_app.env` (текущая версия) — `PLACEHOLDER_*` | Заглушки после санитизации 82cafb7 |

## Что сделано для предотвращения

1. **Env-файлы удалены из git-трекинга** (aaded70):
   - `scripts/env_trudnik_app.env`, `archive/env_*.env`, `.env.staging`
2. **`.gitignore` дополнен**: `scripts/env_*.env`, `archive/env_*.env`,
   `.env.staging`, `.env.amvera`, `.env.production`, `*.env.local`
3. **Pre-commit hook `detect-secrets`** — работает с начала проекта,
   блокирует коммиты с обнаруженными секретами
4. **Все реальные секреты хранятся ТОЛЬКО в Amvera env** (платформенные
   переменные, не в git)

## Почему НЕ переписываем git-историю

- Репозиторий **приватный** — доступ только у владельца
- Все критичные секреты уже **ротированы** (SMTP, VAPID, SECRET_KEY)
- Переписывание истории (`git filter-branch` / BFG) ломает все клоны,
  Amvera-деплой-зеркало и теги — риск больше, чем польза
- GitGuardian позволяет отметить инциденты как «Revoked» после ротации

## Действия владельца (для полного закрытия)

1. **Yandex Maps API key**: Console → API-ключи → отозвать `09ff2043-...` → выпустить новый → обновить в Amvera env `trudnik` (переменная `YANDEX_MAPS_API_KEY`)
2. **PGRST_JWT_SECRET**: ЛК Amvera → trudnik-pr → env → сменить значение → rebuild
3. **Пароль БД**: ЛК Amvera → trudnik-db → сменить пароль → обновить `DATABASE_URL` и `DJANGO_DATABASE_URL` в env проекта trudnik
4. **Пароль Redis**: ЛК Amvera → trudnik-redis → сменить → обновить `REDIS_URL` в env
5. **GitGuardian**: для инцидентов #1–3, #5 отметить «Revoked» (ротация завершена)
