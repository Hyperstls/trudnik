"""
Super Agent для "Трудник" - автоматическое тестирование и исправление
"""

import sys
import json
import os
import subprocess
import time
from pathlib import Path

# Добавляем путь к venv
venv_path = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
if venv_path.exists():
    python_cmd = str(venv_path)
else:
    python_cmd = "python"

def run_command(cmd, timeout=60):
    """Запустить команду и вернуть результат"""
    print(f"🚀 Выполняю: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            cwd=str(Path(__file__).parent)
        )
        print(f"✅ Выполнено (код: {result.returncode})")
        if result.stdout:
            print(f"📊 Вывод:\n{result.stdout[:2000]}")
        if result.stderr and result.returncode != 0:
            print(f"⚠️  Ошибки:\n{result.stderr[:1000]}")
        return result
    except subprocess.TimeoutExpired:
        print(f"❌ Превышено время ожидания {timeout} сек")
        return None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def update_role_user():
    """Обновить роль пользователя через PythonAnywhere"""
    print("\n" + "="*60)
    print("🔄 ОБНОВЛЕНИЕ РОЛИ ПОЛЬЗОВАТЕЛЯ")
    print("="*60)
    
    # Проверяем, есть ли SERVICE_KEY в .env файле
    print("\n1. Проверка SERVICE_KEY...")
    
    # Создаем скрипт для проверки
    check_script = Path(__file__).parent / "check_service_key_pyanywhere.py"
    check_script.write_text('''
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'NOT SET')
print(f"SERVICE_KEY: {key[:20] if key != 'NOT SET' else 'NOT SET'}...")
if key and key != 'NOT SET':
    print("SERVICE_KEY найден!")
else:
    print("SERVICE_KEY не найден!")
''')
    
    print("🤖 Запрос к PythonAnywhere:")
    print("   1. Добавьте SERVICE_KEY в .env файл на PythonAnywhere")
    print("   2. Запустите: python check_service_key_pyanywhere.py")
    print("   3. Если SERVICE_KEY есть, запустите: python disable_rls_and_update.py")
    
    # Альтернатива: вручную через Supabase Dashboard
    print("\n2. Альтернативный способ (вручную):")
    print("   https://supabase.com/dashboard/project/***REMOVED***/table-editor")
    print("   - Найдите таблицу 'profiles'")
    print("   - Три точки → Table Settings → Row Level Security → Отключите")
    print("   - Найдите пользователя c6291021-7741-4a10-b68c-b1c7ec002442")
    print("   - Три точки → Edit Row → Измените role на 'employer'")
    print("   - Save")

def disable_rls_manual():
    """Инструкции по отключению RLS вручную"""
    print("\n" + "="*60)
    print("⚠️  ОТКЛЮЧЕНИЕ RLS В РУЧНОМ РЕЖИМЕ")
    print("="*60)
    print("\nИнструкция:")
    print("1. Перейдите в Supabase Dashboard:")
    print("   https://supabase.com/dashboard/project/***REMOVED***/table-editor")
    print("2. Найдите таблицу 'profiles'")
    print("3. Нажмите на три точки (...) в правом верхнем углу")
    print("4. Выберите 'Table Settings'")
    print("5. Перейдите на вкладку 'Row Level Security (RLS)'")
    print("6. Отключите 'Row Level Security'")
    print("7. Нажмите 'Save'")
    print("\n⚠️  ВАЖНО: Не забудьте включить RLS обратно после тестирования!")

def test_employer_login():
    """Протестировать вход работодателя"""
    print("\n" + "="*60)
    print("🔍 ТЕСТИРОВАНИЕ ВХОДА РАБОТОДАТЕЛЯ")
    print("="*60)
    
    cmd = f'{python_cmd} my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"'
    run_command(cmd)

def main():
    print("\n" + "="*60)
    print("SUPER AGENT для 'Трудник'")
    print("="*60)
    print("\nДоступные команды:")
    print("1. update_role      - Обновить роль пользователя")
    print("2. disable_rls      - Инструкции по отключению RLS")
    print("3. test_login       - Протестировать вход работодателя")
    print("4. full_test        - Полный цикл тестирования")
    
    if len(sys.argv) < 2:
        print("\nИспользование: python super_agent.py <команда>")
        return
    
    command = sys.argv[1].lower()
    
    if command == "update_role":
        update_role_user()
    elif command == "disable_rls":
        disable_rls_manual()
    elif command == "test_login":
        test_employer_login()
    elif command == "full_test":
        update_role_user()
        input("\n✅ Нажмите Enter после обновления роли...")
        test_employer_login()
    else:
        print(f"❌ Неизвестная команда: {command}")

if __name__ == "__main__":
    main()
