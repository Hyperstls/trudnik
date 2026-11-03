#!/usr/bin/env python3
"""Production uptime probe for the scheduled GitHub Actions workflow.

No secrets and no third-party dependencies: checks the public health endpoint,
key pages and a static asset. Exit code 1 makes the workflow fail, which sends
the repository owner a GitHub notification.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("UPTIME_BASE_URL", "https://xn--d1aigknli.xn--p1ai").rstrip("/")
PATHS = ("/health", "/jobs", "/login", "/static/js/job-view.js")
TIMEOUT = 20


def fetch(path):
    request = urllib.request.Request(
        BASE + path, headers={"User-Agent": "trudnik-uptime/1.0"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read(20000)


def main():
    failures = []
    for path in PATHS:
        try:
            status, body = fetch(path)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failures.append("%s: %s" % (path, exc))
            print("FAIL %s: %s" % (path, exc))
            continue
        print("OK   %s: HTTP %s" % (path, status))
        if status != 200:
            failures.append("%s: HTTP %s" % (path, status))
        if path == "/health":
            try:
                payload = json.loads(body)
            except ValueError:
                failures.append("/health: not JSON")
                continue
            if payload.get("status") != "ok" or payload.get("db") is not True:
                failures.append("/health: %s" % payload)
    if failures:
        print("\nUptime check failed:")
        for failure in failures:
            print(" - " + failure)
        return 1
    print("\nAll uptime checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
