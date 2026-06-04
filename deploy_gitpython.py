#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Деплой через GitPython (если установлен)
"""

try:
    from git import Repo
    import os
    
    print("=== Деплой через GitPython ===\n")
    
    # Локальный репозиторий
    local_repo_path = os.path.dirname(os.path.abspath(__file__))
    local_repo = Repo(local_repo_path)
    
    print("1. Локальный репозиторий:")
    print(f"   Путь: {local_repo_path}")
    print(f"   Активная ветка: {local_repo.active_branch}")
    
    # Проверить, что всё закоммичено
    if local_repo.is_dirty():
        print("\n[WARN] Есть несохраненные изменения!")
        print("   Выполните: git add -A && git commit -m 'message'")
    else:
        print("\n[OK] Все изменения закоммичены")
    
    # Пуш наorigin
    print("\n2. Отправка на GitHub...")
    origin = local_repo.remotes.origin
    origin.push('main')
    print("   [OK] Успешно отправлено")
    
    print("\n=== Инструкция для PythonAnywhere ===")
    print("Выполните в консоли PythonAnywhere:")
    print("  cd ~/mysite")
    print("  git pull")
    print("  touch app.py.wsgi")
    
except ImportError:
    print("[ERR] GitPython не установлен")
    print("Установите: pip install GitPython")
except Exception as e:
    print(f"[ERR] Ошибка: {e}")
