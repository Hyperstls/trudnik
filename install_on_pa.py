#!/usr/bin/env python3
"""
СКРИПТ ДЛЯ ЗАГРУЗКИ НА PYTHONANYWHERE
Скопируйте этот код и выполните его в Bash console на PythonAnywhere
"""

import os
import sys
import requests

def download_and_save():
    """Скачать файл и сохранить"""
    
    # URL для загрузки (замените на реальный URL вашего файла)
    # Можно загрузить файл на GitHub, Gist, или другой хостинг
    file_url = "https://raw.githubusercontent.com/USERNAME/REPO/main/app.py"
    
    print("Загрузка app.py...")
    
    try:
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        
        content = response.text
        
        # Сохранить файл
        with open('/home/hyperstls/app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Файл сохранён. Размер: {len(content)} байт")
        return True
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def main():
    print("=" * 60)
    print("ЗАГРУЗКА app.py НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    # Проверить метод загрузки
    print("Выберите метод загрузки:")
    print("1. Скачать с GitHub/Gist")
    print("2. Вставить код вручную")
    print()
    
    method = input("Выберите (1 или 2): ").strip()
    
    if method == '1':
        # Скачать с GitHub
        print()
        file_url = input("Введите URL файла (GitHub/raw): ").strip()
        
        if file_url:
            # Заменить URL для raw content
            if 'github.com' in file_url and not 'raw.githubusercontent' in file_url:
                # Преобразовать github.com в raw.githubusercontent.com
                parts = file_url.replace('https://', '').split('/')
                if len(parts) >= 5:
                    user = parts[0]
                    repo = parts[1]
                    branch = parts[3] if len(parts) > 3 else 'main'
                    path = '/'.join(parts[4:])
                    file_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
            
            print(f"Загрузка с: {file_url}")
            
            try:
                response = requests.get(file_url, timeout=30)
                response.raise_for_status()
                
                content = response.text
                
                # Создать резервную копию
                backup_path = '/home/hyperstls/app.py.backup.20260603'
                if os.path.exists('/home/hyperstls/app.py'):
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        old_content = f.read()
                    print(f"Резервная копия создана: {backup_path}")
                
                # Сохранить файл
                with open('/home/hyperstls/app.py', 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"Файл сохранён. Размер: {len(content)} байт")
                print("✓ Готово!")
                
                # Перезапустить
                print()
                print("Теперь перезапустите приложение:")
                print("cd /home/hyperstls && touch app.py.wsgi")
                
            except Exception as e:
                print(f"Ошибка: {e}")
                return False
    
    elif method == '2':
        # Вставить вручную
        print()
        print("Введите код (закончить ввод: пустая строка)")
        print()
        
        lines = []
        while True:
            try:
                line = input()
                if not line:
                    break
                lines.append(line)
            except EOFError:
                break
        
        content = '\n'.join(lines)
        
        # Создать резервную копию
        backup_path = '/home/hyperstls/app.py.backup.20260603'
        if os.path.exists('/home/hyperstls/app.py'):
            with open(backup_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            print(f"Резервная копия создана: {backup_path}")
        
        # Сохранить файл
        with open('/home/hyperstls/app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Файл сохранён. Размер: {len(content)} байт")
        print("✓ Готово!")
        
    else:
        print("Неверный выбор")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    
    if success:
        print()
        print("=" * 60)
        print("ПЕРЕЗАПУСК ПРИЛОЖЕНИЯ")
        print("=" * 60)
        print()
        print("Выполните в bash console:")
        print("  cd /home/hyperstls")
        print("  touch app.py.wsgi")
        print()
        print("ИЛИ перейдите в Web и нажмите Reload")
