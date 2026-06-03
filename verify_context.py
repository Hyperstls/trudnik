import os
import re

# Получаем текущий проект
project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)

# Читаем PROJECT_CONTEXT.md
with open('PROJECT_CONTEXT.md', 'r', encoding='utf-8') as f:
    context = f.read()

print("=" * 80)
print("ПРОВЕРКА ПРОЕКТА НА ОСНОВЕ PROJECT_CONTEXT.md")
print("=" * 80)

# Проверяем основные файлы
print("\n[1] Проверка основных файлов...")
required_files = ['app.py', 'config.py', 'requirements.txt', '.env']
for f in required_files:
    if os.path.exists(f):
        print(f"    [OK] {f}")
    else:
        print(f"    [MISSING] {f}")

# Проверяем структуру шаблонов
print("\n[2] Проверка шаблонов...")
templates_dir = 'templates'
required_templates = [
    'base.html', 'index.html', 'login.html', 'register.html',
    'jobs.html', 'job_detail.html', 'my_jobs.html', 'my_applications.html',
    'profile.html', 'profile_edit.html', 'workers.html', 'job_new.html'
]
missing_templates = []
for t in required_templates:
    if not os.path.exists(os.path.join(templates_dir, t)):
        missing_templates.append(t)
        print(f"    [MISSING] {t}")
    else:
        print(f"    [OK] {t}")

# Проверяем таблицы в контексте
print("\n[3] Проверка таблиц базы данных...")
required_tables = [
    'profiles', 'jobs', 'applications', 'shifts', 'messages',
    'favorites', 'blacklist', 'reviews', 'job_favorites'
]
# (проверка абстрактная, реальная проверка требует подключения к Supabase)

# Проверяем маршруты из app.py
print("\n[4] Проверка маршрутов...")
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()

required_routes = [
    '/', '/register', '/login', '/logout',
    '/jobs', '/job/new', '/job/<job_id>', '/my-jobs',
    '/my-applications', '/profile', '/profile/<user_id>', '/profile/edit',
    '/profile/worker/<worker_id>', '/workers',
    '/apply/<job_id>', '/unapply/<job_id>',
    '/favorite-job/<job_id>', '/unfavorite-job/<job_id>',
    '/favorites', '/blacklist',
    '/chats', '/chat/<shift_id>', '/chat/new/<worker_id>',
    '/shifts', '/shift/<shift_id>/action',
    '/admin', '/verify-employer'
]

found_routes = re.findall(r"@app\.route\([\'\"]([^\'\"]+)[\'\"]", app_content)
print(f"    [INFO] Найдено {len(found_routes)} маршрутов в app.py")

missing_routes = []
for r in required_routes:
    if r not in found_routes:
        missing_routes.append(r)
        print(f"    [MISSING] {r}")

# Проверяем основные функции
print("\n[5] Проверка основных функций...")
required_functions = [
    'register', 'login', 'logout', 'index', 'jobs_list', 'job_new',
    'job_detail', 'my_jobs', 'my_applications', 'profile', 'profile_edit',
    'profile_worker', 'workers', 'apply_job', 'unapply_job',
    'favorite_job', 'unfavorite_job', 'favorites', 'blacklist',
    'chats', 'chat', 'chat_new', 'shifts', 'shift_action',
    'admin', 'verify_employer'
]

found_functions = re.findall(r"def (\w+)\(", app_content)
print(f"    [INFO] Найдено {len(found_functions)} функций в app.py")

missing_functions = []
for f in required_functions:
    if f not in found_functions:
        missing_functions.append(f)
        print(f"    [MISSING] {f}")

# Резюме
print("\n" + "=" * 80)
print("РЕЗЮМЕ")
print("=" * 80)

all_missing = missing_templates + missing_routes + missing_functions
if not all_missing:
    print("\n[SUCCESS] Все обязательные файлы, маршруты и функции присутствуют!")
    print("\nРекомендации:")
    print("- Запустить приложение и проверить работу")
    print("- Убедиться в корректности работы с Supabase")
    print("- Проверить права доступа (werkzeug SecurityWarning)")
else:
    print(f"\n[WARNING] Обнаружено {len(all_missing)} пропущенных элементов:")
    for m in all_missing:
        print(f"  - {m}")

# Предложение о коммите
print("\n" + "=" * 80)
print("ПРЕДЛОЖЕНИЕ КОММИТА")
print("=" * 80)
print("\nИзменения:")
print("  1. config.py - исправлен синтаксис (был записан как строка)")
print("  2. app.py - восстановлен из git (был обрезан на строке 399)")
print("  3. templates/ - добавлены/обновлены шаблоны:")
print("     - error.html (новый)")
print("     - job_new.html (новый)")
print("     - jobs.html (новый)")
print("     - profile_edit.html (новый)")
print("     - blacklist.html (обновлён)")
print("     - favorites.html (обновлён)")
print("     - profile_worker.html (обновлён)")
print("     - create_job.html (удалён - дублируется)")
print("\nУдалённые файлы:")
print("  - agent_edit.py")
print("  - auto_fix.py")
print("  - check_project.py")
print("  - check_app.py")
print("  - check_app_exists.py")
print("  - check_app_length.py")
print("  - check_app_lines.py")
print("  - check_backup.py")
print("  - check_config.py")
print("  - check_git_app.py")
print("  - check_login.py")
print("  - check_name_usage.py")
print("  - check_names.py")
print("  - check_profile_edit.py")
print("  - check_profile_update.py")
print("  - check_register.py")
print("  - check_routes.py")
print("  - check_routes_templates.py")
print("  - check_templates.py")
print("  - fix_applications.py")
print("  - fix_profile.py")
print("  - main.py")
print("\nДобавленные файлы:")
print("  - FINAL_REPORT.md")
print("  - templates/error.html")
print("  - templates/job_new.html")
print("  - templates/jobs.html")
print("  - templates/profile_edit.html")
