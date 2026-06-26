#!/bin/bash
# ============================================================
# amvera_monitor.sh — Мониторинг состояния проекта Amvera
# Использование: ./amvera_monitor.sh [slug]
#   slug — slug проекта (по умолчанию: trudnik)
# ============================================================
# Показывает: статус всех сервисов, тариф, баланс, логи
# ============================================================

set -euo pipefail

AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"
SLUG="${1:-trudnik}"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  МОНИТОРИНГ СОСТОЯНИЯ${NC}"
echo -e "${CYAN}  Проект: ${SLUG}${NC}"
echo -e "${CYAN}  Дата:   $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}============================================${NC}"

# 1. Авторизация (на случай, если сессия истекла)
echo ""
echo -e "${YELLOW}🔑 Авторизация...${NC}"
"$AMVERA" login --user Hyperstls --password "Step@1986" 2>&1 || true

# 2. Информация о пользователе
echo ""
echo -e "${YELLOW}👤 Текущий пользователь:${NC}"
"$AMVERA" whoami 2>&1 || echo -e "${RED}❌ Не удалось получить информацию о пользователе${NC}"

# 3. Баланс
echo ""
echo -e "${YELLOW}💰 Баланс:${NC}"
"$AMVERA" balance 2>&1 || echo -e "${RED}❌ Не удалось получить баланс${NC}"

# 4. Регион
echo ""
echo -e "${YELLOW}🌍 Регион:${NC}"
"$AMVERA" region 2>&1 || echo -e "${RED}❌ Не удалось получить регион${NC}"

# 5. Все сервисы проекта
echo ""
echo -e "${YELLOW}📦 Все сервисы:${NC}"
"$AMVERA" get 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Ошибка получения списка сервисов${NC}"
fi

# 6. Детальная информация о проекте
echo ""
echo -e "${YELLOW}📄 Детальная информация о проекте ${SLUG}:${NC}"
"$AMVERA" describe project --slug "$SLUG" 2>&1 | head -30
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Ошибка получения информации о проекте${NC}"
fi

# 7. Тариф
echo ""
echo -e "${YELLOW}💳 Тариф проекта ${SLUG}:${NC}"
"$AMVERA" tariff --slug "$SLUG" 2>&1 || echo -e "${RED}❌ Не удалось получить информацию о тарифе${NC}"

# 8. Домены
echo ""
echo -e "${YELLOW}🌐 Домены:${NC}"
"$AMVERA" domain --slug "$SLUG" 2>&1 || echo -e "${RED}❌ Не удалось получить список доменов${NC}"

# 9. Логи выполнения (последние 20 строк)
echo ""
echo -e "${YELLOW}📋 Последние логи выполнения (20 строк):${NC}"
"$AMVERA" logs run --slug "$SLUG" 2>&1 | tail -20
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Не удалось получить логи выполнения${NC}"
fi

# 10. Статус PostgreSQL
echo ""
echo -e "${YELLOW}🗄️  Статус PostgreSQL:${NC}"
"$AMVERA" describe postgresql --slug "${SLUG}-db" 2>&1 | head -15 || echo -e "${RED}❌ Не удалось получить информацию о PostgreSQL${NC}"

# 11. Итоговая сводка
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ Мониторинг завершён${NC}"
echo -e "${GREEN}  Проверьте статусы всех сервисов выше${NC}"
echo -e "${GREEN}============================================${NC}"
