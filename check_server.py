"""Check server status"""
import requests

print("Testing server...")
try:
    r = requests.get('https://hyperstls.pythonanywhere.com', timeout=10)
    print(f'Status: {r.status_code}')
    print(f'Time: {r.elapsed}')
except Exception as e:
    print(f'Error: {e}')
