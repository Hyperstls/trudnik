#!/bin/bash

# Скрипт для деплоя на PythonAnywhere
# Использование: ./deploy_pythonanywhere.sh

echo "=== Деплой на PythonAnywhere ==="
echo ""

# Шаг 1: Проверка статуса git
echo "1. Проверка статуса репозитория..."
git status

# Шаг 2: Добавление всех изменений
echo ""
echo "2. Добавление изменений..."
git add .

# Шаг 3: Коммит
echo ""
echo "3. Коммит изменений..."
git commit -m "deploy: $(date '+%Y-%m-%d %H:%M:%S')"

# Шаг 4: Отправка на GitHub
echo ""
echo "4. Отправка на GitHub..."
git push

echo ""
echo "=== Готово! Теперь выполните на PythonAnywhere: ==="
echo "cd ~/mysite"
echo "git pull"
echo "touch /var/www/hyperstls_pythonanywhere_com_wsgi.py"
