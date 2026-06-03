#!/usr/bin/env python3
"""
Скрипт для отправки app.py на PythonAnywhere
Через paramiko (SSH) или requests (web API)
"""

import os
import sys

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    print("[WARNING] paramiko не установлен. Попробуем другой метод.")

# Конфигурация
PYTHONANYWHERE_CONFIG = {
    'hostname': 'ssh.pythonanywhere.com',
    'port': 22,
    'username': 'hyperstls',
    'password': None,  # Указать пароль или использовать ключ
    'remote_path': '/home/hyperstls/app.py',
    'local_path': 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py',
}

def send_via_paramiko():
    """Отправить файл через SSH/SFTP"""
    if not HAS_PARAMIKO:
        print("[ERROR] paramiko не установлен")
        return False
    
    print("[INFO] Подключение к PythonAnywhere...")
    
    try:
        # Создать SSH клиент
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Подключиться
        ssh.connect(
            PYTHONANYWARE_CONFIG['hostname'],
            port=PYTHONANYWHERE_CONFIG['port'],
            username=PYTHONANYWHERE_CONFIG['username'],
            password=PYTHONANYWHERE_CONFIG['password'],
            timeout=30
        )
        
        print("[OK] Подключение успешно!")
        
        # Открыть SFTP сессию
        sftp = ssh.open_sftp()
        
        # Отправить файл
        print(f"[INFO] Отправка файла: {PYTHONANYWHERE_CONFIG['local_path']}")
        print(f"[INFO] На удалённый путь: {PYTHONANYWHERE_CONFIG['remote_path']}")
        
        sftp.put(
            PYTHONANYWHERE_CONFIG['local_path'],
            PYTHONANYWHERE_CONFIG['remote_path']
        )
        
        print("[OK] Файл успешно отправлен!")
        
        # Закрыть соединения
        sftp.close()
        ssh.close()
        
        print("\n[SUCCESS] Файл отправлен!")
        print("\nТеперь перезапустите приложение:")
        print("1. Открыть: https://www.pythonanywhere.com/")
        print("2. Вкладка: Web")
        print("3. Нажать: Reload")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка при отправке: {e}")
        return False

def check_local_file():
    """Проверить локальный файл"""
    local_path = PYTHONANYWHERE_CONFIG['local_path']
    if not os.path.exists(local_path):
        print(f"[ERROR] Локальный файл не найден: {local_path}")
        return False
    
    size = os.path.getsize(local_path)
    print(f"[OK] Локальный файл найден: {size} bytes")
    return True

def main():
    """Главная функция"""
    print("=" * 60)
    print("ОТПРАВКА app.py НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    # Проверить локальный файл
    if not check_local_file():
        return False
    
    # Попытаться отправить через SSH
    if HAS_PARAMIKO:
        print("[INFO] Попытка отправки через SSH/SFTP...")
        success = send_via_paramiko()
        if success:
            return True
    else:
        print("[INFO] paramiko не установлен, пропускаем SSH")
    
    print()
    print("=" * 60)
    print("АЛЬТЕРНАТИВНЫЕ СПОСОБЫ")
    print("=" * 60)
    print()
    print("Способ 1: Через веб-интерфейс (РЕКОМЕНДУЕТСЯ)")
    print("  - Открыть: https://www.pythonanywhere.com/")
    print("  - Files → /home/hyperstls/app.py → Edit")
    print("  - Вставить код и Save")
    print("  - Web → Reload")
    print()
    print("Способ 2: Через SFTP клиент (FileZilla, WinSCP)")
    print("  - Подключиться к hyperstls.pythonanywhere.com")
    print("  - Загрузить обновлённый app.py")
    print()
    print("Способ 3: Через Git")
    print("  - git commit -am 'Fix create-job route'")
    print("  - git push")
    print("  - git pull на PythonAnywhere")
    print()
    
    return False

if __name__ == "__main__":
    main()
