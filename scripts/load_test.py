"""Безопасный smoke-нагрузочный сценарий: только GET, 100 запросов при P=8.

Прод-режим требует --confirm-prod и разрешён только для https и host из allowlist.
Скрипт не отправляет формы, куки и токены; жёсткий cap — 500 запросов.

Примеры:
    python scripts/load_test.py --self-test
    python scripts/load_test.py --base-url https://xn--d1aigknli.xn--p1ai --confirm-prod
"""
from __future__ import annotations

import argparse
import http.server
import math
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

PROD_HOSTS = {"xn--d1aigknli.xn--p1ai", "трудник.рф"}
HARD_CAP = 500
USER_AGENT = "trudnik-load-test/1.0"
# Только стабильные публичные 200-страницы: / — 302 на /jobs,
# /employers и /my-* требуют входа; /workers публичен, но в дефолт не входит.
DEFAULT_PATHS = "/jobs,/jobs?page=2,/health"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Не уходим по редиректам: цель ограничена allowlist, 3xx считаем non-2xx."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, timeout: float) -> tuple[int, float, str | None]:
    request = urllib.request.Request(
        url, method="GET",
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"},
    )
    started = time.perf_counter()
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            response.read()  # читаем тело целиком: latency = полный ответ
            return response.status, time.perf_counter() - started, None
    except urllib.error.HTTPError as exc:
        # HTTP-статус вне 2xx — это ответ сервера, а не сетевая ошибка.
        return exc.code, time.perf_counter() - started, None
    except Exception as exc:  # noqa: BLE001 — транспортная ошибка = провал запроса
        return 0, time.perf_counter() - started, type(exc).__name__


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank перцентиль (без интерполяции)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(p / 100.0 * len(ordered)) - 1))
    return ordered[index]


def run_load(base_url: str, paths: list[str], requests_n: int,
             concurrency: int, timeout: float) -> int:
    base = base_url.rstrip("/")
    urls = [base + (path if path.startswith("/") else "/" + path) for path in paths]
    targets = [urls[i % len(urls)] for i in range(requests_n)]

    started = time.perf_counter()
    results: list[tuple[int, float, str | None]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(fetch, url, timeout) for url in targets]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started

    latencies = [latency * 1000 for _, latency, _ in results]
    ok = sum(1 for status, _, error in results if error is None and 200 <= status < 300)
    non2xx = sum(1 for status, _, error in results if error is None and not 200 <= status < 300)
    errors = sum(1 for _, _, error in results if error is not None)
    error_names = sorted({error for _, _, error in results if error})
    failed = non2xx + errors
    status_counts = Counter(status for status, _, _ in results)
    codes = "  ".join(f"{code}:{count}" for code, count in sorted(status_counts.items()))

    rps = requests_n / elapsed if elapsed > 0 else 0.0
    print(f"target:     {base}")
    print(f"requests:   {requests_n}  concurrency: {concurrency}  "
          f"duration: {elapsed:.2f}s  rps: {rps:.1f}")
    print(f"total: {requests_n}  ok: {ok}  failed: {failed}  non2xx: {non2xx}  errors: {errors}")
    print(f"status:     {codes}")
    if error_names:
        print("error types: " + ", ".join(error_names))
    print(
        "latency ms: "
        f"p50={percentile(latencies, 50):.0f} "
        f"p90={percentile(latencies, 90):.0f} "
        f"p95={percentile(latencies, 95):.0f} "
        f"p99={percentile(latencies, 99):.0f} "
        f"max={max(latencies):.0f}"
    )
    if non2xx or errors:
        print("FAIL: есть non-2xx или сетевые ошибки", file=sys.stderr)
        return 1
    return 0


def _start_local_server() -> tuple[http.server.ThreadingHTTPServer, str]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # тишина в self-test
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="", help="https://<host> (только прод-allowlist)")
    parser.add_argument("--requests", type=int, default=100, help="всего GET-запросов (cap 500)")
    parser.add_argument("--concurrency", type=int, default=8, help="параллельных воркеров (1..32)")
    parser.add_argument("--paths", default=DEFAULT_PATHS,
                        help="список публичных GET-путей через запятую")
    parser.add_argument("--timeout", type=float, default=10.0, help="таймаут запроса, секунд")
    parser.add_argument("--confirm-prod", action="store_true",
                        help="подтверждение запуска против production в согласованное окно")
    parser.add_argument("--self-test", action="store_true",
                        help="локальный http.server: 100 запросов, P=8, без сети и прода")
    args = parser.parse_args()

    if args.timeout <= 0:
        print("FAIL: --timeout должен быть > 0", file=sys.stderr)
        return 2
    if not 1 <= args.concurrency <= 32:
        print("FAIL: --concurrency должен быть 1..32", file=sys.stderr)
        return 2
    if not 1 <= args.requests <= HARD_CAP:
        print(f"FAIL: --requests должен быть 1..{HARD_CAP}", file=sys.stderr)
        return 2
    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    if not paths or any(not p.startswith("/") for p in paths):
        print("FAIL: --paths должен содержать пути, начинающиеся с /", file=sys.stderr)
        return 2

    if args.self_test:
        # self-test всегда доказывает ровно контрактные 100 запросов при P=8
        server, base_url = _start_local_server()
        try:
            code = run_load(base_url, ["/"], 100, 8, args.timeout)
        finally:
            server.shutdown()
            server.server_close()
        if code != 0:
            print("SELF-TEST FAIL", file=sys.stderr)
            return 1
        print("SELF-TEST OK")
        return 0

    parsed = urllib.parse.urlsplit(args.base_url)
    if parsed.scheme != "https" or parsed.hostname not in PROD_HOSTS:
        print(
            "REFUSED: прод-режим только https и host из allowlist "
            f"({', '.join(sorted(PROD_HOSTS))}); для локальной проверки — --self-test",
            file=sys.stderr,
        )
        return 2
    if not args.confirm_prod:
        print(
            "REFUSED: нужен --confirm-prod — нагрузка допустима только в согласованное окно",
            file=sys.stderr,
        )
        return 2

    return run_load(args.base_url, paths, args.requests, args.concurrency, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
