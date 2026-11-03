#!/usr/bin/env python3
"""Launch-readiness preflight for the public Trudnik deployment (J138).

Checks public pages, security headers, TLS, sitemap/robots and email DNS.
No secrets are required and nothing is modified.

Usage:
    python scripts/launch_check.py
    python scripts/launch_check.py --base-url https://example.test

Exit code 1 only for application/TLS/security failures; email/DNS findings are
warnings for the owner (they depend on the domain registrar/mail provider).
"""
import argparse
import json
import ssl
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

PAGES = (
    "/health",
    "/jobs",
    "/login",
    "/privacy",
    "/terms",
    "/safety",
    "/faq",
    "/sitemap.xml",
    "/robots.txt",
    "/static/manifest.json",
    "/sw.js",
    "/static/js/job-view.js",
)
EMAIL_DOMAINS = ("trudnik.ru", "xn--d1aigknli.xn--p1ai")
DKIM_SELECTORS = ("default", "mail", "smtp", "yandex", "amvera", "selector1", "selector2")


def fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "trudnik-launch-check/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers), response.read(50000)


def dns(name, rtype):
    url = "https://dns.google/resolve?name=%s&type=%s" % (name, rtype)
    try:
        _, _, body = fetch(url)
        return json.loads(body).get("Answer", [])
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return []


def txt_records(name):
    return [answer.get("data", "").strip('"') for answer in dns(name, "TXT")]


def tls_days(host):
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=15) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://xn--d1aigknli.xn--p1ai")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    host = urlparse(base).hostname
    failures = []
    warnings = []

    print("== Application ==")
    for path in PAGES:
        try:
            status, headers, body = fetch(base + path)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print("FAIL %-28s %s" % (path, exc))
            failures.append(path)
            continue
        ok = 200 <= status < 400
        print("%s %-28s HTTP %s" % ("PASS" if ok else "FAIL", path, status))
        if not ok:
            failures.append(path)
            continue
        if path == "/health":
            try:
                payload = json.loads(body)
                if payload.get("status") != "ok" or payload.get("db") is not True:
                    print("FAIL /health payload: %s" % payload)
                    failures.append("/health payload")
            except ValueError:
                print("FAIL /health: not JSON")
                failures.append("/health json")
        if path == "/sitemap.xml" and b"<urlset" not in body:
            print("FAIL /sitemap.xml: no urlset")
            failures.append("/sitemap.xml")
        if path == "/robots.txt" and b"Sitemap:" not in body:
            print("WARN /robots.txt: no Sitemap directive")
            warnings.append("robots sitemap directive")
        print("     headers: CSP=%s HSTS=%s XCTO=%s Ref=%s Perm=%s" % (
            "yes" if "content-security-policy" in headers else "no",
            "yes" if "strict-transport-security" in headers else "no",
            "yes" if "x-content-type-options" in headers else "no",
            "yes" if "referrer-policy" in headers else "no",
            "yes" if "permissions-policy" in headers else "no",
        ))
        for name in ("content-security-policy", "strict-transport-security",
                     "x-content-type-options", "referrer-policy", "permissions-policy"):
            if name not in headers:
                failures.append("header " + name)

    print("\n== TLS ==")
    try:
        days = tls_days(host)
        print("PASS certificate expires in %s days" % days)
        if days < 30:
            warnings.append("TLS expires in %s days" % days)
    except (OSError, ssl.SSLError, ValueError) as exc:
        print("FAIL TLS: %s" % exc)
        failures.append("TLS")

    print("\n== Email DNS (owner action) ==")
    for domain in EMAIL_DOMAINS:
        records = txt_records(domain)
        spf = [record for record in records if record.lower().startswith("v=spf1")]
        print("%s SPF: %s" % (domain, spf[0] if spf else "MISSING"))
        if not spf:
            warnings.append("SPF missing for " + domain)
        dmarc = [record for record in txt_records("_dmarc." + domain)
                 if record.lower().startswith("v=dmarc1")]
        print("%s DMARC: %s" % (domain, dmarc[0] if dmarc else "MISSING"))
        if not dmarc:
            warnings.append("DMARC missing for " + domain)
        mx = dns(domain, "MX")
        exchanges = [answer.get("data", "") for answer in mx]
        print("%s MX: %s" % (domain, exchanges or "NONE"))
        if any("blackhole" in exchange.lower() for exchange in exchanges):
            warnings.append("MX blackhole for " + domain)
        if not any(
            txt_records(selector + "._domainkey." + domain)
            for selector in DKIM_SELECTORS
        ):
            warnings.append("DKIM not found for " + domain)

    print("\n== Result ==")
    if failures:
        print("FAILURES: %s" % ", ".join(failures))
    if warnings:
        print("WARNINGS (owner): %s" % ", ".join(warnings))
    if failures:
        return 1
    print("PASS with %d warning(s)" % len(warnings) if warnings else "ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
