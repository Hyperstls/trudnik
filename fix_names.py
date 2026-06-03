# Исправление register() в app.py

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим и меняем name на full_name
for i in range(len(lines)):
    # name = request.form.get('name') -> full_name = request.form.get('full_name')
    if "name = request.form.get('name')" in lines[i]:
        lines[i] = lines[i].replace("name = request.form.get('name')", "full_name = request.form.get('full_name')")
        print(f'Line {i+1}: name -> full_name')
    # 'name': name, -> 'full_name': full_name,
    if "'name': name," in lines[i]:
        lines[i] = lines[i].replace("'name': name,", "'full_name': full_name,")
        print(f'Line {i+1}: name -> full_name in dict')
    # session['name'] = name -> session['name'] = full_name
    if "session['name'] = name" in lines[i]:
        lines[i] = lines[i].replace("session['name'] = name", "session['name'] = full_name")
        print(f'Line {i+1}: session name updated')

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done!')
