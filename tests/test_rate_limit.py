"""Тест rate limiting: 10 запросов — ок, 11-й — блокировка."""
import sys
import requests
from datetime import datetime

BASE = "http://127.0.0.1:5000"

passed = 0
failed = 0


def log(level, msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {level:5s} | {msg}")


log("INFO", f"Rate Limit Test — {BASE}")
log("INFO", "=" * 60)

# Делаем 11 POST запросов на /login с неверным паролем
blocked = False
for i in range(1, 13):
    s = requests.Session()
    s.get(f"{BASE}/login")  # CSRF
    resp = s.post(f"{BASE}/login", data={
        "email": "org@test.ru",
        "password": f"wrong{i}",
    }, allow_redirects=True)

    is_blocked = "Слишком много попыток" in resp.text
    print(f"  Request {i:2d}: status={resp.status_code}, blocked={is_blocked}")

    if is_blocked and i > 10:
        blocked = True

if blocked:
    passed += 1
    log("PASS", "Rate limit activated after 10+ requests")
else:
    failed += 1
    log("FAIL", "Rate limit NOT activated (may need different IP or timing)")

log("INFO", f"Total: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
