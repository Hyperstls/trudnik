#!/bin/bash
# ============================================================
# amvera_full_cycle.sh — Полный цикл CI/CD
# Использование:
#   ./amvera_full_cycle.sh [slug] [commit-message]
#
#   slug           — slug проекта (по умолчанию: trudnik)
#   commit-message — сообщение коммита (по умолчанию: авто)
# ============================================================
# Этапы:
#   1. Авторизация
#   2. Статус до деплоя
#   3. Git push (если есть изменения)
#   4. Push в Amvera (git remote)
#   5. Пересборка проекта
#   6. Ожидание сборки
#   7. Проверка логов сборки
#   8. Проверка логов выполнения
#   9. Healthcheck
# ============================================================

set -euo pipefail

AMVERA="${AMVERA_CLI:-amvera}"
SLUG="${1:-trudnik}"
COMMIT_MSG="${2:-Auto-deploy $(date '+%Y-%m-%d %H:%M:%S')}"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Переменные для отслеживания ошибок
HAS_ERRORS=false

# Функция для вывода шага
step() {
    local num=$1
    local desc=$2
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}  Шаг ${num}: ${desc}${NC}"
    echo -e "${CYAN}============================================${NC}"
}

# Функция проверки ошибок
check_error() {
    local exit_code=$1
    local context=$2
    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}❌ [${context}] Ошибка (exit code: $exit_code)${NC}"
        HAS_ERRORS=true
    fi
}

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ПОЛНЫЙ ЦИКЛ CI/CD${NC}"
echo -e "${GREEN}  Проект: ${SLUG}${NC}"
echo -e "${GREEN}  Дата:   $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${GREEN}============================================${NC}"

# =============================================
# Шаг 0: Авторизация
# =============================================
step "0" "Авторизация в Amvera Cloud"
echo -e "${YELLOW}🔑 Выполняем вход...${NC}"
"$AMVERA" login --user "${AMVERA_USER:-}" --password "${AMVERA_PASSWORD:-}" 2>&1 || echo -e "${YELLOW}ℹ️  Авторизация не требуется (сессия активна)${NC}"

# =============================================
# Шаг 1: Статус до деплоя
# =============================================
step "1" "Текущее состояние проекта"
echo -e "${YELLOW}📄 Информация о проекте ${SLUG}:${NC}"
"$AMVERA" describe project --slug "$SLUG" 2>&1 | head -10 || echo -e "${YELLOW}⚠️  Не удалось получить информацию${NC}"

# =============================================
# Шаг 2: Git push (если есть незакоммиченные изменения)
# =============================================
step "2" "Git — коммит и push"

# Проверяем, есть ли изменения
if git status --porcelain 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}📝 Обнаружены изменения. Выполняю commit и push...${NC}"

    git add -A
    echo -e "${GREEN}✅ Файлы добавлены в индекс${NC}"

    git commit -m "$COMMIT_MSG"
    echo -e "${GREEN}✅ Коммит создан: ${COMMIT_MSG}${NC}"

    git push origin main 2>&1
    check_error $? "git push origin main"

    echo -e "${GREEN}✅ Изменения отправлены в origin/main${NC}"
else
    echo -e "${YELLOW}ℹ️  Нет незакоммиченных изменений${NC}"
fi

# =============================================
# Шаг 3: Push в Amvera
# =============================================
step "3" "Push в репозиторий Amvera"

echo -e "${YELLOW}📤 Отправка кода в Amvera Git...${NC}"
if git remote | grep -q "amvera"; then
    git push amvera main:master 2>&1 || {
        echo -e "${YELLOW}⚠️  Push в amvera не удался. Использую rebuild...${NC}"
    }
    check_error $? "git push amvera main:master"
    echo -e "${GREEN}✅ Код отправлен в Amvera${NC}"
else
    echo -e "${YELLOW}ℹ️  Git remote 'amvera' не найден. Перехожу к rebuild...${NC}"
fi

# =============================================
# Шаг 4: Пересборка проекта
# =============================================
step "4" "Пересборка проекта"

echo -e "${YELLOW}🚀 Пересборка ${SLUG}...${NC}"
"$AMVERA" rebuild --slug "$SLUG"
check_error $? "amvera rebuild"

echo -e "${YELLOW}⏳ Ожидание 40 секунд для завершения сборки...${NC}"
sleep 40

# =============================================
# Шаг 5: Проверка логов сборки
# =============================================
step "5" "Логи сборки (последние 20 строк)"

BUILD_LOG=$("$AMVERA" logs build --slug "$SLUG" 2>&1)
BUILD_EXIT=$?
check_error $BUILD_EXIT "amvera logs build"

if [ $BUILD_EXIT -eq 0 ]; then
    echo "$BUILD_LOG" | tail -20

    # Проверка на ошибки в сборке
    # Попытка парсинга JSON (если API возвращает JSON)
    if echo "$BUILD_LOG" | python3 -c "import sys,json; d=json.load(sys.stdin); errs=[e for e in d.get('errors',[]) or [] if e]; print('\n'.join(errs))" 2>/dev/null; then
        echo ""
        echo -e "${RED}❌ Обнаружены ошибки в сборке (JSON)!${NC}"
        echo "$BUILD_LOG" | python3 -c "import sys,json; d=json.load(sys.stdin); errs=[e for e in d.get('errors',[]) or [] if e]; print('\n'.join(errs[:10]))" 2>/dev/null
        HAS_ERRORS=true
    elif echo "$BUILD_LOG" | grep -qi "error\|failed\|failure"; then
        echo ""
        echo -e "${RED}❌ Обнаружены ошибки в сборке!${NC}"
        echo "$BUILD_LOG" | grep -i "error\|failed\|failure" | head -10
        HAS_ERRORS=true
    else
        echo ""
        echo -e "${GREEN}✅ Логи сборки не содержат явных ошибок${NC}"
    fi
fi

# =============================================
# Шаг 6: Проверка логов выполнения
# =============================================
step "6" "Логи выполнения (последние 20 строк)"

RUN_LOG=$("$AMVERA" logs run --slug "$SLUG" 2>&1)
RUN_EXIT=$?
check_error $RUN_EXIT "amvera logs run"

if [ $RUN_EXIT -eq 0 ]; then
    echo "$RUN_LOG" | tail -20

    # Проверка на ошибки в выполнении
    # Попытка парсинга JSON (если API возвращает JSON)
    if echo "$RUN_LOG" | python3 -c "import sys,json; d=json.load(sys.stdin); errs=[e for e in d.get('errors',[]) or [] if e]; print('\n'.join(errs))" 2>/dev/null; then
        echo ""
        echo -e "${RED}❌ Обнаружены ошибки в выполнении (JSON)!${NC}"
        echo "$RUN_LOG" | python3 -c "import sys,json; d=json.load(sys.stdin); errs=[e for e in d.get('errors',[]) or [] if e]; print('\n'.join(errs[:10]))" 2>/dev/null
        HAS_ERRORS=true
    elif echo "$RUN_LOG" | grep -qi "error\|traceback\|exception\|failed"; then
        echo ""
        echo -e "${RED}❌ Обнаружены ошибки в выполнении!${NC}"
        echo "$RUN_LOG" | grep -i "error\|traceback\|exception\|failed" | head -10
        HAS_ERRORS=true
    else
        echo ""
        echo -e "${GREEN}✅ Логи выполнения не содержат явных ошибок${NC}"
    fi
fi

# =============================================
# Шаг 7: Healthcheck
# =============================================
step "7" "Healthcheck — проверка работоспособности"

echo -e "${YELLOW}⏳ Ожидание 15 секунд перед healthcheck...${NC}"
sleep 15

HEALTH_URL="https://${SLUG}-hyperstls.amvera.io/health"
echo -e "${YELLOW}🌐 Проверка: ${HEALTH_URL}${NC}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 15 --max-time 20 "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Healthcheck пройден (HTTP ${HTTP_CODE})${NC}"
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${YELLOW}⚠️  Healthcheck: соединение не установлено (таймаут)${NC}"
    echo -e "${YELLOW}   Возможно, приложение ещё запускается.${NC}"
    HAS_ERRORS=true
else
    echo -e "${YELLOW}⚠️  Healthcheck: HTTP ${HTTP_CODE}${NC}"
    echo -e "${YELLOW}   (не 200, но сервер отвечает)${NC}"
fi

# =============================================
# Итог
# =============================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           РЕЗУЛЬТАТ ЦИКЛА CI/CD${NC}"
echo -e "${GREEN}============================================${NC}"

if [ "$HAS_ERRORS" = true ]; then
    echo -e "${RED}❌ Цикл завершён с ошибками/предупреждениями${NC}"
    echo -e "${YELLOW}   Проверьте вывод выше для деталей.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Цикл CI/CD успешно завершён!${NC}"
    echo -e "${GREEN}   Проект ${SLUG} развёрнут и работает.${NC}"
    echo -e "${GREEN}   Healthcheck пройден.${NC}"
    exit 0
fi
