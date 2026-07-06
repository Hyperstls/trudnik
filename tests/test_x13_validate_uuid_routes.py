"""X13: all routes with UUID path parameters must use @validate_uuid."""
import inspect
import re


def test_all_uuid_routes_have_validate_uuid():
    """X13: routes with UUID params must use @validate_uuid decorator."""
    from app.blueprints import (
        jobs, applications, chat, notifications, favorites,
        employers, blacklist, jobs_api, ratings, admin,
        admin_users, admin_jobs, admin_verification, admin_dictionaries
    )
    
    # Паттерн для поиска UUID-параметров в маршрутах
    uuid_param_pattern = re.compile(r'<([a-z_]+_id)>')
    
    # Список всех blueprint модулей для проверки
    modules_to_check = [
        jobs, applications, chat, notifications, favorites,
        employers, blacklist, jobs_api, ratings, admin,
        admin_users, admin_jobs, admin_verification, admin_dictionaries
    ]
    
    violations = []
    
    for module in modules_to_check:
        # Получить все функции из модуля
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and hasattr(obj, '__wrapped__'):
                # Это декорированная функция
                func = obj
                # Получить исходный код
                try:
                    source = inspect.getsource(func)
                except:
                    continue
                
                # Найти все @route декораторы
                route_matches = re.findall(r'@.*?\.route\([\'"](.*?)[\'"]', source)
                
                for route in route_matches:
                    # Проверить, есть ли UUID-параметры
                    uuid_params = uuid_param_pattern.findall(route)
                    if uuid_params:
                        # Проверить, есть ли @validate_uuid
                        if '@validate_uuid' not in source:
                            violations.append(
                                f"{module.__name__}.{name}: route '{route}' has UUID params but no @validate_uuid"
                            )
    
    # Если есть нарушения — тест провален
    if violations:
        violation_msg = "\n".join(violations)
        assert False, f"Routes missing @validate_uuid:\n{violation_msg}"
