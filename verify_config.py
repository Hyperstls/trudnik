import os

# Проверка конфигурации
errors = []

if not os.getenv('SUPABASE_URL'):
    errors.append('SUPABASE_URL не задан')
if not os.getenv('SUPABASE_KEY') and not os.getenv('SUPABASE_ANON_KEY'):
    errors.append('SUPABASE_KEY или SUPABASE_ANON_KEY не задан')

if errors:
    print('Ошибки конфигурации:')
    for err in errors:
        print(f'  - {err}')
else:
    print('Конфигурация OK')

# Проверка переменных в шаблонах
templates_with_missing_vars = {
    'base.html': ['git_version'],
    'index.html': ['jobs', 'workers', 'user_id', 'user_role', 'git_version', 'applied_job_ids', 'city', 'payment_min', 'payment_max', 'sort', 'lat', 'lng', 'radius'],
    'login.html': [],
    'register.html': [],
    'profile.html': ['profile_user', 'current_user_id', 'current_user_role', 'error_message'],
    'profile_edit.html': ['profile'],
    'my_jobs.html': ['jobs'],
    'my_applications.html': ['applications', 'jobs', 'user_id'],
    'workers.html': ['workers'],
    'shifts.html': ['shifts'],
    'chat.html': ['shift', 'messages', 'user_id'],
    'chats_list.html': ['chats', 'shifts'],
    'job_detail.html': ['job', 'employer', 'already_applied', 'yandex_api_key', 'current_user_role'],
    'favorites.html': ['jobs'],
    'blacklist.html': ['workers'],
}

# Проверка существования файлов
import os
templates_dir = 'templates'
missing_templates = []
for template in templates_with_missing_vars.keys():
    if not os.path.exists(os.path.join(templates_dir, template)):
        missing_templates.append(template)

if missing_templates:
    print('Отсутствующие шаблоны:')
    for t in missing_templates:
        print(f'  - {t}')
