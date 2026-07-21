#!/bin/bash
# ============================================================
# amvera_db_backup.sh — Бэкап PostgreSQL в Amvera Cloud
# Использование:
#   ./amvera_db_backup.sh create [db-slug]  — создать бэкап
#   ./amvera_db_backup.sh list   [db-slug]  — список бэкапов
#   ./amvera_db_backup.sh delete [db-slug] [backup-id] — удалить бэкап
#
#   db-slug — slug БД (по умолчанию: trudnik-db)
# ============================================================

set -euo pipefail

AMVERA="${AMVERA_CLI:-amvera}"
ACTION="${1:-list}"
DB_SLUG="${2:-trudnik-db}"
BACKUP_ID="${3:-}"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  PostgreSQL: ${DB_SLUG}${NC}"
echo -e "${CYAN}  Действие:   ${ACTION}${NC}"
echo -e "${CYAN}  Дата:       $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}============================================${NC}"

# 1. Авторизация (на случай, если сессия истекла)
echo ""
echo -e "${YELLOW}🔑 Авторизация...${NC}"
"$AMVERA" login --user "${AMVERA_USER:-}" --password "${AMVERA_PASSWORD:-}" 2>&1 || true

case "$ACTION" in
    create)
        echo ""
        echo -e "${YELLOW}📦 Создание бэкапа PostgreSQL ${DB_SLUG}...${NC}"
        CREATE_OUTPUT=$("$AMVERA" psql backup create --slug "$DB_SLUG" 2>&1)
        CREATE_EXIT=$?

        if [ $CREATE_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка создания бэкапа (exit code: $CREATE_EXIT)${NC}"
            echo "$CREATE_OUTPUT"
            exit 1
        fi

        echo -e "${GREEN}✅ Бэкап успешно создан!${NC}"
        echo "$CREATE_OUTPUT"

        echo ""
        echo -e "${YELLOW}🧹 Ротация старых бэкапов (>30 дней)...${NC}"
        if [ -d "/data/backups" ]; then
            find /data/backups/ -name "trudnik_*.sql.gz" -mtime +30 -delete -print 2>/dev/null || true
            echo -e "${GREEN}✅ Ротация завершена${NC}"
        else
            echo -e "${YELLOW}⚠️  /data/backups не существует — ротация пропущена${NC}"
        fi

        echo ""
        echo -e "${YELLOW}📋 Обновлённый список бэкапов:${NC}"
        "$AMVERA" psql backup list --slug "$DB_SLUG" 2>&1
        ;;

    list)
        echo ""
        echo -e "${YELLOW}📋 Список бэкапов PostgreSQL ${DB_SLUG}:${NC}"
        LIST_OUTPUT=$("$AMVERA" psql backup list --slug "$DB_SLUG" 2>&1)
        LIST_EXIT=$?

        if [ $LIST_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка получения списка бэкапов (exit code: $LIST_EXIT)${NC}"
            echo "$LIST_OUTPUT"
            exit 1
        fi

        echo "$LIST_OUTPUT"

        # Подсчёт количества бэкапов (если вывод есть)
        BACKUP_COUNT=$(echo "$LIST_OUTPUT" | grep -ci "backup\|id\|complete" 2>/dev/null || echo "?")
        echo ""
        echo -e "${CYAN}ℹ️  Завершено.${NC}"
        ;;

    delete)
        if [ -z "$BACKUP_ID" ]; then
            echo -e "${RED}❌ Ошибка: не указан ID бэкапа для удаления${NC}"
            echo ""
            echo "Использование: $0 delete <db-slug> <backup-id>"
            echo ""
            echo "Сначала получите список бэкапов: $0 list <db-slug>"
            exit 1
        fi

        echo ""
        echo -e "${YELLOW}🗑️  Удаление бэкапа ${BACKUP_ID} из ${DB_SLUG}...${NC}"
        DELETE_OUTPUT=$("$AMVERA" psql backup delete --slug "$DB_SLUG" --id "$BACKUP_ID" 2>&1)
        DELETE_EXIT=$?

        if [ $DELETE_EXIT -ne 0 ]; then
            echo -e "${RED}❌ Ошибка удаления бэкапа (exit code: $DELETE_EXIT)${NC}"
            echo "$DELETE_OUTPUT"
            exit 1
        fi

        echo -e "${GREEN}✅ Бэкап ${BACKUP_ID} удалён${NC}"
        echo "$DELETE_OUTPUT"
        ;;

    *)
        echo -e "${RED}❌ Неизвестное действие: ${ACTION}${NC}"
        echo ""
        echo "Использование:"
        echo "  $0 create [db-slug]              — создать бэкап"
        echo "  $0 list   [db-slug]              — список бэкапов"
        echo "  $0 delete [db-slug] [backup-id]  — удалить бэкап"
        echo ""
        echo "Параметры:"
        echo "  db-slug    — slug базы данных (по умолчанию: trudnik-db)"
        echo "  backup-id  — ID бэкапа (только для delete)"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ Операция с бэкапами завершена${NC}"
echo -e "${GREEN}============================================${NC}"
