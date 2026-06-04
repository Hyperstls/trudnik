#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Деплой через SFTP
"""

import paramiko
import os

# Настройки подключения
HOSTNAME = "hyperstls.pythonanywhere.com"
PORT = 22
USERNAME = "hyperstls"
PASSWORD = "Hyperstls2024!"
LOCAL_APP_PATH = "C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py"
REMOTE_APP_PATH = "/home/hyperstls/mysite/app.py"

print("=== Деплой через SFTP ===\n")

# 1. Подключение
print("1. Подключение к PythonAnywhere...")
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOSTNAME, port=PORT, username=USERNAME, password=PASSWORD, timeout=10)
    print("   [OK] Подключено!")
    
    # 2. Копирование файла
    print("\n2. Копирование app.py...")
    sftp = ssh.open_sftp()
    
    # Проверить, что файл существует
    if not os.path.exists(LOCAL_APP_PATH):
        print(f"   [ERR] Файл не найден: {LOCAL_APP_PATH}")
        sftp.close()
        ssh.close()
        exit(1)
    
    sftp.put(LOCAL_APP_PATH, REMOTE_APP_PATH)
    print("   [OK] Файл скопирован!")
    
    # 3. Перезагрузка приложения
    print("\n3. Перезагрузка приложения...")
    stdin, stdout, stderr = ssh.exec_command("touch ~/mysite/app.py.wsgi")
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        print("   [OK] Приложение перезагружено!")
    else:
        print(f"   [ERR] Ошибка перезагрузки: {exit_status}")
        print(stderr.read().decode())
    
    # 4. Проверка
    print("\n4. Проверка файла...")
    stdin, stdout, stderr = ssh.exec_command("ls -la ~/mysite/app.py")
    file_info = stdout.read().decode()
    print(f"   {file_info.strip()}")
    
    sftp.close()
    ssh.close()
    
    print("\n=== Готово! ===")
    print("Теперь проверьте сайт:")
    print("https://hyperstls.pythonanywhere.com")
    print("\nВойдите как test_employer_final@test.com и попробуйте создать задание.")
    
except paramiko.AuthenticationException:
    print("[ERR] Ошибка аутентификации")
    print("Проверьте логин и пароль")
except paramiko.SSHException as e:
    print(f"[ERR] SSH ошибка: {e}")
except Exception as e:
    print(f"[ERR] Ошибка: {e}")
    import traceback
    traceback.print_exc()
