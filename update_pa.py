# Скрипт для обновления app.py на PythonAnywhere
# Выполнять после локального обновления

import subprocess
import sys

def update_pythonanywhere():
    """Обновляет app.py на PythonAnywhere через scp"""
    print("=== Обновление app.py на PythonAnywhere ===")
    
    local_file = "C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py"
    remote_file = "hyperstls@pythonanywhere.com:/home/hyperstls/app.py"
    
    try:
        # Используем scp для копирования файла
        cmd = ["scp", local_file, remote_file]
        print(f"Команда: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Файл успешно скопирован на PythonAnywhere")
            print("\nТеперь нужно перезапустить веб-приложение:")
            print("1. Перейти на https://www.pythonanywhere.com/")
            print("2. Войти в аккаунт hyperstls")
            print("3. Перейти во вкладку Web")
            print("4. Нажать кнопку 'Reload' для перезапуска приложения")
            print("\nИЛИ выполнить через Bash console:")
            print("cd /home/hyperstls && source .venv/bin/activate && flask run")
        else:
            print("❌ Ошибка при копировании файла")
            print(f"STDERR: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ Команда scp не найдена. Убедитесь, что установлен SSH клиент.")
        print("   Или используйте другой метод загрузки файла (веб-консоль, SFTP)")
    except subprocess.TimeoutExpired:
        print("❌ Таймаут при копировании файла")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    update_pythonanywhere()
