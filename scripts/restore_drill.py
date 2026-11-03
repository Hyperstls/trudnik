#!/usr/bin/env python3
"""Verified local restore drill (J137).

Copies the local Django database into a scratch database inside the same
PostgreSQL container, restores it, and compares row counts / schema markers.
The target must contain ``drill`` in its name; the source database is never
modified.

Example:
    .venv\\Scripts\\python.exe scripts\\restore_drill.py --drop-target

Production restore is a separate owner-run procedure: never point this script
at the production database (see docs/RESTORE_DRILL.md).
"""
import argparse
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

TABLES = ("profiles", "jobs", "applications", "messages", "notifications", "site_pages", "skills")
DB = settings.DATABASES["default"]
DB_NAME = DB["NAME"]
DB_USER = DB["USER"]
DB_PASSWORD = DB.get("PASSWORD") or ""


def _docker(container, password, args, input_bytes=None):
    env = dict(os.environ)
    if password:
        env["PGPASSWORD"] = password
    command = ["docker", "exec"]
    if input_bytes is not None:
        command.append("-i")
    if password:
        command += ["-e", "PGPASSWORD"]
    command += [container] + args
    process = subprocess.run(
        command,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("%s failed: %s" % (args[0], stderr[-1200:]))
    return process.stdout


def psql(container, password, db, sql):
    return _docker(
        container, password,
        ["psql", "-U", DB_USER, "-d", db, "-tAc", sql],
    ).decode("utf-8", "replace").strip()


def scalar(container, password, db, sql):
    value = psql(container, password, db, sql)
    return int(value) if value else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default=os.getenv("RESTORE_DRILL_CONTAINER", "trudnik-db"))
    parser.add_argument("--source-db", default=DB_NAME)
    parser.add_argument("--target-db", default=DB_NAME + "_restore_drill")
    parser.add_argument("--recreate-target", action="store_true")
    parser.add_argument("--drop-target", action="store_true")
    args = parser.parse_args()

    password = DB_PASSWORD

    if "drill" not in args.target_db.lower():
        raise SystemExit("refusing: target database name must contain 'drill'")
    if args.target_db == args.source_db:
        raise SystemExit("refusing: target equals source")

    exists = scalar(
        args.container, password, "postgres",
        "SELECT 1 FROM pg_database WHERE datname = '%s'" % args.target_db,
    )
    if exists and not args.recreate_target:
        raise SystemExit(
            "target %s already exists; pass --recreate-target to replace it" % args.target_db
        )
    if exists:
        _docker(args.container, password, ["dropdb", "-U", DB_USER, args.target_db])
    _docker(args.container, password, ["createdb", "-U", DB_USER, args.target_db])

    print("dump %s -> %s" % (args.source_db, args.target_db))
    dump = _docker(
        args.container, password,
        ["pg_dump", "-U", DB_USER, "-d", args.source_db, "-Fc"],
    )
    print("dump size: %.1f KiB" % (len(dump) / 1024))
    _docker(
        args.container, password,
        ["pg_restore", "-U", DB_USER, "-d", args.target_db, "--no-owner", "--no-privileges"],
        input_bytes=dump,
    )

    failures = []
    for table in TABLES:
        source = scalar(args.container, password, args.source_db, "SELECT count(*) FROM %s" % table)
        target = scalar(args.container, password, args.target_db, "SELECT count(*) FROM %s" % table)
        status = "OK" if source == target else "MISMATCH"
        print("%-14s source=%-8s target=%-8s %s" % (table, source, target, status))
        if source != target:
            failures.append(table)

    postgis = scalar(
        args.container, password, args.target_db,
        "SELECT count(*) FROM pg_extension WHERE extname = 'postgis'",
    )
    rls = scalar(
        args.container, password, args.target_db,
        "SELECT count(*) FROM pg_class WHERE relname = 'profiles' AND relrowsecurity",
    )
    functions = scalar(
        args.container, password, args.target_db,
        "SELECT count(*) FROM pg_proc WHERE proname IN "
        "('apply_job_atomic', 'accept_application', 'withdraw_application_atomic')",
    )
    print("postgis extension: %s" % ("OK" if postgis else "MISSING"))
    print("profiles RLS: %s" % ("OK" if rls else "MISSING"))
    print("RPC functions: %s" % functions)
    if not postgis or not rls or functions < 3:
        failures.append("schema")

    if args.drop_target:
        _docker(args.container, password, ["dropdb", "-U", DB_USER, args.target_db])
        print("target dropped")

    if failures:
        print("\nRESTORE DRILL FAILED: %s" % ", ".join(failures))
        return 1
    print("\nRESTORE DRILL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
