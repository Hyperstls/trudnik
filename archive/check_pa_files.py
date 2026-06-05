import urllib.request
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# PythonAnywhere API credentials
API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN")
USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")

if not API_TOKEN or not USERNAME:
    raise RuntimeError(
        "PYTHONANYWHERE_API_TOKEN и PYTHONANYWHERE_USERNAME должны быть "
        "установлены в переменных окружения."
    )

# API endpoints
API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{USERNAME}/"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# Get files in home directory
home_url = f"{API_BASE}files/path/home/{USERNAME}/"
print(f"Get files: {home_url}")

try:
    req = urllib.request.Request(home_url, method='GET')
    req.add_header("Authorization", f"Token {API_TOKEN}")
    
    with urllib.request.urlopen(req, timeout=10) as response:
        files = json.loads(response.read().decode())
        print(f"Files in home directory:")
        for item in files:
            print(f"  {item['name']} ({'dir' if item['is_dir'] else 'file'})")
except Exception as e:
    print(f"Exception: {e}")

# Get files in mysite directory
mysite_url = f"{API_BASE}files/path/home/{USERNAME}/mysite/"
print(f"\nGet files: {mysite_url}")

try:
    req = urllib.request.Request(mysite_url, method='GET')
    req.add_header("Authorization", f"Token {API_TOKEN}")
    
    with urllib.request.urlopen(req, timeout=10) as response:
        files = json.loads(response.read().decode())
        print(f"Files in mysite directory:")
        for item in files:
            print(f"  {item['name']} ({'dir' if item['is_dir'] else 'file'})")
except Exception as e:
    print(f"Exception: {e}")
