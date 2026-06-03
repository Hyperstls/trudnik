#!/usr/bin/env python3
"""
Скрипт для прямого обновления app.py на PythonAnywhere
Через SSH/SFTP (если настроено) или через web-консоль
"""

import os
import sys

# Конфигурация PythonAnywhere
PYTHONANYWHERE_CONFIG = {
    'hostname': 'hyperstls.pythonanywhere.com',
    'username': 'hyperstls',
    'remote_path': '/home/hyperstls/app.py',
    'backup_path': '/home/hyperstls/app.py.backup.20260603',
    'local_path': 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py',
}

def read_local_file():
    """Прочитать локальный файл app.py"""
    try:
        with open(PYTHONANYWHERE_CONFIG['local_path'], 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"❌ Ошибка чтения локального файла: {e}")
        sys.exit(1)

def check_file_exists():
    """Проверить наличие локального файла"""
    if not os.path.exists(PYTHONANYWHERE_CONFIG['local_path']):
        print(f"❌ Файл не найден: {PYTHONANYWHERE_CONFIG['local_path']}")
        return False
    return True

def show_summary():
    """Показать краткую сводку"""
    print("=" * 60)
    print("ОБНОВЛЕНИЕ FLASK-ПРИЛОЖЕНИЯ НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    print(f"Локальный файл: {PYTHONANYWHERE_CONFIG['local_path']}")
    print(f"Удалённый файл: {PYTHONANYWHERE_CONFIG['remote_path']}")
    print(f"Резервная копия: {PYTHONANYWHERE_CONFIG['backup_path']}")
    print()
    
    if not check_file_exists():
        return False
    
    local_content = read_local_file()
    print(f"✅ Локальный файл найден")
    print(f"✅ Размер: {len(local_content)} символов")
    print(f"✅ Строк: {len(local_content.splitlines())}")
    print()
    
    print("Ключевые изменения:")
    print("  1. Добавлен import traceback")
    print("  2. Улучшена функция supabase_request() с try/except")
    print("  3. Обновлён маршрут /create-job с логированием")
    print()
    
    return True

def show_manual_instructions():
    """Показать ручные инструкции"""
    print("=" * 60)
    print("РУЧНОЕ ОБНОВЛЕНИЕ (Через веб-интерфейс)")
    print("=" * 60)
    print()
    print("1. Открыть: https://www.pythonanywhere.com/")
    print("2. Войти как: hyperstls")
    print("3. Вкладка: Files")
    print("4. Путь: /home/hyperstls/app.py")
    print("5. Нажать: Edit")
    print("6. Выделить весь код (Ctrl+A)")
    print("7. Удалить (Delete)")
    print("8. Вставить новый код (Ctrl+V)")
    print("9. Нажать: Save")
    print()
    print("10. Перезапустить: Вкладка Web → кнопка Reload")
    print()
    print("Готово!")
    print()

def show_alternative_methods():
    """Показать альтернативные методы"""
    print("=" * 60)
    print("АЛЬТЕРНАТИВНЫЕ МЕТОДЫ ОБНОВЛЕНИЯ")
    print("=" * 60)
    print()
    
    print("МЕТОД 1: SCP (если настроен SSH)")
    print("  Команда:")
    print("  scp C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py hyperstls@pythonanywhere.com:/home/hyperstls/app.py")
    print()
    
    print("МЕТОД 2: SFTP (FileZilla, WinSCP)")
    print("  1. Подключиться к hyperstls.pythonanywhere.com")
    print("  2. Найти файл: /home/hyperstls/app.py")
    print("  3. Загрузить обновлённую версию")
    print()
    
    print("МЕТОД 3: Git (если используется репозиторий)")
    print("  1. Закоммитить изменения: git commit -am 'Fix create-job route'")
    print("  2. Отправить: git push")
    print("  3. На PythonAnywhere: git pull")
    print()
    
    print("МЕТОД 4: PythonAnywhere Web Console")
    print("  1. Вкладка: Bash console")
    print("  2. Команда: nano /home/hyperstls/app.py")
    print("  3. Редактировать и сохранить (Ctrl+O, Ctrl+X)")
    print()

def main():
    """Главная функция"""
    print()
    
    if not show_summary():
        return
    
    print()
    show_manual_instructions()
    show_alternative_methods()
    
    print("=" * 60)
    print("ПРЕДОСТЕРЕЖЕНИЯ")
    print("=" * 60)
    print()
    print("⚠️  Создайте резервную копию перед обновлением!")
    print("⚠️  Проверьте синтаксис перед сохранением!")
    print("⚠️  Перезапустите приложение после обновления!")
    print()
    
    print("Удачи! 🚀")
    print()

if __name__ == "__main__":
    main()
