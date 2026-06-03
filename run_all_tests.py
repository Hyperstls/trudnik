"""
Финальный тестовый скрипт для проверки и исправления всех функций "Трудника"
"""

import subprocess
import sys

def run_command(cmd, description):
    """Запустить команду и проверить результат"""
    print(f"\n{'='*70}")
    print(f"🔍 {description}")
    print(f"{'='*70}")
    print(f"📋 Команда: {cmd}")
    print()
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=120
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        
        if result.returncode == 0:
            print(f"✅ Успех: {description}")
            return True
        else:
            print(f"❌ Ошибка: {description} (код {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ Таймаут: {description}")
        return False
    except Exception as e:
        print(f"❌ Исключение: {description}: {e}")
        return False

def main():
    print("🤖 Тестирование и исправление 'Трудника'")
    print("="*70)
    
    tests = [
        # Проверка auto_fix_agent.py
        (
            'python auto_fix_agent.py "Добавь столбец verified в таблицу profiles"',
            "Тест auto_fix_agent.py - добавление столбца"
        ),
        (
            'python auto_fix_agent.py "Обнови сайт"',
            "Тест auto_fix_agent.py - обновление сайта"
        ),
        (
            'python auto_fix_agent.py "Проверь состояние БД"',
            "Тест auto_fix_agent.py - проверка БД"
        ),
        
        # Проверка my_browser_agent.py
        (
            'python my_browser_agent.py "Перейди на главную страницу"',
            "Тест my_browser_agent.py - главная страница"
        ),
        
        # Проверка тестовых скриптов
        (
            'python test_profile_api.py',
            "Проверка профилей в БД"
        ),
    ]
    
    results = []
    for cmd, desc in tests:
        result = run_command(cmd, desc)
        results.append((desc, result))
        
        # Пауза между тестами
        print("\n⏳ Ожидание 5 секунд...")
        import time
        time.sleep(5)
    
    # Итоги
    print(f"\n{'='*70}")
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*70}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for desc, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {desc}")
    
    print(f"\nВсего тестов: {total}")
    print(f"Успешно: {passed}")
    print(f"Ошибок: {total - passed}")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены успешно!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} тест(ов) не пройдено")
        return 1

if __name__ == "__main__":
    sys.exit(main())
