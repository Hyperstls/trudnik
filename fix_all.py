# Исправление register() и login() в app.py

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Меняем name на full_name для register
content = content.replace("name = request.form.get('name')", "full_name = request.form.get('full_name')")
content = content.replace("'name': name,", "'full_name': full_name,")
content = content.replace("session['name'] = name", "session['name'] = full_name")

# Меняем name на full_name для login
content = content.replace("session['name'] = profile_data.get('name')", "session['name'] = profile_data.get('full_name')")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done!')
