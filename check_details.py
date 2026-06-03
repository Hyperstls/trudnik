import re

# Проверка маршрутов
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()

# Ищем маршруты
routes = re.findall(r"@app\.route\([\'\"]([^\'\"]+)[\'\"]", app_content)
print("Маршруты в app.py:")
for r in routes:
    print(f"  {r}")

# Ищем функции
functions = re.findall(r"def (\w+)\(", app_content)
print("\nФункции в app.py:")
for f in functions:
    print(f"  {f}")
