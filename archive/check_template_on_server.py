#!/usr/bin/env python3
"""
Проверка наличия поля max_workers в шаблоне на сервере PythonAnywhere
Через Flask shell или прямой доступ к файлам
"""

import os
import sys

# Добавляем путь к приложению
sys.path.insert(0, '/var/www/trudnik_pythonanywhere_com')

from flask import Flask
app = Flask(__name__)

def check_template():
    """Проверка шаблона job_new.html на сервере"""
    template_path = '/var/www/trudnik_pythonanywhere_com/templates/job_new.html'
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'max_workers' in content:
            print("✅ Поле max_workers найдено в шаблоне на сервере!")
            
            # Показать строку с полем
            for i, line in enumerate(content.split('\n'), 1):
                if 'max_workers' in line:
                    print(f"   Строка {i}: {line.strip()}")
            
            # Проверить, что это правильный HTML
            if '<input type="number" name="max_workers"' in content:
                print("✅ Найдено правильное поле input с name='max_workers'")
                return True
            else:
                print("⚠️ Поле есть, но может быть скрыто или неправильно настроено")
                return False
        else:
            print("❌ Поле max_workers НЕ найдено в шаблоне на сервере!")
            return False
    else:
        print(f"❌ Шаблон не найден по пути: {template_path}")
        return False

if __name__ == '__main__':
    print("Проверка шаблона job_new.html на PythonAnywhere...")
    print("=" * 60)
    check_template()
