import urllib.request
import urllib.parse

# PythonAnywhere API credentials
API_TOKEN = "e4e936c2bed6824c4981927652c21986780e22b3"
USERNAME = "Hyperstls"

# Console API endpoint
console_url = f"https://www.pythonanywhere.com/api/v0/user/{USERNAME}/consoles/"

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# Create a console
print("Creating console...")
try:
    req = urllib.request.Request(console_url, method='POST', data=b'{}')
    req.add_header("Authorization", f"Token {API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    
    with urllib.request.urlopen(req, timeout=10) as response:
        console_data = urllib.parse.parse_qs(response.read().decode())
        print(f"Console created: {console_data}")
except Exception as e:
    print(f"Exception creating console: {e}")
