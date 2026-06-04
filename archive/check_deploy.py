#!/usr/bin/env python3
"""Проверка, что app.py содержит max_workers"""

import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

checks = [
    ('max_workers', r"'max_workers'"),
    ('current_workers', r"'current_workers'"),
    ('job_new route', r'def job_new'),
    ('create_job route', r'def create_job'),
]

print("=" * 60)
print("ПРОВЕРКА app.py НА ЛОКАЛЬНОМ КОМПЬЮТЕРЕ")
print("=" * 60)

for name, pattern in checks:
    if re.search(pattern, content):
        print(f"[OK] {name} найден")
    else:
        print(f"[ERROR] {name} НЕ найден")

# Проверка шаблонов
print("\n" + "=" * 60)
print("ПРОВЕРКА ШАБЛОНов")
print("=" * 60)

import os
templates_dir = 'templates'

for template in ['job_new.html', 'job_detail.html', 'my_jobs.html']:
    path = os.path.join(templates_dir, template)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            t_content = f.read()
        if 'max_workers' in t_content:
            print(f"[OK] {template} содержит max_workers")
        else:
            print(f"[WARN] {template} НЕ содержит max_workers")
    else:
        print(f"[ERROR] {template} не найден")

print("\n" + "=" * 60)
