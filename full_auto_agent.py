"""
Полный автоматический агент для тестирования "Трудник"
"""

import sys
import subprocess
from pathlib import Path

venv_path = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
if venv_path.exists():
    python_cmd = str(venv_path)
else:
    python_cmd = "python"

def run_command(cmd, timeout=120):
    """Запустить команду"""
    print(f"\n{'='*60}")
    print(f"[EXEC] {cmd}")
    print('='*60)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(Path(__file__).parent))
        print(f"[OK] Код: {result.returncode}")
        if result.stdout:
            print(f"[OUTPUT] {result.stdout[:2000]}")
        if result.stderr and result.returncode != 0:
            print(f"[ERROR] {result.stderr[:500]}")
        return result
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def main():
    print("\n" + "="*60)
    print("FULL AUTO TEST AGENT для 'Трудник'")
    print("="*60)
    print("\nДоступные команды:")
    print("1. check_all     - Проверить всё")
    print("2. fix_rls       - Инструкции по отключению RLS")
    print("3. test_login    - Протестировать вход работодателя")
    print("4. fix_role      - Создать скрипт для исправления роли")
    print("5. auto_test     - Автоматическое тестирование")
    
    if len(sys.argv) < 2:
        print("\nИспользование: python full_auto_agent.py <команда>")
        return
    
    command = sys.argv[1].lower()
    
    if command == "check_all":
        print("\n### Шаг 1: Проверка конфигурации")
        run_command(f'{python_cmd} auto_fix_agent.py check_config')
        
        print("\n### Шаг 2: Проверка роли пользователя")
        run_command(f'{python_cmd} auto_fix_agent.py check_role')
        
        print("\n### Шаг 3: Тест входа работодателя")
        run_command(f'{python_cmd} my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"')
        
    elif command == "fix_rls":
        print("\n### Инструкции по отключению RLS")
        print("1. Перейдите в Supabase Dashboard:")
        print("   https://supabase.com/dashboard/project/***REMOVED***/table-editor")
        print("2. Найдите таблицу 'profiles'")
        print("3. Три точки → Table Settings → Row Level Security → Отключите")
        print("4. Сохраните изменения")
        
    elif command == "test_login":
        print("\n### Тест входа работодателя")
        run_command(f'{python_cmd} my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"')
        
    elif command == "fix_role":
        print("\n### Создание скрипта для исправления роли")
        run_command(f'{python_cmd} auto_fix_agent.py create_fix')
        print("\nИнструкция:")
        print("1. Загрузите fix_role_via_service_key.py на PythonAnywhere")
        print("2. Убедитесь, что SERVICE_KEY задан в .env файле")
        print("3. Выполните: python fix_role_via_service_key.py")
        
    elif command == "auto_test":
        print("\n### Автоматическое тестирование")
        
        print("\n[1/3] Проверка конфигурации...")
        run_command(f'{python_cmd} auto_fix_agent.py check_config')
        
        print("\n[2/3] Проверка роли пользователя...")
        run_command(f'{python_cmd} auto_fix_agent.py check_role')
        
        print("\n[3/3] Тест входа работодателя...")
        run_command(f'{python_cmd} my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"')
        
        print("\n" + "="*60)
        print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        print("="*60)
        print("\nЕсли роль не обновлена:")
        print("1. Отключите RLS в Supabase Dashboard (см. 'fix_rls')")
        print("2. Или запустите скрипт fix_role_via_service_key.py на PythonAnywhere")
    else:
        print(f"[ERROR] Неизвестная команда: {command}")

if __name__ == "__main__":
    main()
