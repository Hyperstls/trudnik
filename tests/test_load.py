"""Load/stress testing for Trudnik — проверка устойчивости под нагрузкой."""
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import os
BASE = os.environ.get('TEST_BASE_URL', 'http://localhost:8000')
CONCURRENT_USERS = 20
REQUESTS_PER_USER = 5

results = {"success": 0, "failed": 0, "times": []}


def make_request(url, session=None):
    """Один HTTP-запрос, возвращает время ответа."""
    s = session or requests.Session()
    start = time.time()
    try:
        r = s.get(url, timeout=10)
        elapsed = time.time() - start
        return {"ok": r.status_code == 200, "time": elapsed, "status": r.status_code}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "time": elapsed, "error": str(e)[:80]}


def user_session(email, password):
    """Имитация пользовательской сессии: логин + несколько запросов."""
    s = requests.Session()
    # Логин
    s.get(f"{BASE}/login")
    resp = s.post(f"{BASE}/login", data={"email": email, "password": password}, timeout=10)
    if resp.status_code != 200 or "login" in resp.url:
        return [{"ok": False, "time": 0, "error": "login failed"}]

    times = []
    for _ in range(REQUESTS_PER_USER):
        r = make_request(f"{BASE}/", session=s)
        times.append(r)
    return times


def run():
    print(f"Trudnik Load Test — {BASE}")
    print(f"Concurrent users: {CONCURRENT_USERS}, Requests per user: {REQUESTS_PER_USER}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Тест 1: Публичная страница (без авторизации)
    print("\n[Test 1] Публичная страница / (анонимные запросы)")
    start = time.time()
    with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
        futures = [executor.submit(make_request, f"{BASE}/") for _ in range(CONCURRENT_USERS * REQUESTS_PER_USER)]
        for f in as_completed(futures):
            r = f.result()
            results["times"].append(r["time"])
            if r["ok"]:
                results["success"] += 1
            else:
                results["failed"] += 1
    elapsed = time.time() - start

    total = results["success"] + results["failed"]
    avg_time = sum(results["times"]) / len(results["times"]) if results["times"] else 0
    max_time = max(results["times"]) if results["times"] else 0
    min_time = min(results["times"]) if results["times"] else 0

    print(f"  Total: {total} | Success: {results['success']} | Failed: {results['failed']}")
    print(f"  Time: {elapsed:.2f}s | Avg: {avg_time:.3f}s | Min: {min_time:.3f}s | Max: {max_time:.3f}s")
    print(f"  Throughput: {total / elapsed:.1f} req/s" if elapsed > 0 else "  Throughput: N/A")

    # Сохраняем предыдущие результаты и сбрасываем
    public_success = results["success"]
    public_failed = results["failed"]

    results["success"] = 0
    results["failed"] = 0
    results["times"] = []

    # Тест 2: Публичные страницы (без авторизации, разные URL)
    print("\n[Test 2] Публичные страницы (разные URL)")
    public_urls = [
        f"{BASE}/",
        f"{BASE}/workers",
        f"{BASE}/login",
        f"{BASE}/register",
    ]
    start = time.time()
    with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
        futures = []
        for i in range(CONCURRENT_USERS * REQUESTS_PER_USER):
            url = public_urls[i % len(public_urls)]
            futures.append(executor.submit(make_request, url))
        for f in as_completed(futures):
            r = f.result()
            results["times"].append(r["time"])
            if r["ok"]:
                results["success"] += 1
            else:
                results["failed"] += 1
    elapsed = time.time() - start

    total = results["success"] + results["failed"]
    avg_time = sum(results["times"]) / len(results["times"]) if results["times"] else 0
    max_time = max(results["times"]) if results["times"] else 0
    min_time = min(results["times"]) if results["times"] else 0

    print(f"  Total: {total} | Success: {results['success']} | Failed: {results['failed']}")
    print(f"  Time: {elapsed:.2f}s | Avg: {avg_time:.3f}s | Min: {min_time:.3f}s | Max: {max_time:.3f}s")
    print(f"  Throughput: {total / elapsed:.1f} req/s" if elapsed > 0 else "  Throughput: N/A")

    # Итог
    all_success = public_success + results["success"]
    all_failed = public_failed + results["failed"]
    all_total = all_success + all_failed
    print(f"\n{'='*60}")
    print(f"Overall: {all_success}/{all_total} passed ({all_failed} failed)")
    print(f"Load test {'PASSED' if all_failed == 0 else 'COMPLETED with errors'}")

    return all_failed == 0


if __name__ == "__main__":
    ok = run()
    import sys
    sys.exit(0 if ok else 1)
