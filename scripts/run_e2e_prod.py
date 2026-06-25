"""Запуск всех E2E тестов против production (Amvera).

Использование:
    python scripts/run_e2e_prod.py
"""
import subprocess
import sys
import os
import time
import re

BASE_URL = os.environ.get("PROD_URL", "https://trudnik-hyperstls.amvera.io")
os.environ["BASE_URL"] = BASE_URL

# Список E2E тестов — полный набор из tests_e2e/
test_files = [
    "tests_e2e/test_smoke.py",
    "tests_e2e/test_e2e_scenarios.py",
    "tests_e2e/test_button_registry.py",
    "tests_e2e/test_admin_pages.py",
    "tests_e2e/test_employer_pages.py",
    "tests_e2e/test_worker_pages.py",
    "tests_e2e/test_map_geolocation.py",
    "tests_e2e/test_filters.py",
    "tests_e2e/test_ratings_reviews.py",
    "tests_e2e/test_notifications.py",
    "tests_e2e/test_performance.py",
]

total_passed = 0
total_failed = 0
results = {}

start_time = time.time()

for f in test_files:
    print(f"\n{'='*60}")
    print(f"Running: {f}")
    print(f"{'='*60}")
    result = subprocess.run(
        ["python", "-m", "pytest", f, "-v", "--tb=short", f"--base-url={BASE_URL}"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    # Парсим last line для passed/failed/errors
    lines = output.strip().split('\n')
    # Ищем строку с результатом
    final = ""
    for line in lines:
        if "passed" in line or "failed" in line or "error" in line.lower():
            final = line
    # Выводим последние строки
    for line in lines[-8:]:
        print(line)
    
    # Подсчёт
    p = re.search(r'(\d+) passed', final)
    f_match = re.search(r'(\d+) failed', final)
    e_match = re.search(r'(\d+) error', final)
    passed = int(p.group(1)) if p else 0
    failed = int(f_match.group(1)) if f_match else 0
    errors = int(e_match.group(1)) if e_match else 0
    if passed + failed + errors > 0:
        total_passed += passed
        total_failed += failed + errors
        results[f] = f"{passed} passed, {failed} failed, {errors} errors"
    else:
        # Не удалось распарсить результат — считаем провалом
        results[f] = f"PARSE_ERROR: output={final.strip()[:120]}" if final.strip() else "PARSE_ERROR: no pytest summary line"
        total_failed += 1
    
    print(f"--- {f} completed ---")

elapsed = time.time() - start_time

print("\n" + "="*60)
print("FINAL REPORT: E2E tests against PRODUCTION")
print(f"Base URL: {BASE_URL}")
print(f"Elapsed: {elapsed:.1f}s")
print("="*60)
for f, res in results.items():
    print(f"  {f}: {res}")
print(f"\nTOTAL: {total_passed} passed / {total_failed} failed")
print("="*60)

sys.exit(0 if total_failed == 0 else 1)
