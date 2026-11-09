#!/usr/bin/env python3
"""Production uptime probe for the scheduled GitHub Actions workflow.

No secrets and no third-party dependencies: checks the public health endpoint,
key pages and a static asset. Exit code 1 makes the workflow fail, which sends
the repository owner a GitHub notification.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.getenv("UPTIME_BASE_URL", "https://xn--d1aigknli.xn--p1ai").rstrip("/")
PATHS = ("/health", "/jobs", "/login", "/static/js/job-view.js")
TIMEOUT = 10
ATTEMPTS = 3
RETRY_DELAY = 1.5
# Деплой/старт БД занимает 1–3 минуты: после первого провала ждём и повторяем
# весь набор, иначе каждый redeploy открывает ложный инцидент.
GLOBAL_RETRY_DELAY = float(os.getenv("UPTIME_GLOBAL_RETRY_DELAY", "90"))


def fetch(path):
    """Fetch with retries: Amvera ingress sometimes resets TLS on a single try."""
    request = urllib.request.Request(
        BASE + path, headers={"User-Agent": "trudnik-uptime/1.0"}
    )
    last_error = None
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                if response.status < 500:
                    return response.status, response.read(20000)
                last_error = "HTTP %s" % response.status
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt + 1 < ATTEMPTS:
            time.sleep(RETRY_DELAY)
    if isinstance(last_error, Exception):
        raise last_error
    raise OSError(last_error or "request failed")


def run_checks():
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
    return failures


def main():
    failures = run_checks()
    if failures and GLOBAL_RETRY_DELAY > 0:
        print(
            "\nFirst pass failed; retrying in %.0fs (deploy window)..."
            % GLOBAL_RETRY_DELAY
        )
        time.sleep(GLOBAL_RETRY_DELAY)
        failures = run_checks()
    if failures:
        print("\nUptime check failed:")
        for failure in failures:
            print(" - " + failure)
        return 1
    print("\nAll uptime checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
