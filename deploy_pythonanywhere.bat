#!/bin/bash

# Скрипт для деплоя на PythonAnywhere
# Использование: ./deploy_pythonanywhere.bat

@echo off
echo === Деплой на PythonAnywhere ===
echo.

echo 1. Проверка статуса репозитория...
git status

echo.
echo 2. Добавление изменений...
git add .

echo.
echo 3. Коммит изменений...
set /p commit_msg="Введите сообщение коммита (по умолчанию: deploy update): "
if "%commit_msg%"=="" set commit_msg=deploy update
git commit -m "%commit_msg%"

echo.
echo 4. Отправка на GitHub...
git push

echo.
echo === Готово! Теперь выполните на PythonAnywhere: ===
echo cd ~/mysite
echo git pull
echo touch /var/www/hyperstls_pythonanywhere_com_wsgi.py

pause
