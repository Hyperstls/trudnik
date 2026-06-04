#!/usr/bin/env python3
"""Проверка конца файла app.py"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Last 10 lines:")
for line in lines[-10:]:
    print(line.strip())
