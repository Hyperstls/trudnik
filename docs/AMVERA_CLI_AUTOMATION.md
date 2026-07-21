# Автоматизация работы с Amvera Cloud CLI

> **Дата исследования:** 2026-06-26  
> **Версия Amvera CLI:** 1.2.2  
> **Проект:** Trudnik (`trudnik`)  
> **Аккаунт:** hyperstls (prcp2@inbox.ru)  
> **Регион:** msk_0  
> **Баланс:** 134.66 ₽  
> **Тариф:** BEGINNER (CPU 0.25 ядра, RAM 0.5 ГБ, SSD 5 ГБ)

---

## 1. Конфигурация проекта (`amvera.yaml`)

Файл [`amvera.yaml`](../amvera.yaml:1) в корне проекта:

```yaml
meta:
  environment: docker
  toolchain:
    name: docker
    version: latest
build:
  dockerfile: Dockerfile
  skip: false
run:
  persistenceMount: /data
  containerPort: 8000
  servicePort: 80
```

**Ключевые особенности:**
- Деплой через Docker-образ (сборка из [`Dockerfile`](../Dockerfile:1))
- Приложение внутри контейнера слушает порт **8000** (Uvicorn: `asgi:application`)
- Amvera пробрасывает на внешний порт **80**
- Монтирование `/data` для постоянного хранения

---

## 2. Полный список команд Amvera CLI

Ниже приведён полный список команд, полученный через `amvera help`. Команды, помеченные `(*)`, недоступны без авторизации.

### 2.1 Встроенные команды

| Команда | Описание |
|---------|----------|
| `help` | Справка по любой команде |
| `update enable` | Включить автообновления CLI |
| `update disable` | Отключить автообновления CLI |
| `update` | Выбор версии и обновление CLI |
| `version`, `--version`, `-v` | Версия приложения |

### 2.2 Управление пользователем

| Команда | Описание | Статус |
|---------|----------|--------|
| `whoami` | Информация о текущем пользователе | ✅ Доступна |
| `logout` | Выход из Amvera Cloud | ✅ Доступна |
| `balance` | Текущий баланс | ✅ Доступна |
| `region` | Текущий регион | ✅ Доступна |
| `region select` | Выбор региона по умолчанию | ✅ Доступна |
| `* login` | Вход в Amvera Cloud | ❌ Недоступна (помечена `*`) |

### 2.3 Создание проектов

| Команда | Описание |
|---------|----------|
| `create` | Создать новый проект |
| `create project` | Создать новый проект (полный синоним) |
| `create postgresql` / `create psql` / `create postgre` | Создать кластер PostgreSQL (CNPG) |
| `create preconfigured` / `create preconf` | Создать предварительно настроенный сервис из marketplace |

### 2.4 Получение информации о проектах

| Команда | Описание |
|---------|----------|
| `get` | Список ВСЕХ проектов (включая БД и сервисы) |
| `get project` / `get projects` | Список только проектов |
| `get preconfigured` / `get conf` / `get preconf` | Список предварительно настроенных сервисов |
| `get psql` / `get postgresql` / `get postgre` | Список PostgreSQL-кластеров |
| `get env` / `get environment` / `get envs` | Список переменных окружения |
| `get domain` / `get domains` | Список доменов |
| `describe project` | Детальная информация о проекте |
| `describe preconfigured` / `describe preconf` | Информация о предварительно настроенном сервисе |
| `describe postgresql` / `describe postgre` / `describe psql` | Информация о PostgreSQL |

### 2.5 Действия с проектами

| Команда | Описание |
|---------|----------|
| `rebuild` | Пересобрать проект (**не работает** для PostgreSQL и preconfigured) |
| `start` | Запустить проект |
| `stop` | Остановить проект |
| `restart` | Перезапустить проект |
| `freeze` | Заморозить проект (slug) |
| `delete` | Удалить проект по slug |
| `scale` | Изменить количество инстансов проекта |

### 2.6 Переменные окружения

| Команда | Описание |
|---------|----------|
| `env` | Список переменных окружения |
| `env add` / `env create` | Добавить переменную окружения |
| `env update` / `env change` | Обновить переменную окружения |
| `env delete` / `env remove` | Удалить переменную окружения |

### 2.7 Логи

| Команда | Описание |
|---------|----------|
| `logs build` | Логи сборки (build stage) |
| `logs run` | Логи выполнения (run stage) |

### 2.8 Домены

| Команда | Описание |
|---------|----------|
| `domain` | Список доменов проекта |

### 2.9 PostgreSQL / Бэкапы

| Команда | Описание |
|---------|----------|
| `psql` | Список всех PostgreSQL-кластеров |
| `psql backup create` | Создать бэкап PostgreSQL |
| `psql backup list` / `psql backup ls` | Список бэкапов PostgreSQL |
| `psql backup delete` | Удалить бэкап PostgreSQL |
| `psql restore` | Восстановить PostgreSQL из бэкапа |
| `psql scheduled` | Включить/отключить автоматические бэкапы |

> **💡 Стратегия бэкапов:** Используйте скрипт `scripts/amvera_db_backup.sh` для ручного создания, просмотра и удаления бэкапов PostgreSQL. Рекомендуется настроить автоматическое резервное копирование через `psql scheduled` и регулярно создавать бэкапы перед каждым деплоем в production. Подробнее: `./scripts/amvera_db_backup.sh create` — создание бэкапа, `./scripts/amvera_db_backup.sh list` — просмотр списка.

### 2.10 Выгрузка / загрузка данных

| Команда | Описание |
|---------|----------|
| `upload code` | Загрузить исходный код в репозиторий |
| `upload data` | Загрузить файлы в data-хранилище |
| `download code` | Скачать архив проекта с кодом |
| `download data` | Скачать архив с данными |

### 2.11 Тарифы

| Команда | Описание |
|---------|----------|
| `tariff` | Информация о тарифе проекта |
| `tariff list` / `tariff ls` | Список всех доступных тарифов |
| `tariff update` | Изменить тариф |

---

## 3. Инфраструктура проекта Trudnik

### 3.1 Все сервисы (из `amvera get`)

| ID | Имя | Slug | Статус | Тип |
|----|-----|------|--------|-----|
| 158841 | **Trudnik** | `trudnik` | RUNNING | PROJECT |
| 159810 | **trudnik-db** | `trudnik-db` | RUNNING | POSTGRESQL |
| 159802 | **trudnik-pgAdmin** | `trudnik-pgadmin` | RUNNING | PRECONFIGURED |
| 159797 | **trudnik-redis** | `trudnik-redis` | RUNNING | PRECONFIGURED |
| 159794 | **trudnik-PR** | `trudnik-pr` | RUNNING | PRECONFIGURED |

### 3.2 Домены (из `amvera domain --slug trudnik`)

| Домен | Тип | Статус |
|-------|-----|--------|
| `trudnik-hyperstls.amvera.io` | EXTERNAL / HTTPS | Активен, по умолчанию |
| `amvera-hyperstls-run-trudnik` | INTERNAL / HTTP | Активен, по умолчанию |

### 3.3 Детальная информация (из `amvera describe project --slug trudnik`)

| Параметр | Значение |
|----------|----------|
| ID | 158841 |
| Имя | Trudnik |
| Slug | `trudnik` |
| Статус | RUNNING |
| Статус-сообщение | Project successfully deployed |
| Требуется инстансов | 1 |
| Текущий инстансов | 1 |
| Git clone | `git clone https://git.amvera.ru/hyperstls/trudnik` |
| Git remote | `git remote add amvera https://git.amvera.ru/hyperstls/trudnik` |
| Тариф | BEGINNER |

### 3.4 Тариф (из `amvera tariff --slug trudnik`)

| Параметр | Значение |
|----------|----------|
| Название | BEGINNER |
| CPU | 0.25 ядра |
| RAM | 0.5 ГБ |
| SSD | 5.0 ГБ |

### 3.5 Логи сборки (из `amvera logs build --slug trudnik`)

Приложение запускается через:
```
uvicorn asgi:application --host 0.0.0.0 --port 8000 --workers 2
```

Healthcheck:
```
python -c "import urllib.request, sys; resp = urllib.request.urlopen('http://localhost:8000/ready', timeout=3); sys.exit(0 if resp.status == 200 else 1)" || exit 1
```

Docker-образ пушится в: `cr.yandex/crp2gf3gm8rv83kfkvet/amvera-hyperstls-trudnik`

---

## 4. Сценарии использования в разработке

### 4.1 Деплой новой версии

| Команда | Описание |
|---------|----------|
| [`rebuild --slug trudnik`](#61-быстрый-деплой-после-git-push) | Пересобрать и перезапустить проект |
| [`logs build --slug trudnik`](#61-быстрый-деплой-после-git-push) | Проверить логи сборки |
| [`logs run --slug trudnik`](#61-быстрый-деплой-после-git-push) | Проверить логи выполнения |

**Когда применять:** после каждого `git push` в основную ветку.

### 4.2 Мониторинг состояния

| Команда | Описание |
|---------|----------|
| [`get`](#62-мониторинг-состояния) | Статус всех проектов/сервисов |
| [`describe project --slug trudnik`](#62-мониторинг-состояния) | Детальная информация о проекте |
| [`logs run --slug trudnik`](#62-мониторинг-состояния) | Последние логи выполнения |

**Когда применять:** при подозрении на проблемы, ежедневно при активной разработке.

### 4.3 Бэкап базы данных

| Команда | Описание |
|---------|----------|
| [`psql backup create --slug trudnik-db`](#63-бэкап-postgresql) | Создать бэкап |
| [`psql backup list --slug trudnik-db`](#63-бэкап-postgresql) | Список бэкапов |

**Когда применять:** перед миграциями, по расписанию (например, ежедневно).

### 4.4 Управление переменными окружения

| Команда | Описание |
|---------|----------|
| `env --slug trudnik` | Просмотр переменных (⚠️ **баг в CLI v1.2.2** — ошибка парсинга) |
| [`env add --slug trudnik --name KEY --value VAL`](#64-управление-переменными-окружения) | Добавить переменную |
| [`env update --slug trudnik --name KEY --value VAL`](#64-управление-переменными-окружения) | Обновить переменную |
| [`env delete --slug trudnik --name KEY`](#64-управление-переменными-окружения) | Удалить переменную |

**Когда применять:** при добавлении новых API-ключей, смене секретов, настройке окружения.

### 4.5 Масштабирование

| Команда | Описание |
|---------|----------|
| `scale --slug trudnik --instances 2` | Увеличить количество инстансов |
| `scale --slug trudnik --instances 1` | Уменьшить до одного |

**Когда применять:** при ожидаемых всплесках нагрузки.

### 4.6 Управление тарифом

| Команда | Описание |
|---------|----------|
| `tariff update --slug trudnik --tariff ADVANCED` | Перейти на тариф ADVANCED |
| `tariff --slug trudnik` | Текущий тариф |

**Когда применять:** при необходимости увеличить ресурсы.

---

## 5. Замеченные проблемы в Amvera CLI v1.2.2

### 5.1 Ошибка парсинга `env`

Команда `env --slug trudnik` завершается с ошибкой:

```
Error while extracting response for type [java.util.List<...EnvResponse>] and content type [application/json]
```

Это **баг в CLI v1.2.2** — Java-приложение не может распарсить ответ API. В результатах `describe project` секция "ENVIRONMENT VARIABLES" также падает с этой ошибкой.

**Workaround:** Временно использовать `describe project --slug trudnik` — она выводит остальную информацию, хотя env-секция тоже падает. Для реального управления env пользоваться веб-интерфейсом Amvera Cloud.

### 5.2 Git bash — обязательное требование

На Windows CLI **работает только через Git bash**. Прямой запуск `amvera.exe` в cmd или PowerShell приводит к ошибкам.

---

## 6. Скрипты автоматизации

> **Канонические скрипты** живут в `scripts/amvera_*.sh` (`amvera_full_cycle.sh`, `amvera_deploy.sh`, `amvera_env_manager.sh`, `amvera_db_backup.sh`, `amvera_monitor.sh`) и используют env `AMVERA_CLI` (по умолчанию `amvera`). Ниже — справочные inline-варианты (могут отставать от `scripts/`; предпочтительнее `scripts/`).

Все скрипты рассчитаны на запуск через Git bash (`C:\Program Files\Git\bin\bash.exe`).
Путь к CLI: `C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe` (или задайте env `AMVERA_CLI`).

Для удобства рекомендуется создать алиас:

```bash
alias amvera="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"
```

### 6.1 Быстрый деплой после git push

```bash
#!/usr/bin/env bash
# quick-deploy.sh — пересборка + проверка логов
# Использование: ./quick-deploy.sh [slug]
# По умолчанию: trudnik

SLUG="${1:-trudnik}"
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

echo "=== 1. Пересборка проекта $SLUG ==="
"$AMVERA" rebuild --slug "$SLUG"
if [ $? -ne 0 ]; then
    echo "❌ Ошибка пересборки!"
    exit 1
fi

echo ""
echo "=== 2. Ожидание завершения сборки (30 сек) ==="
sleep 30

echo ""
echo "=== 3. Логи сборки ==="
"$AMVERA" logs build --slug "$SLUG" | tail -20

echo ""
echo "=== 4. Логи выполнения (последние 15 строк) ==="
"$AMVERA" logs run --slug "$SLUG" | tail -15

echo ""
echo "✅ Деплой завершён. Проверьте логи на наличие ошибок."
```

### 6.2 Мониторинг состояния

```bash
#!/usr/bin/env bash
# monitor.sh — мониторинг состояния проекта
# Использование: ./monitor.sh [slug]
# По умолчанию: trudnik

SLUG="${1:-trudnik}"
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

echo "=== СОСТОЯНИЕ ПРОЕКТА: $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

echo "--- Все сервисы ---"
"$AMVERA" get

echo ""
echo "--- Детальная информация о проекте $SLUG ---"
"$AMVERA" describe project --slug "$SLUG" 2>&1 | head -20

echo ""
echo "--- Домены ---"
"$AMVERA" domain --slug "$SLUG"

echo ""
echo "--- Последние логи выполнения ---"
"$AMVERA" logs run --slug "$SLUG" | tail -10

echo ""
echo "--- Баланс ---"
"$AMVERA" balance
```

### 6.3 Бэкап PostgreSQL

```bash
#!/usr/bin/env bash
# backup-psql.sh — создание и просмотр бэкапов PostgreSQL
# Использование:
#   ./backup-psql.sh create [db-slug]  — создать бэкап
#   ./backup-psql.sh list [db-slug]    — список бэкапов

ACTION="${1:-list}"
DB_SLUG="${2:-trudnik-db}"
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

echo "=== PostgreSQL: $DB_SLUG ==="

case "$ACTION" in
    create)
        echo "Создание бэкапа..."
        "$AMVERA" psql backup create --slug "$DB_SLUG"
        echo ""
        echo "Обновлённый список бэкапов:"
        "$AMVERA" psql backup list --slug "$DB_SLUG"
        ;;
    list)
        echo "Список бэкапов:"
        "$AMVERA" psql backup list --slug "$DB_SLUG"
        ;;
    *)
        echo "Использование: $0 {create|list} [db-slug]"
        exit 1
        ;;
esac
```

### 6.4 Управление переменными окружения

```bash
#!/usr/bin/env bash
# env-manager.sh — управление переменными окружения
# Использование:
#   ./env-manager.sh list [slug]
#   ./env-manager.sh add <KEY> <VALUE> [slug]
#   ./env-manager.sh update <KEY> <VALUE> [slug]
#   ./env-manager.sh delete <KEY> [slug]

ACTION="${1:-list}"
KEY="$2"
VALUE="$3"
SLUG="${4:-trudnik}"
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

case "$ACTION" in
    list)
        echo "=== Переменные окружения проекта $SLUG ==="
        # ⚠️ Известный баг CLI v1.2.2: команда env падает с ошибкой парсинга JSON
        "$AMVERA" env --slug "$SLUG" 2>&1 || echo "⚠️  Баг CLI: используйте веб-интерфейс для просмотра"
        ;;
    add)
        echo "=== Добавление переменной $KEY в проект $SLUG ==="
        "$AMVERA" env add --slug "$SLUG" --name "$KEY" --value "$VALUE"
        ;;
    update)
        echo "=== Обновление переменной $KEY в проекте $SLUG ==="
        "$AMVERA" env update --slug "$SLUG" --name "$KEY" --value "$VALUE"
        ;;
    delete)
        echo "=== Удаление переменной $KEY из проекта $SLUG ==="
        "$AMVERA" env delete --slug "$SLUG" --name "$KEY"
        ;;
    *)
        echo "Использование: $0 {list|add|update|delete} [key] [value] [slug]"
        exit 1
        ;;
esac
```

### 6.5 Полный цикл CI/CD (git push → rebuild → check)

```bash
#!/usr/bin/env bash
# full-cycle.sh — полный цикл деплоя
# Использование: ./full-cycle.sh [slug] [commit-message]
# По умолчанию: slug=trudnik, message="Auto-deploy $(date)"

SLUG="${1:-trudnik}"
COMMIT_MSG="${2:-Auto-deploy $(date '+%Y-%m-%d %H:%M:%S')}"
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

set -e  # Выход при первой ошибке

echo "========================================="
echo " ПОЛНЫЙ ЦИКЛ ДЕПЛОЯ"
echo " Проект: $SLUG"
echo " Дата:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# Шаг 1: Статус до деплоя
echo ""
echo "=== Шаг 1: Текущее состояние ==="
"$AMVERA" describe project --slug "$SLUG" 2>&1 | head -10

# Шаг 2: Git push (если есть изменения)
echo ""
echo "=== Шаг 2: Git push ==="
if git status --porcelain | grep -q .; then
    git add -A
    git commit -m "$COMMIT_MSG"
    git push origin main
    echo "✅ Изменения отправлены в репозиторий"
else
    echo "ℹ️  Нет незакоммиченных изменений"
fi

# Шаг 3: Push в Amvera
echo ""
echo "=== Шаг 3: Push в Amvera ==="
git push amvera main:master 2>&1 || echo "ℹ️  Используем rebuild..."

# Шаг 4: Пересборка
echo ""
echo "=== Шаг 4: Пересборка проекта ==="
"$AMVERA" rebuild --slug "$SLUG"
echo "⏳ Ожидание 40 секунд..."
sleep 40

# Шаг 5: Проверка логов сборки
echo ""
echo "=== Шаг 5: Логи сборки (последние 10 строк) ==="
BUILD_LOG=$("$AMVERA" logs build --slug "$SLUG" 2>&1)
echo "$BUILD_LOG" | tail -10

# Проверка на ошибки в сборке
if echo "$BUILD_LOG" | grep -qi "error"; then
    echo "❌ Обнаружены ошибки в сборке!"
    echo "$BUILD_LOG" | grep -i "error"
    exit 1
fi

# Шаг 6: Проверка логов выполнения
echo ""
echo "=== Шаг 6: Логи выполнения (последние 10 строк) ==="
"$AMVERA" logs run --slug "$SLUG" | tail -10

# Шаг 7: Healthcheck через внешний домен
echo ""
echo "=== Шаг 7: Healthcheck ==="
sleep 10
HEALTH_URL="https://${SLUG}-hyperstls.amvera.io/health"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Healthcheck пройден (HTTP $HTTP_CODE)"
else
    echo "⚠️  Healthcheck: HTTP $HTTP_CODE (возможно, приложение ещё стартует)"
fi

echo ""
echo "========================================="
echo " ✅ ЦИКЛ ЗАВЕРШЁН"
echo "========================================="
```

---

## 7. CI/CD интеграция (GitHub Actions)

> **Статус:** деплой в Amvera сейчас **ручной** через `scripts/amvera_*.sh`. Активные workflow — только `.github/workflows/test.yml` (тесты) и `build-apk.yml` (сборка APK). Раздел ниже описывает **предлагаемые** (не подключённые в репо) workflow деплоя.

### 7.1 Настройка Secrets в GitHub

Для работы GitHub Actions с Amvera CLI необходимо добавить следующие секреты в репозиторий (Settings → Secrets and variables → Actions):

| Secret | Описание |
|--------|----------|
| `AMVERA_USER` | Имя пользователя Amvera (`hyperstls`) |
| `AMVERA_PASSWORD` | Пароль от аккаунта Amvera |

### 7.2 Проблема авторизации

Команда `login` в Amvera CLI v1.2.2 **помечена `*`** как недоступная. Это означает, что на текущей версии CLI автоматическая авторизация в CI/CD через CLI невозможна. Однако, если токен авторизации сохраняется в файловом хранилище CLI, можно попробовать передать его как артефакт.

**Альтернативный подход:** Использовать прямой `git push` в репозиторий Amvera (Git-remote), который уже настроен:

```
git remote add amvera https://git.amvera.ru/hyperstls/trudnik
```

При `git push` на этот remote Amvera автоматически собирает и деплоит проект.

### 7.3 GitHub Actions workflow (push-based)

```yaml
# .github/workflows/deploy-amvera.yml
name: Deploy to Amvera Cloud

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Push to Amvera
        run: |
          git remote add amvera https://${{ secrets.AMVERA_USER }}:${{ secrets.AMVERA_PASSWORD }}@git.amvera.ru/hyperstls/trudnik.git
          git push amvera main:master
```

### 7.4 GitHub Actions workflow (CLI-based — если `login` заработает)

```yaml
# .github/workflows/deploy-amvera-cli.yml
name: Deploy to Amvera Cloud (CLI)

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Install Amvera CLI
        run: |
          curl -fsSL https://cli.amvera.com/install.sh | bash
          echo "$HOME/.amvera/bin" >> $GITHUB_PATH

      - name: Login to Amvera
        run: |
          amvera login --username ${{ secrets.AMVERA_USER }} --password ${{ secrets.AMVERA_PASSWORD }}

      - name: Upload code
        run: |
          amvera upload code --slug trudnik --path .

      - name: Rebuild project
        run: |
          amvera rebuild --slug trudnik

      - name: Wait and check logs
        run: |
          sleep 30
          amvera logs build --slug trudnik | tail -20
          amvera logs run --slug trudnik | tail -10
```

---

## 8. Шпаргалка (быстрые команды)

```bash
# Алиас для удобства
alias amvera="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"

# Информация
amvera whoami                          # кто я
amvera balance                         # баланс
amvera region                          # регион

# Проекты
amvera get                             # все сервисы
amvera describe project --slug trudnik # детали проекта

# Деплой
amvera rebuild --slug trudnik          # пересобрать
amvera logs build --slug trudnik       # логи сборки
amvera logs run --slug trudnik         # логи выполнения

# Бэкапы
amvera psql backup create --slug trudnik-db  # создать бэкап БД
amvera psql backup list --slug trudnik-db    # список бэкапов

# Домены
amvera domain --slug trudnik           # домены

# Переменные окружения (⚠️ баг CLI)
amvera env --slug trudnik              # ❌ не работает в v1.2.2
amvera env add --slug trudnik --name KEY --value VAL
amvera env update --slug trudnik --name KEY --value VAL
amvera env delete --slug trudnik --name KEY

# Управление
amvera start --slug trudnik            # запустить
amvera stop --slug trudnik             # остановить
amvera restart --slug trudnik          # перезапустить
amvera scale --slug trudnik --instances 2  # масштабировать

# Тариф
amvera tariff --slug trudnik           # текущий тариф
amvera tariff list                     # все тарифы
```

---

## 9. Рекомендации

1. **Используйте Git push вместо rebuild.** Поскольку `git remote add amvera` уже настроен для проекта, проще пушить напрямую в репозиторий Amvera — он сам соберёт и задеплоит проект.

2. **Мониторинг через скрипты.** Скрипты из раздела 6 можно добавить в `PATH` или использовать как алиасы в `.bashrc` для Git bash.

3. **Backup перед миграциями.** Перед применением SQL-миграций (файлы в [`migrations/`](../migrations/)) обязательно создавайте бэкап БД через `psql backup create`.

4. **Баланс 134 ₽.** Тариф BEGINNER достаточно скромный, следите за расходом. При росте нагрузки рассмотрите `tariff update`.

5. **env-баг.** Из-за бага в CLI v1.2.2 просмотр переменных окружения через CLI невозможен. Используйте личный кабинет Amvera Cloud для просмотра. Команды `add`/`update`/`delete` должны работать (проверьте при необходимости).
