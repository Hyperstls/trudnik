"""Ожидание доступности продакшена Amvera."""
import urllib.request
import urllib.error
import time
import sys
import os

URL = os.environ.get("PROD_URL", "https://trudnik-hyperstls.amvera.io/")
HEALTH_URL = URL.rstrip("/") + "/health"
MAX_ATTEMPTS = 20
WAIT_SEC = 15

print(f"Waiting for {HEALTH_URL} (up to {MAX_ATTEMPTS} attempts, {WAIT_SEC}s each)...")
for i in range(1, MAX_ATTEMPTS + 1):
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        r = urllib.request.urlopen(req, timeout=20)
        print(f"[{i}/{MAX_ATTEMPTS}] HTTP {r.getcode()} — PROD is UP!")
        sys.exit(0)
    except urllib.error.HTTPError as e:
        print(f"[{i}/{MAX_ATTEMPTS}] HTTP {e.code} — waiting {WAIT_SEC}s...")
    except Exception as e:
        print(f"[{i}/{MAX_ATTEMPTS}] {type(e).__name__}: {e} — waiting {WAIT_SEC}s...")
    time.sleep(WAIT_SEC)

print(f"FAIL: Prod not reachable after {MAX_ATTEMPTS} attempts")
sys.exit(1)
