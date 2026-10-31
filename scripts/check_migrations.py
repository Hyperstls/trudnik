#!/usr/bin/env python3
"""Read-only deployment gate: migrations ledger + auth DB invariants.

Checks:
  1. every numbered migrations/*.sql is recorded in _migrations;
  2. profiles.email_verified default is false (fail-closed);
  3. change_password(text, text) exists (password-reset overload, migration 149).

Usage:
    DATABASE_ADMIN_URL=postgresql://... python scripts/check_migrations.py

Exit codes: 0 = OK, 1 = invariant violated, 2 = config/connection error.
No secrets are printed.
"""
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 is not installed", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
MIG_RE = re.compile(r"^\d{3}[a-z]?_.*\.sql$", re.IGNORECASE)


def _load_dotenv() -> None:
    """Load .env without overriding already-set process env."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _database_url() -> str:
    """DATABASE_ADMIN_URL/DATABASE_URL; map compose alias db→localhost:5433."""
    _load_dotenv()
    url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL", "")
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.hostname == "db" and parts.port in (None, 5432):
        userinfo = parts.netloc.rpartition("@")[0]
        if userinfo:
            userinfo += "@"
        url = urlunsplit(
            (parts.scheme, "%slocalhost:5433" % userinfo, parts.path, parts.query, parts.fragment)
        )
    return url


def main() -> int:
    files = sorted(
        p.name for p in (ROOT / "migrations").iterdir()
        if p.is_file() and MIG_RE.match(p.name)
    )
    url = _database_url()
    if not url:
        print("ERROR: DATABASE_ADMIN_URL or DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        conn = psycopg2.connect(url, connect_timeout=10)
    except Exception as exc:
        print("ERROR: DB connection failed: %s" % exc, file=sys.stderr)
        return 2

    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT filename FROM _migrations")
            applied = {row[0] for row in cur.fetchall()}
            pending = [name for name in files if name not in applied]

            cur.execute(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='profiles' "
                "AND column_name='email_verified'"
            )
            row = cur.fetchone()
            email_default = row[0] if row else None

            cur.execute(
                "SELECT to_regprocedure('public.change_password(text,text)')"
            )
            reset_fn = cur.fetchone()[0]
    finally:
        conn.close()

    plan = {
        "files": len(files),
        "applied": len(applied),
        "pending": len(pending),
        "email_verified_default": email_default,
        "reset_rpc": "present" if reset_fn else "MISSING",
    }
    print("migrations:", plan)
    for name in pending:
        print("  PENDING:", name)

    ok = (
        not pending
        and email_default in ("false", "false::boolean")
        and bool(reset_fn)
    )
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
