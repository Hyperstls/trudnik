# skip_deleted.py
import os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

filepath = 'tests/test_all_functions.py'
if not os.path.exists(filepath):
    print('File not found')
    sys.exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

original = content

# Добавить skip перед class TestShiftsBlueprint
content = content.replace(
    'class TestShiftsBlueprint',
    '@pytest.mark.skip(reason="Модуль shifts удалён миграцией 027")\nclass TestShiftsBlueprint'
)

# Добавить skip перед class TestMonetizationBlueprint
content = content.replace(
    'class TestMonetizationBlueprint',
    '@pytest.mark.skip(reason="Модуль monetization удалён миграцией 022")\nclass TestMonetizationBlueprint'
)

if content != original:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK Skip markers added')
else:
    print('SKIP No changes (markers may already exist)')
