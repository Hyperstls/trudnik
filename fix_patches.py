# fix_patches.py
import os, re, glob, sys

# Принудительно UTF-8 для вывода
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Файлы для обработки
files = glob.glob('tests/test_all_functions.py') + glob.glob('tests/test_*.py')

for filepath in files:
    if not os.path.exists(filepath): continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Замена 1: 'app.blueprints.XXX.supabase_request' → 'app.utils.supabase_request'
    content = re.sub(
        r"'app\.blueprints\.\w+\.supabase_request'",
        "'app.utils.supabase_request'",
        content
    )
    
    # Замена 2: 'app.utils.requests.' → 'app.utils.supabase.requests.'
    content = content.replace("'app.utils.requests.'", "'app.utils.supabase.requests.'")
    
    # Замена 3: 'app.decorators.supabase_request' → 'app.utils.supabase_request'  
    content = content.replace("'app.decorators.supabase_request'", "'app.utils.supabase_request'")
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'OK {filepath} - replacements applied')
    else:
        print(f'SKIP {filepath} - no changes')

print('Done.')
