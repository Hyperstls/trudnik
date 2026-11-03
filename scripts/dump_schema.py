#!/usr/bin/env python3
"""Regenerate tests/fixtures/schema.sql from the local Docker database (J140).

Schema-only dump (no rows), self-contained roles for RLS policies. Run after
SQL migrations/schema changes, then commit the fixture:

    .venv\\Scripts\\python.exe scripts/dump_schema.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "djadmin"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

ROLES = """-- CI fixture: roles referenced by RLS policies.
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;

"""


def main():
    db = settings.DATABASES["default"]
    env = dict(os.environ)
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = db["PASSWORD"]
    command = [
        "docker", "exec", "-e", "PGPASSWORD",
        os.getenv("SCHEMA_DUMP_CONTAINER", "trudnik-db"),
        "pg_dump", "-U", db["USER"], "-d", db["NAME"],
        "--schema-only", "--no-owner", "--no-privileges",
    ]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if process.returncode != 0:
        print(process.stderr.decode("utf-8", "replace")[-1000:], file=sys.stderr)
        return 1
    target = ROOT / "tests" / "fixtures" / "schema.sql"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(ROLES.encode() + process.stdout)
    print("wrote %s (%.1f KiB)" % (target, target.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
