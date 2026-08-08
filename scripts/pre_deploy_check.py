#!/usr/bin/env python3
"""Pre-deploy check: ловит системные баги ДО деплоя на Amvera.

Запуск: python scripts/pre_deploy_check.py
Возвращает exit code 0 (всё ок) или 1 (есть проблемы).

Проверяет:
  1. py_compile всех .py файлов
  2. CSP nonce: все <script> в шаблонах имеют nonce
  3. Inline event handlers: нет onclick/onchange/onsubmit в HTML
  4. profiles select=: все PostgREST-запросы profiles? имеют select=
  5. current_app.logger в Celery tasks: не использовать вне request-context
  6. Двойные атрибуты: нет duplicate class= на одном элементе
"""
import re
import sys
import os
import subprocess
import pathlib

# Force UTF-8 output (Windows console fix)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = pathlib.Path(__file__).parent.parent
ERRORS = []


def err(msg):
    ERRORS.append(msg)
    print(f"  [FAIL] {msg}")


def ok(msg):
    print(f"  [PASS] {msg}")


def check_py_compile():
    """1. py_compile всех .py файлов."""
    print("\n[1/6] py_compile...")
    py_files = list(ROOT.glob("app/**/*.py")) + list(ROOT.glob("tests/**/*.py"))
    py_files = [f for f in py_files if "__pycache__" not in str(f)]
    failed = []
    for f in py_files:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failed.append(str(f.relative_to(ROOT)))
    if failed:
        err(f"py_compile failed: {', '.join(failed)}")
    else:
        print(f"  ✅ {len(py_files)} files compile OK")


def check_csp_nonce():
    """2. Все <script> в шаблонах должны иметь nonce."""
    print("\n[2/6] CSP nonce check...")
    tpl_dir = ROOT / "templates"
    for f in tpl_dir.rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<script(?![^>]*nonce=)[^>]*>', content):
            line = content[:m.start()].count("\n") + 1
            err(f"{f.relative_to(ROOT)}:{line} <script> without nonce")
    if not any("nonce" in e for e in ERRORS[-3:]):
        print("  ✅ All <script> tags have nonce")


def check_inline_handlers():
    """3. Нет inline onclick/onchange/onsubmit/onload в HTML (CSP strict-dynamic)."""
    print("\n[3/6] Inline event handlers (CSP strict-dynamic)...")
    tpl_dir = ROOT / "templates"
    found = False
    for f in tpl_dir.rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'\son(click|change|submit|load|error|mouseover)\s*=', content):
            line = content[:m.start()].count("\n") + 1
            snippet = content.split("\n")[line - 1].strip()[:60]
            err(f"{f.relative_to(ROOT)}:{line} inline {m.group(0).strip()}: {snippet}")
            found = True
    if not found:
        print("  ✅ No inline event handlers")


def check_profiles_select():
    """4. Все profiles? запросы через user-JWT должны иметь select=.
    Примечание: postgrest_admin_request (service_role) обходят RLS — select= не нужен.
    Также PATCH/POST обрабатываются _normalize_endpoint автоматически."""
    print("\n[4/6] profiles select= check (user-JWT only)...")
    app_dir = ROOT / "app"
    found = False
    for f in app_dir.rglob("*.py"):
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if "profiles?" not in line:
                continue
            if "select=" in line:
                continue
            if "postgrest_admin_request" in line or "admin_request" in line:
                continue
            if "postgrest_rpc" in line:
                continue
            if "PATCH" in line or "'POST'" in line or '"POST"' in line:
                continue  # _normalize_endpoint handles mutations
            if "admin" in str(f.relative_to(ROOT)).replace("\\", "/").lower():
                continue  # admin blueprints use service_role
            rel = str(f.relative_to(ROOT))
            err(f"{rel}:{i} profiles query without select= (user-JWT): {line.strip()[:70]}")
            found = True
    if not found:
        print("  [PASS] All user-JWT profiles queries have select=")


def check_current_app_in_tasks():
    """5. Celery tasks не должны использовать current_app.logger."""
    print("\n[5/6] current_app.logger in Celery tasks...")
    tasks_dir = ROOT / "app" / "tasks"
    found = False
    for f in tasks_dir.glob("*.py"):
        content = f.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            if "current_app.logger" in line and "import" not in line and "#" not in line.split("current_app")[0]:
                err(f"{f.relative_to(ROOT)}:{i} current_app.logger in Celery task (use module logger)")
                found = True
    if not found:
        print("  ✅ No current_app.logger in Celery tasks")


def check_duplicate_attributes():
    """6. Нет дублирующихся атрибутов (например, два class= на одном элементе)."""
    print("\n[6/6] Duplicate HTML attributes...")
    tpl_dir = ROOT / "templates"
    found = False
    for f in tpl_dir.rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<\w+[^>]*>', content):
            tag = m.group(0)
            attrs = re.findall(r'\s(\w[\w-]*)=', tag)
            seen = set()
            for a in attrs:
                if a in seen:
                    line = content[:m.start()].count("\n") + 1
                    err(f"{f.relative_to(ROOT)}:{line} duplicate attribute: {a}")
                    found = True
                    break
                seen.add(a)
    if not found:
        print("  ✅ No duplicate attributes")


def main():
    print("=" * 60)
    print("  PRE-DEPLOY CHECK — Trudnik")
    print("=" * 60)

    check_py_compile()
    check_csp_nonce()
    check_inline_handlers()
    check_profiles_select()
    check_current_app_in_tasks()
    check_duplicate_attributes()

    print("\n" + "=" * 60)
    if ERRORS:
        print(f"  ❌ {len(ERRORS)} problem(s) found. Fix before deploy!")
        for e in ERRORS:
            print(f"     • {e}")
        sys.exit(1)
    else:
        print("  ✅ ALL CHECKS PASSED. Safe to deploy.")
        sys.exit(0)


if __name__ == "__main__":
    main()
