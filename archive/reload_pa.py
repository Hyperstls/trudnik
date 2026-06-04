import urllib.request
import json

# PythonAnywhere API credentials
API_TOKEN = "e4e936c2bed6824c4981927652c21986780e22b3"
USERNAME = "Hyperstls"

# API endpoints
API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{USERNAME}/"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# Reload the web app
webapp_url = f"{API_BASE}webapps/hyperstls.pythonanywhere.com/reload/"
print(f"Reload webapp: {webapp_url}")

try:
    req = urllib.request.Request(webapp_url, method='POST')
    req.add_header("Authorization", f"Token {API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    
    with urllib.request.urlopen(req, timeout=10) as response:
        print(f"Status: {response.status}")
        if response.status == 200:
            print("Web app reloaded successfully!")
            print(f"Response: {response.read().decode()}")
        else:
            print(f"Error: {response.read().decode()}")
except Exception as e:
    print(f"Exception: {e}")
