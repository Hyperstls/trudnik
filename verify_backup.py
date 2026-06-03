with open('app_backup.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Проверяем синтаксис
try:
    compile(content, 'app_backup.py', 'exec')
    print("[OK] Синтаксис OK")
except SyntaxError as e:
    print(f"[FAIL] Синтаксическая ошибка: {e}")
