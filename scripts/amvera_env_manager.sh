#!/bin/bash
# ============================================================
# amvera_env_manager.sh — Управление переменными окружения
# Использование:
#   ./amvera_env_manager.sh list              [slug]
#   ./amvera_env_manager.sh show              [slug]  (синоним list)
#   ./amvera_env_manager.sh add    KEY VALUE  [slug]
#   ./amvera_env_manager.sh update KEY VALUE  [slug]
#   ./amvera_env_manager.sh delete KEY        [slug]
#   ./amvera_env_manager.sh dotenv            [slug]  — читать из .env
#
#   slug — slug проекта (по умолчанию: trudnik)
# ============================================================
# ⚠️  Известный баг CLI v1.2.2: команда `env` падает с ошибкой
#     парсинга JSON. В этом случае используйте флаг `dotenv`
#     для чтения из локальных .env файлов.
# ============================================================

set -euo pipefail

AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"
ACTION="${1:-list}"
KEY="${2:-}"
VALUE="${3:-}"
SLUG="${4:-trudnik}"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Переменные окружения проекта: ${SLUG}${NC}"
echo -e "${CYAN}  Действие: ${ACTION}${NC}"
echo -e "${CYAN}============================================${NC}"

# 1. Авторизация (на случай, если сессия истекла)
echo ""
echo -e "${YELLOW}🔑 Авторизация...${NC}"
"$AMVERA" login --user Hyperstls --password "Step@1986" 2>&1 || true

case "$ACTION" in
    list|show)
        echo ""
        echo -e "${YELLOW}📋 Переменные окружения проекта ${SLUG}:${NC}"
        echo -e "${CYAN}⚠️  ВНИМАНИЕ: В CLI v1.2.2 команда \`env\` может падать${NC}"
        echo -e "${CYAN}   с ошибкой парсинга JSON (известный баг).${NC}"
        echo ""
        echo -e "${YELLOW}Попытка через CLI...${NC}"
        ENV_OUTPUT=$("$AMVERA" env --slug "$SLUG" 2>&1)
        ENV_EXIT=$?

        if [ $ENV_EXIT -ne 0 ]; then
            echo -e "${RED}❌ CLI вернул ошибку:${NC}"
            echo "$ENV_OUTPUT"
            echo ""
            echo -e "${YELLOW}💡 Используйте флаг \`dotenv\` для чтения из локальных .env файлов:${NC}"
            echo "   $0 dotenv $SLUG"
            echo ""
            echo -e "${YELLOW}💡 Или откройте веб-интерфейс Amvera Cloud:${NC}"
            echo "   https://app.amvera.cloud/"
        else
            echo "$ENV_OUTPUT"
        fi
        ;;

    add)
        if [ -z "$KEY" ] || [ -z "$VALUE" ]; then
            echo -e "${RED}❌ Ошибка: необходимо указать KEY и VALUE${NC}"
            echo "Использование: $0 add KEY VALUE [slug]"
            exit 1
        fi
        echo ""
        echo -e "${YELLOW}➕ Добавление переменной ${KEY}=${VALUE}...${NC}"
        ADD_OUTPUT=$("$AMVERA" env add --slug "$SLUG" --name "$KEY" --value "$VALUE" 2>&1)
        ADD_EXIT=$?
        if [ $ADD_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка добавления (exit code: $ADD_EXIT)${NC}"
            echo "$ADD_OUTPUT"
            exit 1
        fi
        echo -e "${GREEN}✅ Переменная ${KEY} добавлена${NC}"
        echo "$ADD_OUTPUT"
        ;;

    update|change)
        if [ -z "$KEY" ] || [ -z "$VALUE" ]; then
            echo -e "${RED}❌ Ошибка: необходимо указать KEY и VALUE${NC}"
            echo "Использование: $0 update KEY VALUE [slug]"
            exit 1
        fi
        echo ""
        echo -e "${YELLOW}🔄 Обновление переменной ${KEY}=${VALUE}...${NC}"
        UPDATE_OUTPUT=$("$AMVERA" env update --slug "$SLUG" --name "$KEY" --value "$VALUE" 2>&1)
        UPDATE_EXIT=$?
        if [ $UPDATE_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка обновления (exit code: $UPDATE_EXIT)${NC}"
            echo "$UPDATE_OUTPUT"
            exit 1
        fi
        echo -e "${GREEN}✅ Переменная ${KEY} обновлена${NC}"
        echo "$UPDATE_OUTPUT"
        ;;

    delete|remove)
        if [ -z "$KEY" ]; then
            echo -e "${RED}❌ Ошибка: необходимо указать KEY${NC}"
            echo "Использование: $0 delete KEY [slug]"
            exit 1
        fi
        echo ""
        echo -e "${YELLOW}🗑️  Удаление переменной ${KEY}...${NC}"
        DELETE_OUTPUT=$("$AMVERA" env delete --slug "$SLUG" --name "$KEY" 2>&1)
        DELETE_EXIT=$?
        if [ $DELETE_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка удаления (exit code: $DELETE_EXIT)${NC}"
            echo "$DELETE_OUTPUT"
            exit 1
        fi
        echo -e "${GREEN}✅ Переменная ${KEY} удалена${NC}"
        echo "$DELETE_OUTPUT"
        ;;

    dotenv)
        echo ""
        echo -e "${YELLOW}📂 Чтение переменных из локальных .env файлов...${NC}"

        # Пути к .env файлам
        ENV_FILES=(
            ".env.example"
            "archive/env_trudnik_db.env"
            "archive/env_trudnik_pgadmin.env"
            "archive/env_trudnik_pr.env"
            "archive/env_trudnik_redis.env"
        )

        FOUND=false
        for ENV_PATH in "${ENV_FILES[@]}"; do
            if [ -f "$ENV_PATH" ]; then
                FOUND=true
                echo ""
                echo -e "${CYAN}--- ${ENV_PATH} ---${NC}"
                # Показываем содержимое, маскируя значения секретов
                while IFS='=' read -r key value; do
                    # Пропускаем пустые строки и комментарии
                    if [ -z "$key" ] || [[ "$key" == \#* ]]; then
                        echo "$key${value:+=$value}"
                        continue
                    fi
                    # Маскируем длинные значения (секреты, пароли, ключи)
                    if [ ${#value} -gt 20 ]; then
                        echo "${key}=${value:0:10}...${value: -5}"
                    else
                        echo "${key}=${value}"
                    fi
                done < "$ENV_PATH"
            fi
        done

        if [ "$FOUND" = false ]; then
            echo -e "${YELLOW}ℹ️  Локальные .env файлы не найдены${NC}"
            echo "  Искал в:"
            for ENV_PATH in "${ENV_FILES[@]}"; do
                echo "    - $ENV_PATH"
            done
            echo ""
            echo -e "${YELLOW}💡 Используйте \`list\` для попытки чтения через CLI:${NC}"
            echo "   $0 list $SLUG"
        fi
        ;;

    *)
        echo -e "${RED}❌ Неизвестное действие: ${ACTION}${NC}"
        echo ""
        echo "Использование:"
        echo "  $0 list              [slug]  — показать переменные (через CLI)"
        echo "  $0 dotenv            [slug]  — читать из локальных .env файлов"
        echo "  $0 add    KEY VALUE  [slug]  — добавить переменную"
        echo "  $0 update KEY VALUE  [slug]  — обновить переменную"
        echo "  $0 delete KEY        [slug]  — удалить переменную"
        echo ""
        echo "Параметры:"
        echo "  slug — slug проекта (по умолчанию: trudnik)"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ Операция с переменными окружения завершена${NC}"
echo -e "${GREEN}============================================${NC}"
