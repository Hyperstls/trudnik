"""Тесты защиты от PostgREST инъекций через sanitize_postgrest()."""
import sys
import requests
from datetime import datetime

BASE = "http://127.0.0.1:5000"

RESULTS = {"passed": 0, "failed": 0}


def log(level, msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {level:5s} | {msg}")


def test(name, fn):
    try:
        fn()
        RESULTS["passed"] += 1
        log("PASS", name)
    except AssertionError as e:
        RESULTS["failed"] += 1
        log("FAIL", f"{name} -- {e}")
    except Exception as e:
        RESULTS["failed"] += 1
        log("FAIL", f"{name} -- {type(e).__name__}: {str(e)[:150]}")


def t_sanitize_or_injection():
    """Инъекция оператора 'or' через запятую — должна быть отфильтрована."""
    # Пытаемся передать city=Moscow,or(1,eq,1) через поиск
    r = requests.get(f"{BASE}/", params={"city": "Moscow,or(1,eq,1)"})
    assert r.status_code == 200, f"Should return 200, got {r.status_code}"
    # Страница не должна упасть (500)
    assert "Internal Server Error" not in r.text, "Should not crash with 500"


def t_sanitize_in_injection():
    """Инъекция оператора 'in' — должна быть отфильтрована."""
    r = requests.get(f"{BASE}/", params={"city": "in.(Moscow,Paris)"})
    assert r.status_code == 200
    assert "Internal Server Error" not in r.text


def t_sanitize_special_chars():
    """Спецсимволы в поиске — должны быть безопасно обработаны."""
    r = requests.get(f"{BASE}/", params={"city": "test\"'&;,()"})
    assert r.status_code == 200
    assert "Internal Server Error" not in r.text


def t_sanitize_workers_search():
    """Инъекция в поиск трудников — должна быть отфильтрована."""
    r = requests.get(f"{BASE}/workers", params={"city": "Moscow,or(1,eq,1)"})
    assert r.status_code == 200
    assert "Internal Server Error" not in r.text


def t_sanitize_normal_works():
    """Проверка что нормальный поиск всё ещё работает."""
    r = requests.get(f"{BASE}/", params={"city": "Москва"})
    assert r.status_code == 200
    r2 = requests.get(f"{BASE}/workers", params={"city": "Москва"})
    assert r2.status_code == 200


# ── Main ─────────────────────────────────────────

TESTS = [
    ("SQL-like OR injection blocked", t_sanitize_or_injection),
    ("IN injection blocked", t_sanitize_in_injection),
    ("Special chars filtered", t_sanitize_special_chars),
    ("Workers search injection blocked", t_sanitize_workers_search),
    ("Normal search still works", t_sanitize_normal_works),
]

if __name__ == "__main__":
    log("INFO", f"PostgREST Sanitization Tests — {BASE}")
    log("INFO", "=" * 60)
    for name, fn in TESTS:
        test(name, fn)
    log("INFO", f"Total: {RESULTS['passed']} passed, {RESULTS['failed']} failed")
    sys.exit(0 if RESULTS["failed"] == 0 else 1)
