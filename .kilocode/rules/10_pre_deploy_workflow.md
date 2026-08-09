@rule global code
ПЕРЕД КАЖДЫМ `git push` ОБЯЗАТЕЛЬНО запускай `python scripts/pre_deploy_check.py`.
Если скрипт находит проблемы — ИСПРАВЬ их до push. Не push'ь с ошибками.
Регулярно актуализируй скрипт (scripts/pre_deploy_check.py) и static tests
(tests/test_static_checks.py), если обнаруживаешь новые системные паттерны багов.

Также регулярно пользуйся и актуализируй `.kilocode/memory/project_patterns.md` —
там записаны все паттерны проекта (CSP, PostgREST, Celery, CSRF, SW, HTML,
миграции), выявленные из 100+ багфиксов. Добавляй новые паттерны при обнаружении.

При обнаружении нового системного бага:
1. Исправь код.
2. Добавь проверку в scripts/pre_deploy_check.py + tests/test_static_checks.py.
3. Запиши паттерн в .kilocode/memory/project_patterns.md.
4. Запусти pre_deploy_check.py — должен быть 0 проблем.
