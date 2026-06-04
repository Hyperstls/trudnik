#!/bin/bash
# Скрипт для тестирования системы избранного через агентов

echo "=== Тестирование системы избранного ==="
echo ""

# Настройки
URL="https://hyperstls.pythonanywhere.com"
API_CHECK="${URL}/api/favorites/check"
API_ADD="${URL}/api/favorites/add"
API_REMOVE="${URL}/api/favorites/remove"

# Тестовые данные (используем test worker id)
WORKER_ID="test-worker-id-123"
USER_ID="test-user-id-456"

echo "1. Проверка API /api/favorites/check"
echo "   Отправка POST запроса на ${API_CHECK}"
curl -s -X POST "${API_CHECK}" \
    -H "Content-Type: application/json" \
    -d "{\"worker_id\": \"${WORKER_ID}\"}" \
    -H "Cookie: session=test" 2>&1 | head -20

echo ""
echo "2. Проверка API /api/favorites/add"
echo "   Отправка POST запроса на ${API_ADD}"
curl -s -X POST "${API_ADD}" \
    -H "Content-Type: application/json" \
    -d "{\"worker_id\": \"${WORKER_ID}\"}" \
    -H "Cookie: session=test" 2>&1 | head -20

echo ""
echo "3. Проверка API /api/favorites/remove"
echo "   Отправка POST запроса на ${API_REMOVE}"
curl -s -X POST "${API_REMOVE}" \
    -H "Content-Type: application/json" \
    -d "{\"worker_id\": \"${WORKER_ID}\"}" \
    -H "Cookie: session=test" 2>&1 | head -20

echo ""
echo "4. Проверка главной страницы"
curl -s "${URL}/" | grep -o "Трудники" || echo "Кнопка 'Трудники' не найдена"

echo ""
echo "5. Проверка страницы трудников"
curl -s "${URL}/workers" | grep -o "В избранное" || echo "Кнопка 'В избранное' не найдена"

echo ""
echo "=== Тестирование завершено ==="
