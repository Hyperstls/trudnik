#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Инструкция: Как выполнить git pull на PythonAnywhere через веб-интерфейс

ПРОСТАЯ ИНСТРУКЦИЯ (5 минут):

1. Откройте https://www.pythonanywhere.com/
2. Войдите как Hyperstls
3. Нажмите на иконку консоли (компьютер с терминалом) или перейдите в консоли
4. В открывшейся консоли выполните следующие команды:
   
   cd ~/mysite
   git config --global user.email "hyperstls@inbox.ru"
   git config --global user.name "Hyperstls"
   git config pull.rebase false
   git pull
   touch app.py.wsgi

5. Нажмите Enter после каждой команды
6. Готово! Изменения загружены.

АЛТЕРНАТИВНЫЙ СПОСОБ (если консоль не открывается):

1. Откройте https://www.pythonanywhere.com/
2. Войдите как Hyperstls
3. Перейдите во вкладку "Files"
4. Откройте файл: /home/hyperstls/mysite/app.py
5. Нажмите "Edit"
6. Скопируйте весь код из локального файла app.py
7. Вставьте его в веб-редактор
8. Нажмите "Save"
9. Перейдите во вкладку "Web" и нажмите "Reload"

КОМАНДЫ ДЛЯ КОПИРОВАНИЯ:

cd ~/mysite
git config --global user.email "hyperstls@inbox.ru"
git config --global user.name "Hyperstls"
git config pull.rebase false
git pull
touch app.py.wsgi

Просто вставьте их по одной в консоль PythonAnywhere и нажимайте Enter.
