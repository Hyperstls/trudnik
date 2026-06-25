"""
Script to reset users on Trudnik (Amvera) via the /api/reset-users endpoint.

The endpoint is protected by X-Admin-Token (SECRET_KEY) and bypasses CSRF.

Usage:
    python manage_users.py [SECRET_KEY]

Requires: pip install requests
"""

import sys
import time

import requests

# Fix Unicode on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_URL = "https://trudnik-hyperstls.amvera.io"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def try_reset(token: str) -> dict:
    """Call the /api/reset-users endpoint."""
    log("Calling POST /api/reset-users...")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/reset-users",
            headers={
                "X-Admin-Token": token,
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        log(f"   Status: {resp.status_code}")

        if resp.status_code == 401:
            log("[ERROR] Unauthorized - wrong SECRET_KEY")
            return {"success": False, "error": "Unauthorized"}
        if resp.status_code == 400:
            log(f"[ERROR] Bad Request: {resp.text[:300]}")
            return {"success": False, "error": resp.text[:200]}
        if not resp.ok:
            log(f"[ERROR] HTTP {resp.status_code}: {resp.text[:300]}")
            return {"success": False, "error": f"HTTP {resp.status_code}"}

        return resp.json()
    except Exception as e:
        log(f"[ERROR] {e}")
        return {"success": False, "error": str(e)}


def print_result(data: dict):
    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)

    ok = data.get('success')
    print(f"[{'OK' if ok else 'WARN'}] Success: {ok}")
    print(f"   Deleted:  {data.get('deleted', 0)}")
    print(f"   Failed:   {data.get('delete_failed', 0)}")

    for u in data.get('created', []):
        print(f"   Created:  {u.get('email', '?')} ({u.get('role', '?')})")
    for e in data.get('create_failed', []):
        print(f"   Failed:   {e}")
    for e in data.get('errors', []):
        print(f"   Error:    {e}")

    final = data.get('final_users', [])
    print(f"\n   Final users ({data.get('final_count', len(final))}):")
    for u in final:
        print(f"      * {u.get('email', '?')} [{u.get('role', '?')}]")

    expected = {'admin@test.ru', 'org@test.ru', 'trud@test.ru'}
    actual = {u['email'] for u in final}
    if expected == actual:
        print("\n[OK] All three users are in place!")
    else:
        if missing := expected - actual:
            print(f"\n[ERR] Missing: {missing}")
        if extra := actual - expected:
            print(f"[WARN] Extra: {extra}")


def main():
    log("=" * 60)
    log(">>> Trudnik User Reset Script")
    log(f"    URL: {BASE_URL}")
    log("=" * 60)

    token = sys.argv[1] if len(sys.argv) > 1 else "***REMOVED***"
    log(f"Token: {token}")

    result = try_reset(token)
    print_result(result)
    return 0 if result.get('success') else 1


if __name__ == "__main__":
    sys.exit(main())
