#!/usr/bin/env python3
import sys
sys.path.insert(0, '.venv/Lib/site-packages')
import requests

r = requests.get('https://hyperstls.pythonanywhere.com', timeout=10)
print('Status:', r.status_code)
