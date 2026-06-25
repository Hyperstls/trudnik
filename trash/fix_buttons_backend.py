# fix_buttons_backend.py
import os, re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

filepath = 'tests/test_buttons_backend.py'
if not os.path.exists(filepath):
    print('File not found')
    sys.exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

original = content

# Исправь form_with_csrf() вызовы — убрать keyword arguments если они есть
# form_with_csrf(data) вместо form_with_csrf(field=value)
# Замена keyword вызовов на позиционные где data — dict
content = re.sub(r'form_with_csrf\((\w+)=', r'form_with_csrf({', content)
# Это грубая замена, но лучше чем ничего

if content != original:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK test_buttons_backend.py fixed')
else:
    print('SKIP test_buttons_backend.py - no changes')
