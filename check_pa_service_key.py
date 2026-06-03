"""
Проверка SERVICE_KEY из PythonAnywhere
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME", "Hyperstls")
PA_API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN", "e4e936c2bed6824c4981927652c21986780e22b3")

console_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/"

print("=== Получение SERVICE_KEY из PythonAnywhere ===")
print(f"Username: {PA_USERNAME}")

headers = {"Authorization": f"Token {PA_API_TOKEN}"}

# Получаем консоли
resp = requests.get(console_url, headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if resp.status_code == 200:
    consoles = resp.json()
    print(f"\nНайдено консолей: {len(consoles)}")
    
    for console in consoles:
        console_id = console["id"]
        print(f"\n--- Консоль #{console_id}: {console['name']} ---")
        
        # Получаем историю ввода
        history_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/{console_id}/history/"
        hist_resp = requests.get(history_url, headers=headers, timeout=10)
        
        if hist_resp.status_code == 200:
            history = hist_resp.json()
            print(f"История команд:")
            for item in history:
                print(f"  - {item['input']}")
                if item.get('output'):
                    print(f"    Output: {item['output'][:200]}")
        else:
            print(f"Ошибка получения истории: {hist_resp.status_code}")
else:
    print(f"Ошибка: {resp.status_code}")
    print(f"Response: {resp.text}")
