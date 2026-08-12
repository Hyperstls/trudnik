#!/usr/bin/env python3
"""Pre-deploy check: ловит системные баги ДО деплоя на Amvera.

Запуск: python scripts/pre_deploy_check.py
Возвращает exit code 0 (всё ок) или 1 (есть проблемы).

Проверяет:
  1. py_compile всех .py файлов
  2. CSP nonce: все <script> в шаблонах имеют nonce
  3. Inline event handlers: нет onclick/onchange/onsubmit в HTML
     (исключение: onerror на <img> — image fallback, project_patterns.md)
  4. profiles select=: все PostgREST-запросы profiles? имеют select=
     (понимает многострочные вызовы и переменные-запросы с select=)
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
    """3. Нет inline onclick/onchange/onsubmit/onload в HTML (CSP strict-dynamic).

    Исключение (project_patterns.md): onerror на <img> допустим — image fallback.
    Тег <img> может стоять на несколько строк выше onerror (многострочные атрибуты).
    """
    print("\n[3/6] Inline event handlers (CSP strict-dynamic)...")
    tpl_dir = ROOT / "templates"
    found = False
    for f in tpl_dir.rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            for m in re.finditer(r'\son(click|change|submit|load|error|mouseover)\s*=', line):
                snippet = line.strip()[:80]
                # Исключение: onerror на <img> — допустим для fallback картинок.
                # Проверяем контекст: текущая + 10 предыдущих строк (многострочные атрибуты).
                if 'onerror' in m.group(0):
                    context = '\n'.join(lines[max(0, i - 11):i + 1])
                    if re.search(r'<img\b', context):
                        continue
                err(f"{f.relative_to(ROOT)}:{i} inline {m.group(0).strip()}: {snippet}")
                found = True
    if not found:
        print("  ✅ No inline event handlers")


def _collect_safe_query_vars(lines):
    """Собрать имена локальных переменных, заведомо содержащих select=.

    Покрывает три способа построения запроса:
      1. Прямое присваивание/дополнение:  query = '...select=...'  /  query += '&select=...'
      2. Список-частей:                    query_parts = ['select=*', ...]
      3. Вызов функции-билдера:            query = build_worker_query(...)
         где функция (в этом же файле) содержит select= в теле.

    Возвращает set имён переменных, безопасных для подстановки в profiles?{var}.
    """
    safe_vars = set()

    # 1. Функции, чьё тело содержит 'select=' (build_*_query и т.п.)
    func_has_select = {}
    current_func = None
    current_select = False
    for line in lines:
        mdef = re.match(r'def\s+(\w+)\s*\(', line)
        if mdef:
            if current_func is not None:
                func_has_select[current_func] = current_select
            current_func = mdef.group(1)
            current_select = False
        elif current_func and 'select=' in line:
            current_select = True
    if current_func is not None:
        func_has_select[current_func] = current_select

    # 2. Переменные с select= (прямое присваивание или +=)
    for line in lines:
        m = re.match(r'\s*(\w+)\s*\+?=\s*(.*)', line)
        if m and 'select=' in m.group(2):
            safe_vars.add(m.group(1))

    # 3. var = func(...) где func содержит select= в теле
    for line in lines:
        m = re.match(r'\s*(\w+)\s*=\s*(\w+)\s*\(', line)
        if m:
            varname, funcname = m.group(1), m.group(2)
            if func_has_select.get(funcname):
                safe_vars.add(varname)

    return safe_vars


def check_profiles_select():
    """4. Все profiles? запросы через user-JWT должны иметь select=.

    Примечания:
      - postgrest_admin_request (service_role) обходят RLS — select= не нужен.
      - PATCH/POST обрабатываются _normalize_endpoint автоматически.
      - Многострочные вызовы: postgrest_admin_request/PATCH может быть на предыдущей строке.
      - Переменные-запросы: select= может быть в переменной (query += '&select=...').
    """
    print("\n[4/6] profiles select= check (user-JWT only)...")
    app_dir = ROOT / "app"
    found = False
    for f in app_dir.rglob("*.py"):
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        safe_vars = _collect_safe_query_vars(lines)
        prev_line = ""
        for i, line in enumerate(lines, 1):
            if "profiles?" not in line:
                prev_line = line
                continue
            if "select=" in line:
                prev_line = line
                continue
            # admin (service_role) — на этой или предыдущей строке
            if "postgrest_admin_request" in line or "admin_request" in line:
                prev_line = line
                continue
            if "admin_request" in prev_line:
                prev_line = line
                continue
            if "postgrest_rpc" in line:
                prev_line = line
                continue
            # PATCH/POST — на этой или предыдущей строке (_normalize_endpoint)
            if "PATCH" in line or "'POST'" in line or '"POST"' in line:
                prev_line = line
                continue
            if "PATCH" in prev_line or "'POST'" in prev_line or '"POST"' in prev_line:
                prev_line = line
                continue
            if "admin" in str(f.relative_to(ROOT)).replace("\\", "/").lower():
                prev_line = line  # admin blueprints use service_role
                continue
            # Переменная-запрос: f'profiles?{var}' где var содержит select= (см. safe_vars)
            mvars = re.findall(r'profiles\?\{(\w+)\}', line)
            if mvars and all(v in safe_vars for v in mvars):
                prev_line = line
                continue
            rel = str(f.relative_to(ROOT))
            err(f"{rel}:{i} profiles query without select= (user-JWT): {line.strip()[:70]}")
            found = True
            prev_line = line
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
