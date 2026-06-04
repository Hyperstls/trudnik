#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Выполнение команд на PythonAnywhere через SSH
"""

import socket
import sys

# Попробуем подключиться к PythonAnywhere через SSH
HOST = "hyperstls.pythonanywhere.com"
PORT = 22
USERNAME = "hyperstls"

print("=== Подключение к PythonAnywhere ===\n")
print(f"Хост: {HOST}")
print(f"Порт: {PORT}")
print(f"Пользователь: {USERNAME}")

# Попробуем подключиться
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((HOST, PORT))
    print("\n[OK] Подключение к SSH-серверу успешно!")
    sock.close()
    
    print("\nТеперь выполните эти команды в веб-консоли PythonAnywhere:")
    print("  1. Откройте https://www.pythonanywhere.com/consoles/")
    print("  2. Выполните:")
    print("     cd ~/mysite")
    print("     git pull")
    print("     touch app.py.wsgi")
    
except socket.timeout:
    print("\n[ERR] Время ожидания подключения истекло")
except socket.error as e:
    print(f"\n[ERR] Ошибка подключения: {e}")
except Exception as e:
    print(f"\n[ERR] Неизвестная ошибка: {e}")

print("\n=== Альтернативный способ ===")
print("Можно также использовать SFTP для загрузки файлов:")
print("  1. Подключитесь к hyperstls.pythonanywhere.com через SFTP")
print("  2. Загрузите файл app.py в ~/mysite/")
print("  3. Выполните: touch app.py.wsgi")
