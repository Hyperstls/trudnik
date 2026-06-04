#!/usr/bin/env python3
"""Скрипт для тестирования создания задания напрямую на сервере"""

import sys
import os

# Добавляем путь к проекту
project_path = '/home/Hyperstls/mysite'
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from app import app

# Создаем тестовое задание
test_job_data = {
    'title': 'Тест max_workers',
    'city': 'Москва',
    'address': 'Тестовая улица, 1',
    'description': 'Тестовое задание для проверки max_workers',
    'payment': '5000',
    'max_workers': '5',
    'latitude': '55.751574',
    'longitude': '37.613260',
}

with app.app_context():
    # Имитация сессии
    with app.test_client() as client:
        print("=" * 60)
        print("ТЕСТ: Создание задания с max_workers")
        print("=" * 60)
        
        # 1. Сначала нужно залогиниться
        print("\n[1/3] Логинимся как работодатель...")
        login_response = client.post('/login', data={
            'email': 'test_max_workers@example.com',
            'password': 'Test123456'
        }, follow_redirects=True)
        print(f"    Статус: {login_response.status_code}")
        
        # 2. Переходим на страницу создания задания
        print("\n[2/3] Переходим на /job/new...")
        job_new_response = client.get('/job/new')
        print(f"    Статус: {job_new_response.status_code}")
        
        # 3. Создаем задание
        print("\n[3/3] Создаем задание...")
        create_response = client.post('/job/new', data=test_job_data, follow_redirects=True)
        print(f"    Статус: {create_response.status_code}")
        print(f"    URL после создания: {create_response.request.url}")
        
        # Проверяем результат
        if 'Задание опубликовано' in create_response.get_data(as_text=True):
            print("\n[OK] Задание успешно создано!")
        elif 'Ошибка создания задания' in create_response.get_data(as_text=True):
            print("\n[ERROR] Ошибка создания задания!")
            print("\nПолный ответ сервера:")
            print(create_response.get_data(as_text=True))
        else:
            print("\n[WARN] Неожиданный результат")
            print("\nПервые 1000 символов ответа:")
            print(create_response.get_data(as_text=True)[:1000])
        
        print("\n" + "=" * 60)
