# Скрипт для исправления register() в app.py

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим строку с name = request.form.get('name')
for i, line in enumerate(lines):
    if "name = request.form.get('name')" in line:
        print(f'Found at line {i+1}: {line.rstrip()}')
        lines[i] = line.replace("name = request.form.get('name')", "full_name = request.form.get('full_name')  # Исправлено: full_name вместо name")
        print(f'Changed to: {lines[i].rstrip()}')
    if "'name': name," in line:
        lines[i] = line.replace("'name': name,", "'full_name': full_name,  # Используем full_name")
        print(f'Changed line {i+1}: {lines[i].rstrip()}')
    if "session['name'] = name" in line:
        lines[i] = line.replace("session['name'] = name", "session['name'] = full_name")
        print(f'Changed line {i+1}: {lines[i].rstrip()}')

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('File updated!')
