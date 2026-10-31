#!/usr/bin/env python3
"""One-off production ledger reconciliation (P1-13).

The prod DB was bootstrapped out-of-band: `_migrations` stops at 066 while the
schema already contains objects from 067-149. Re-running 067 fails on
`login_user` return type, so this script:
  1. verifies a set of sentinel objects that prove the schema is current;
  2. inserts the missing 067-149 filenames into `_migrations` with checksums,
     without executing them (ON CONFLICT DO NOTHING);
  3. leaves 150+ pending for the normal apply_migrations.py run.

It never prints the DB URL. Exit 0 only if all sentinels exist and rows are
written; exit 1 otherwise (caller must stop the container).
"""
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
MIG_RE = re.compile(r"^(\d{3})[a-z]?_.*\.sql$", re.IGNORECASE)

SENTINELS = {
    "change_password(text,text)": "SELECT to_regprocedure('public.change_password(text,text)')",
    "job_photos": "SELECT to_regclass('public.job_photos')",
    "site_pages": "SELECT to_regclass('public.site_pages')",
    "sync_user_skills(uuid,uuid[])": "SELECT to_regprocedure('public.sync_user_skills(uuid,uuid[])')",
    "expire_unfilled_jobs()": "SELECT to_regprocedure('public.expire_unfilled_jobs()')",
    "delete_user_cascade(uuid)": "SELECT to_regprocedure('public.delete_user_cascade(uuid)')",
    "notification_outbox": "SELECT to_regclass('public.notification_outbox')",
    "push_subscriptions": "SELECT to_regclass('public.push_subscriptions')",
}


def main() -> int:
    url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL", "")
    if not url:
        print("RECONCILE: DATABASE_ADMIN_URL/DATABASE_URL is not set", file=sys.stderr)
        return 2

    files = sorted(
        p.name for p in (ROOT / "migrations").iterdir()
        if p.is_file() and MIG_RE.match(p.name)
    )
    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS _migrations ("
                "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now(), checksum TEXT)"
            )
            cur.execute("SELECT filename FROM _migrations")
            applied = {row[0] for row in cur.fetchall()}

            for name, sql in SENTINELS.items():
                cur.execute(sql)
                present = cur.fetchone()[0]
                print("SENTINEL %s: %s" % (name, "ok" if present else "MISSING"))
                if not present:
                    print("RECONCILE: ABORT — schema sentinel missing, no rows written")
                    return 1

            target = []
            for name in files:
                match = MIG_RE.match(name)
                if not match:
                    continue
                number = int(match.group(1))
                if 67 <= number <= 149 and name not in applied:
                    target.append(name)

            for name in target:
                checksum = hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest()
                cur.execute(
                    "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s) "
                    "ON CONFLICT (filename) DO NOTHING",
                    (name, checksum),
                )
            print(
                "RECONCILE: files=%d applied_before=%d inserted_067_149=%d deferred_150_plus=%s"
                % (len(files), len(applied), len(target),
                   [n for n in files if int(MIG_RE.match(n).group(1)) >= 150])
            )
    finally:
        conn.close()
    print("RECONCILE: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
