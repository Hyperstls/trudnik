"""
Деплой на PythonAnywhere через Git
"""

import subprocess
import sys

print("=== Деплой на PythonAnywhere ===\n")

# 1. Проверить статус Git
print("1. Проверка статуса Git...")
try:
    result = subprocess.run(['git', 'status'], capture_output=True, text=True, timeout=10)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
except Exception as e:
    print(f"Ошибка: {e}")

# 2. Проверить лог
print("\n2. Лог последних коммитов...")
try:
    result = subprocess.run(['git', 'log', '--oneline', '-5'], capture_output=True, text=True, timeout=10)
    print(result.stdout)
except Exception as e:
    print(f"Ошибка: {e}")

# 3. Push на GitHub
print("\n3. Отправка на GitHub...")
try:
    result = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True, timeout=30)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
except Exception as e:
    print(f"Ошибка: {e}")

print("\n=== Готово! ===")
print("\nИзменения отправлены на GitHub.")
print("Теперь выполните на PythonAnywhere:")
print("  cd ~/mysite")
print("  git pull")
print("  touch app.py.wsgi")
