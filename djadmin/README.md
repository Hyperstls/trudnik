# djadmin — Django «Трудник» (продакшен)

Django 5.2 LTS поверх общей БД PostgreSQL. Полностью заменил Flask-деплой
2026-10-30. Спецификация миграции — [docs/django_migration_prompt.md](../docs/django_migration_prompt.md).

## Домены (Amvera, проект trudnik)

| Домен | Назначение |
|---|---|
| **xn--d1aigknli.xn--p1ai** (трудник.рф) | основной публичный домен |
| trudnik-hyperstls.msk1.amvera.tech | технический HTTPS-домен |
| run-trudnik | внутреннее имя сервиса |
| trudnik-db-hyperstls.tcp-msk1.amvera.tech:5432 | ВНЕШНИЙ доступ к БД (использует Django, роль trudnik_dj) — не удалять! |
| cnpg-trudnik-db-rw | внутреннее rw-имя БД (кластер с пустыми грантами trudnik_dj — не используется) |

## Ветки и деплой

- **main** = стабильный Django; работа идёт в **main-jango** (после каждой фазы: `git push origin main-jango:main`).
- **Прод деплоится из master** репо Amvera: `git push amvera-msk1 main-jango:master --force` + `rebuildProject` (MCP) — смена ветки в ЛК НЕ работает.
- Откат на Flask: `git push amvera-msk1 9b3ed42:master --force` + restart.

## Локальный запуск и тесты

```bash
docker compose up -d db redis
.venv/Scripts/python.exe -m pip install -r djadmin/requirements.txt
.venv/Scripts/python.exe djadmin/manage.py check
.venv/Scripts/python.exe scripts/dj_test_clone.py        # клон dev-БД (живые триггеры/RPC)
.venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1   # 131 тест
```

## Переменные окружения (прод, проект trudnik)

Общие с Flask (SECRET_KEY — общий ⇒ токены писем Flask↔Django взаимозаменяемы,
SMTP_*, SMARTCAPTCHA_*, MAX_WEBHOOK_SECRET, WORKER_SITE_URL, REDIS_URL).
Django-специфичные: `DJANGO_DATABASE_URL` (роль trudnik_dj, внешний хост БД),
`DJANGO_WHITENOISE_MANIFEST=1`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
`MAX_BOT_USERNAME` (нужно задать для верификации через MAX).

## Верификация через MAX

Профиль → «Подтвердить через MAX» → одноразовая ссылка (10 мин) → бот.
Требует: в ЛК MAX-бота webhook `https://xn--d1aigknli.xn--p1ai/messenger/webhook/max`
с секретом = MAX_WEBHOOK_SECRET; в env — MAX_BOT_USERNAME.

## Известные особенности

- БД подключена через внешний ингресс (внутренний кластер не имеет грантов trudnik_dj).
- Роль trudnik_dj: BYPASSRLS ⇒ видимость данных гарантируют queryset-менеджеры
  (Job.public, Profile.public_workers) — см. спеку §1.3/ADR-4.
- Фоновые задачи Flask (outbox-доставка, авто-истечение заданий, авто-заморозка)
  не переноcены до фазы 3.
