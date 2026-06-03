#!/usr/bin/env python3
"""
Загрузка app.py на PythonAnywhere через Web Console (Bash)
Метод: Использование curl для загрузки файла с GitHub Gist или другого хостинга
"""

import os
import sys
import requests

# Конфигурация
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'
REMOTE_PATH = '/home/hyperstls/app.py'
BACKUP_PATH = '/home/hyperstls/app.py.backup.20260603'

# Уникальный идентификатор для загрузки файла
# Файл будет доступен через URL вида: https://example.com/app_upload_<id>.py
UPLOAD_SERVER_URL = "http://localhost:8080/upload"  # Это будет запущено локально

def read_local_file():
    """Прочитать локальный файл"""
    try:
        with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать файл: {e}")
        return None

def start_upload_server():
    """Запустить локальный сервер для загрузки"""
    print("[INFO] Запуск локального сервера загрузки...")
    
    import http.server
    import socketserver
    
    PORT = 8080
    Handler = http.server.SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"[OK] Сервер запущен на порту {PORT}")
        print(f"[INFO] Файл будет доступен по: http://localhost:{PORT}/")
        print(f"[INFO] Откройте этот URL на PythonAnywhere и загрузите файл")
        httpd.serve_forever()

def main():
    print("=" * 60)
    print("ЗАГРУЗКА НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    print()
    
    print("=" * 60)
    print("МАНУАЛЬНАЯ ЗАГРУЗКА (РЕКОМЕНДУЕТСЯ)")
    print("=" * 60)
    print()
    print("Способ 1: Через веб-интерфейс PythonAnywhere")
    print("  1. Открыть: https://www.pythonanywhere.com/")
    print("  2. Войти как: Hyperstls")
    print("  3. Вкладка: Files -> /home/hyperstls/app.py -> Edit")
    print("  4. Выделить весь код (Ctrl+A), удалить (Delete)")
    print("  5. Вставить обновлённый код (Ctrl+V)")
    print("  6. Нажать: Save")
    print("  7. Вкладка: Web -> Reload")
    print()
    
    print("Способ 2: Через Bash консоль")
    print("  1. Открыть Bash console на PythonAnywhere")
    print("  2. Выполнить:")
    print("     cd /home/hyperstls")
    print("     cp app.py app.py.backup.20260603")
    print("     # Затем вставить код через heredoc:")
    print("     cat > app.py << 'ENDOFFILE'")
    print("     [вставить код здесь]")
    print("     ENDOFFILE")
    print()
    
    print("Способ 3: Через SFTP (FileZilla, WinSCP)")
    print("  1. Подключиться к: hyperstls.pythonanywhere.com")
    print("  2. Загрузить: app.py в /home/hyperstls/")
    print()
    
    print("=" * 60)
    print("ПРОВЕРКА ПОСЛЕ ЗАГРУЗКИ")
    print("=" * 60)
    print()
    print("1. Открыть: https://hyperstls.pythonanywhere.com/")
    print("2. Войти как: test_employer_final@test.com")
    print("3. Перейти в: /create-job")
    print("4. Заполнить форму и отправить")
    print("5. Ожидаем: 'Задание опубликовано' (не 500)")
    print()
    
    return True

if __name__ == "__main__":
    main()
