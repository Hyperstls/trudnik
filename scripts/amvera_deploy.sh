#!/bin/bash
# ============================================================
# amvera_deploy.sh — Быстрый деплой проекта Amvera
# Использование: ./amvera_deploy.sh [slug]
#   slug — slug проекта (по умолчанию: trudnik)
# ============================================================
# После git push: пересборка + проверка логов сборки и выполнения
# ============================================================

set -euo pipefail

AMVERA="${AMVERA_CLI:-amvera}"
SLUG="${1:-trudnik}"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Быстрый деплой проекта: ${SLUG}${NC}"
echo -e "${CYAN}  Дата: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}============================================${NC}"

# 1. Авторизация (на случай, если сессия истекла)
echo ""
echo -e "${YELLOW}🔑 Авторизация...${NC}"
"$AMVERA" login --user "${AMVERA_USER:-}" --password "${AMVERA_PASSWORD:-}" 2>&1 || true

# 2. Пересборка проекта
echo ""
echo -e "${YELLOW}🚀 Пересборка проекта ${SLUG}...${NC}"
"$AMVERA" rebuild --slug "$SLUG"
REBUILD_EXIT=$?

if [ $REBUILD_EXIT -ne 0 ]; then
    echo -e "${RED}❌ Ошибка пересборки (exit code: $REBUILD_EXIT)${NC}"
    exit 1
fi

# 3. Ожидание завершения сборки
echo ""
echo -e "${YELLOW}⏳ Ожидание завершения сборки (30 сек)...${NC}"
sleep 30

# 4. Логи сборки (последние 50 строк)
echo ""
echo -e "${CYAN}📋 Логи сборки (последние 50 строк):${NC}"
"$AMVERA" logs build --slug "$SLUG" 2>&1 | tail -50

# 5. Логи выполнения (последние 30 строк)
echo ""
echo -e "${CYAN}📋 Логи выполнения (последние 30 строк):${NC}"
"$AMVERA" logs run --slug "$SLUG" 2>&1 | tail -30

# 6. Финальная проверка
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ Деплой завершён${NC}"
echo -e "${GREEN}  Проверьте логи на наличие ошибок${NC}"
echo -e "${GREEN}============================================${NC}"
