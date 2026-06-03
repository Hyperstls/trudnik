import re

with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()

routes = re.findall(r'@app\.route\([\'"]([^\'"]+)[\'"]', app_content)
print("Маршруты в app.py:")
for r in routes:
    print(f"  {r}")
