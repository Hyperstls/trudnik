#!/usr/bin/env python3
"""
Скрипт для тестирования системы избранного
Использует requests для проверки API endpoints
"""

import requests
import sys
import json
from datetime import datetime

# Настройки
BASE_URL = "https://hyperstls.pythonanywhere.com"

# API endpoints
API_CHECK = f"{BASE_URL}/api/favorites/check"
API_ADD = f"{BASE_URL}/api/favorites/add"
API_REMOVE = f"{BASE_URL}/api/favorites/remove"

def test_api_endpoint(name, url, method="POST", data=None, headers=None, cookies=None):
    """Тестирование API endpoint"""
    print(f"\n{'='*60}")
    print(f"Тест: {name}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    
    if headers is None:
        headers = {'Content-Type': 'application/json'}
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        else:
            response = requests.post(url, 
                                    json=data, 
                                    headers=headers, 
                                    cookies=cookies,
                                    timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {response.elapsed.total_seconds():.3f}s")
        
        # Проверяем Content-Type
        content_type = response.headers.get('Content-Type', '')
        print(f"Content-Type: {content_type}")
        
        if 'application/json' in content_type or response.status_code == 200:
            try:
                result = response.json()
                print(f"Response: {json.dumps(result, indent=2)}")
                return True, result
            except:
                print(f"Response (text): {response.text[:200]}")
                return False, None
        else:
            print(f"Error: {response.text[:200]}")
            return False, None
            
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return False, None
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return False, None

def main():
    print("="*60)
    print("Тестирование системы избранного")
    print("="*60)
    
    # Тестовые данные
    worker_id = "test-worker-123"
    
    results = {}
    
    # Тест 1: Проверка /api/favorites/check
    success, result = test_api_endpoint(
        "Check favorite status",
        API_CHECK,
        data={"worker_id": worker_id}
    )
    results["check"] = success
    
    # Тест 2: Добавление в избранное
    success, result = test_api_endpoint(
        "Add to favorites",
        API_ADD,
        data={"worker_id": worker_id}
    )
    results["add"] = success
    
    # Тест 3: Проверка после добавления
    success, result = test_api_endpoint(
        "Check favorite status after add",
        API_CHECK,
        data={"worker_id": worker_id}
    )
    results["check_after_add"] = success
    
    # Тест 4: Удаление из избранного
    success, result = test_api_endpoint(
        "Remove from favorites",
        API_REMOVE,
        data={"worker_id": worker_id}
    )
    results["remove"] = success
    
    # Тест 5: Проверка после удаления
    success, result = test_api_endpoint(
        "Check favorite status after remove",
        API_CHECK,
        data={"worker_id": worker_id}
    )
    results["check_after_remove"] = success
    
    # Сводка
    print("\n" + "="*60)
    print("СВОДКА РЕЗУЛЬТАТОВ")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\nAll tests passed successfully!")
        return 0
    else:
        print("\nSome tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
