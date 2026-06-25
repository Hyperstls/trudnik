# 🔐 Инструкция по устранению утечки секретов — «Трудник»

> ⚠️ ВНИМАНИЕ: Этот файл — напоминалка. Реальные пароли и токены могли утечь в Git-историю.
> Выполни все шаги последовательно.

---

## 1. Срочно сменить (утекли в репозиторий)

| # | Секрет | Значение (утёкшее) | Где найден | Что сделать |
|---|--------|-------------------|------------|-------------|
| 1 | **Пароль БД** | `***REMOVED***` | `.env.amvera`, `archive/env_trudnik_db.env`, `archive/env_trudnik_pr.env` | Сменить пароль PostgreSQL на Amvera, обновить во всех файлах |
| 2 | **Пароль суперпользователя БД** | `hyperstls` | `archive/env_trudnik_db.env` | Сменить, обновить в Amvera Secrets |
| 3 | **Пароль Redis** | `***REMOVED***` | `.env.amvera`, `archive/env_trudnik_redis.env`, `archive/env_trudnik_pgadmin.env` | Сменить, обновить везде |
| 4 | **JWT-секрет** | `95a6e0be...` | `.env.amvera`, `archive/env_trudnik_pr.env` | Сгенерировать новый: `python -c "import secrets; print(secrets.token_hex(32))"` |
| 5 | **Flask SECRET_KEY** | `***REMOVED***` | `.env.amvera` | Сгенерировать новый: `python -c "import secrets; print(secrets.token_hex(32))"` |
| 6 | **SMTP-пароль** | `lvszpkuthmspixnv` | `.env.amvera` | Сменить пароль Яндекс.Почты, обновить |
| 7 | **GIT_TOKEN** | `***REMOVED***...` | `.env.amvera` | **НЕМЕДЛЕННО ОТОЗВАТЬ** в GitHub Settings → Personal Access Tokens |
| 8 | **PA_API_TOKEN** | (значение в .env.amvera) | `.env.amvera` | Отозвать старый, выпустить новый |
| 9 | **YANDEX_GEOCODER_KEY** | (значение в .env.amvera) | `.env.amvera` | Проверить, не скомпрометирован ли |

---

## 2. Рекомендуется сменить (переиспользованы)

| Проблема | Рекомендация |
|----------|-------------|
| Пароль `***REMOVED***` используется для SECRET_KEY, Redis и pgAdmin | Использовать разные пароли для каждого сервиса |
| Все пароли в `archive/` (4 .env-файла) | Эти файлы ТОЛЬКО для справки. Заменить реальные пароли на placeholders: `REPLACE_ME` |

---

## 3. Очистка Git-истории

### Проверить, что утекло в Git:

```bash
# Проверить .env.amvera
git log -- .env.amvera

# Проверить старые пути scripts/ (перемещены в archive/)
git log -- scripts/env_trudnik_db.env
git log -- scripts/env_trudnik_redis.env
git log -- scripts/env_trudnik_pr.env
git log -- scripts/env_trudnik_pgadmin.env
```

### Если файлы найдены в истории — очистить:

```bash
# Удалить .env.amvera из всей истории
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env.amvera" \
  --prune-empty --tag-name-filter cat -- --all

# Удалить scripts/env_trudnik_*.env из всей истории
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch scripts/env_trudnik_db.env scripts/env_trudnik_redis.env scripts/env_trudnik_pr.env scripts/env_trudnik_pgadmin.env" \
  --prune-empty --tag-name-filter cat -- --all

# Опубликовать изменения
git push --force --all
git push --force --tags
```

> ⚠️ После `push --force` все разработчики должны переклонировать репозиторий!

---

## 4. Amvera Secrets (рекомендуемое хранение)

Все чувствительные переменные должны храниться в Amvera Secrets, а не в файлах репозитория.

Создать секреты в Amvera:

- [ ] `SECRET_KEY` — Flask secret key
- [ ] `DATABASE_URL` — URL подключения к PostgreSQL
- [ ] `PGRST_JWT_SECRET` — JWT-секрет для PostgREST
- [ ] `REDIS_URL` — URL подключения к Redis
- [ ] `SMTP_PASSWORD` — Пароль Яндекс.Почты
- [ ] `YANDEX_GEOCODER_KEY` — API-ключ Яндекс.Геокодера

После создания секретов — удалить значения из `.env.amvera`, оставив только placeholders.

---

## 5. Чек-лист после исправления

- [ ] Все пароли сменены на новые
- [ ] GIT_TOKEN отозван в GitHub
- [ ] Git-история очищена
- [ ] Новые пароли добавлены в Amvera Secrets
- [ ] `.env.amvera` больше не содержит реальных паролей
- [ ] `archive/env_trudnik_*.env` файлы содержат только placeholders
- [ ] Приложение перезапущено на Amvera с новыми секретами
