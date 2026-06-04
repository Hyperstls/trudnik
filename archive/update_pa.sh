#!/bin/bash
# Скрипт для обновления и перезапуска приложения на PythonAnywhere

cd /home/Hyperstls/mysite
echo "Обновление из репозитория..."
git pull origin main

echo "Перезапуск WSGI..."
touch /var/www/hyperstls_pythonanywhere_com_wsgi.py

echo "Готово! Приложение обновлено и перезапущено."
