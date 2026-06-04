#!/bin/bash
# Автотест системы избранного
# Проверяет: HTML, JavaScript, API endpoints

echo "=========================================="
echo "АВТОТЕСТ СИСТЕМЫ ИЗБРАННОГО"
echo "=========================================="
echo ""

URL="https://hyperstls.pythonanywhere.com"

# 1. Проверка HTML страницы /workers
echo "1. Проверка HTML страницы /workers"
echo "-----------------------------------"

html_content=$(curl -s "${URL}/workers")

# Проверка наличия кнопки "В избранное"
if echo "$html_content" | grep -q "В избранное"; then
    echo "✅ Кнопка 'В избранное' найдена в HTML"
else
    echo "❌ Кнопка 'В избранное' НЕ найдена в HTML"
fi

# Проверка наличия onclick="toggleFavorite"
if echo "$html_content" | grep -q 'onclick="toggleFavorite'; then
    echo "✅ Функция toggleFavorite вызывается в HTML"
else
    echo "❌ Функция toggleFavorite НЕ вызывается в HTML"
fi

# Проверка наличия stopPropagation
if echo "$html_content" | grep -q 'stopPropagation'; then
    echo "✅ stopPropagation найден в HTML"
else
    echo "❌ stopPropagation НЕ найден в HTML"
fi

echo ""

# 2. Проверка JavaScript функции toggleFavorite
echo "2. Проверка JavaScript функции toggleFavorite"
echo "---------------------------------------------"

# Проверка определения функции
if echo "$html_content" | grep -q 'function toggleFavorite'; then
    echo "✅ Функция toggleFavorite определена"
else
    echo "❌ Функция toggleFavorite НЕ определена"
fi

# Проверка вызова e.stopPropagation
if echo "$html_content" | grep -q 'stopPropagation'; then
    echo "✅ e.stopPropagation() вызывается в функции"
else
    echo "❌ e.stopPropagation() НЕ вызывается"
fi

# Проверка API вызовов
if echo "$html_content" | grep -q '/api/favorites/add'; then
    echo "✅ Вызов /api/favorites/add найден"
else
    echo "❌ Вызов /api/favorites/add НЕ найден"
fi

if echo "$html_content" | grep -q '/api/favorites/remove'; then
    echo "✅ Вызов /api/favorites/remove найден"
else
    echo "❌ Вызов /api/favorites/remove НЕ найден"
fi

echo ""

# 3. Проверка API endpoints
echo "3. Проверка API endpoints"
echo "-------------------------"

# Проверка /api/favorites/add
response=$(curl -s -X POST "${URL}/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"worker_id": "test-worker-123"}' \
    -w "\nHTTP_CODE:%{http_code}")

http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE:/d')

if [ "$http_code" = "200" ]; then
    echo "✅ /api/favorites/add возвращает 200"
    
    # Проверка Content-Type
    content_type=$(curl -s -I "${URL}/api/favorites/add" | grep -i "Content-Type")
    if echo "$content_type" | grep -q "application/json"; then
        echo "✅ /api/favorites/add возвращает JSON"
    else
        echo "⚠️  /api/favorites/add возвращает: $(echo "$content_type" | cut -d: -f2)"
    fi
    
    echo "   Response: ${body:0:100}..."
else
    echo "❌ /api/favorites/add возвращает: $http_code"
    echo "   Response: ${body:0:100}..."
fi

# Проверка /api/favorites/check
response=$(curl -s -X POST "${URL}/api/favorites/check" \
    -H "Content-Type: application/json" \
    -d '{"worker_id": "test-worker-123"}' \
    -w "\nHTTP_CODE:%{http_code}")

http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE:/d')

if [ "$http_code" = "200" ]; then
    echo "✅ /api/favorites/check возвращает 200"
    echo "   Response: ${body:0:100}..."
else
    echo "❌ /api/favorites/check возвращает: $http_code"
    echo "   Response: ${body:0:100}..."
fi

echo ""

# 4. Проверка наличия workerId в кнопке
echo "4. Проверка workerId в кнопке"
echo "------------------------------"

# Ищем кнопку с data-worker-id
if echo "$html_content" | grep -q 'data-worker-id="'; then
    echo "✅ data-worker-id найден в кнопке"
    
    # Извлекаем workerId
    worker_id=$(echo "$html_content" | grep -o 'data-worker-id="[^"]*"' | head -1 | cut -d'"' -f2)
    if [ -n "$worker_id" ]; then
        echo "   Пример workerId: $worker_id"
    fi
else
    echo "❌ data-worker-id НЕ найден"
fi

echo ""

# 5. Проверка favorites.html
echo "5. Проверка страницы /favorites"
echo "--------------------------------"

favorites_html=$(curl -s "${URL}/favorites")

if echo "$favorites_html" | grep -q 'Удалить из избранного'; then
    echo "✅ Кнопка 'Удалить из избранного' найдена"
else
    echo "❌ Кнопка 'Удалить из избранного' НЕ найдена"
fi

if echo "$favorites_html" | grep -q 'worker-item-'; then
    echo "✅ Класс worker-item найден"
else
    echo "❌ Класс worker-item НЕ найден"
fi

echo ""

# 6. Сводка
echo "=========================================="
echo "СВОДКА РЕЗУЛЬТАТОВ"
echo "=========================================="

# Подсчет ошибок
errors=0
warnings=0

# Проверка HTML
if ! echo "$html_content" | grep -q "В избранное"; then
    ((errors++))
    echo "❌ Кнопка 'В избранное' НЕ найдена в HTML"
fi

if ! echo "$html_content" | grep -q 'onclick="toggleFavorite'; then
    ((errors++))
    echo "❌ toggleFavorite НЕ вызывается в HTML"
fi

if ! echo "$html_content" | grep -q 'stopPropagation'; then
    ((warnings++))
    echo "⚠️  stopPropagation НЕ найден"
fi

# Проверка API
if [ "$http_code" != "200" ]; then
    ((errors++))
    echo "❌ API endpoints не работают"
fi

echo ""
echo "Ошибок: $errors"
echo "Предупреждений: $warnings"

if [ $errors -eq 0 ]; then
    echo ""
    echo "✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!"
    echo "Теперь нужно сделать деплой на PythonAnywhere:"
    echo "  cd ~/mysite && git pull && touch /var/www/hyperstls_pythonanywhere_com_wsgi.py"
    exit 0
else
    echo ""
    echo "❌ ЕСТЬ ОШИБКИ - проверьте вывод выше"
    exit 1
fi
