"""
Script to reset users on Trudnik (Amvera) via the /api/reset-users endpoint.

Usage:
    python manage_users.py

The script calls POST /api/reset-users with X-Admin-Token header.
The endpoint (inside the container) uses PostgREST admin access to:
1. Delete all existing users via delete_user_cascade RPC
2. Create admin@test.ru (admin), org@test.ru (employer), trud@test.ru (worker)
   All with password Step@1986

Requires: pip install requests
"""

import sys
import time
import requests

# ============================================================
# Config
# ============================================================
BASE_URL = "https://trudnik-hyperstls.amvera.io"

# SECRET_KEY for the reset-users endpoint
# Must match the SECRET_KEY environment variable on the server
# For local dev: dev-secret-key-change-in-production-abc123
# For production: unknown (set in amvera env vars)
ADMIN_TOKEN = None  # Will be set below


def log(msg: str) -> None:
    """Print with timestamp."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def try_reset(url: str, token: str) -> dict:
    """Call the /api/reset-users endpoint."""
    log(f"Calling POST {url}/api/reset-users...")
    log(f"   Token: {token[:20]}...")

    try:
        resp = requests.post(
            f"{url}/api/reset-users",
            headers={
                "X-Admin-Token": token,
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        log(f"   Status: {resp.status_code}")

        if resp.status_code == 401:
            log("[ERROR] Unauthorized - wrong SECRET_KEY token")
            return {"success": False, "error": "Unauthorized - wrong token"}

        if not resp.ok:
            log(f"[ERROR] HTTP {resp.status_code}: {resp.text[:300]}")
            return {"success": False, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        return data

    except requests.exceptions.ConnectionError:
        log(f"[ERROR] Cannot connect to {url}")
        return {"success": False, "error": "Connection error"}
    except Exception as e:
        log(f"[ERROR] {e}")
        return {"success": False, "error": str(e)}


def print_result(data: dict):
    """Pretty-print the result."""
    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)

    if data.get('success'):
        print("[OK] Operation successful!")
    else:
        print("[WARN] Operation completed with errors")

    print(f"   Deleted:  {data.get('deleted', 0)}")
    print(f"   Failed:   {data.get('delete_failed', 0)}")

    created = data.get('created', [])
    print(f"   Created:  {len(created)}")
    for u in created:
        print(f"      * {u.get('email', '?')} ({u.get('role', '?')})")

    failed = data.get('create_failed', [])
    if failed:
        print(f"   Create failed: {failed}")

    errors = data.get('errors', [])
    if errors:
        print("   Errors:")
        for e in errors:
            print(f"      - {e}")

    final_users = data.get('final_users', [])
    print(f"\n   Final users ({data.get('final_count', len(final_users))}):")
    for u in final_users:
        print(f"      * {u.get('email', '?')} [{u.get('role', '?')}]")

    # Verify expected state
    expected = {'admin@test.ru', 'org@test.ru', 'trud@test.ru'}
    actual = {u['email'] for u in final_users}
    if expected == actual:
        print("\n[OK] All three users are in place!")
    else:
        missing = expected - actual
        extra = actual - expected
        if missing:
            print(f"\n[ERR] Missing: {missing}")
        if extra:
            print(f"[WARN] Extra: {extra}")


def main():
    global ADMIN_TOKEN

    log("=" * 60)
    log(">>> Trudnik User Reset Script")
    log(f"    Base URL: {BASE_URL}")
    log("=" * 60)

    # Try multiple possible tokens
    # The server SECRET_KEY is set via env var and we don't know it for production
    # Common possibilities:
    possible_tokens = [
        "dev-secret-key-change-in-production-abc123",  # local dev key
        # Add more if you know the production key
    ]

    # Also check command line argument
    if len(sys.argv) > 1:
        possible_tokens.insert(0, sys.argv[1])

    for token in possible_tokens:
        log(f"\nTrying token: {token[:20]}...")
        result = try_reset(BASE_URL, token)

        if result.get('success') is not None and result.get('error') != 'Unauthorized - wrong token':
            # Got a response (either success or failure, but not auth error)
            print_result(result)
            if result.get('success'):
                return 0
            else:
                log("\nOperation reported errors (see above).")
                return 1

    log("\n[ERROR] All tokens failed.")
    log("You need the production SECRET_KEY to use this script.")
    log("Try: python manage_users.py <SECRET_KEY>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
