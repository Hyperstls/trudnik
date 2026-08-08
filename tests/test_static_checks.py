"""Static code checks — ловят системные баги до деплоя.

Запуск: pytest tests/test_static_checks.py -v
Эти тесты НЕ требуют БД/Redis/PostgREST — чистый анализ кода.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent


# ── CSP: nonce на всех <script> ──────────────────────────────────
def test_all_scripts_have_csp_nonce():
    """CSP strict-dynamic: все <script> в шаблонах должны иметь nonce."""
    violations = []
    for f in (ROOT / "templates").rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<script(?![^>]*nonce=)[^>]*>', content):
            line = content[:m.start()].count("\n") + 1
            violations.append(f"{f.name}:{line}")
    assert not violations, f"<script> without nonce: {violations}"


# ── CSP: нет inline event handlers ───────────────────────────────
def test_no_inline_event_handlers():
    """CSP strict-dynamic блокирует onclick/onchange/onsubmit."""
    violations = []
    for f in (ROOT / "templates").rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'\son(click|change|submit|load|mouseover)\s*=', content):
            line = content[:m.start()].count("\n") + 1
            violations.append(f"{f.name}:{line}")
    # onerror в _icons.html — допустимое исключение (image fallback)
    violations = [v for v in violations if "_icons.html" not in v]
    assert not violations, f"Inline event handlers (CSP violation): {violations}"


# ── PostgREST: profiles GET через user-JWT должен иметь select= ───
@pytest.mark.xfail(reason="known debt: 4 profiles GET without select= (auth, employers, notifications, job_service)")
def test_profiles_get_queries_have_select():
    """profiles ограничена column-level GRANT — GET без select= → 401."""
    violations = []
    for f in (ROOT / "app").rglob("*.py"):
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if "admin" in rel:
            continue  # admin blueprints use service_role
        content = f.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            if "profiles?" not in line:
                continue
            if "select=" in line:
                continue
            if "admin_request" in line or "postgrest_rpc" in line:
                continue
            if "PATCH" in line or "'POST'" in line or '"POST"' in line:
                continue  # _normalize_endpoint handles mutations
            if "auth.py" in rel and ("email_verified" in line or "reset" in line.lower()):
                continue  # auth internal flows
            violations.append(f"{rel}:{i}: {line.strip()[:60]}")
    assert not violations, f"profiles GET without select= (401 risk): {violations}"


# ── Celery: нет current_app.logger в tasks/ ──────────────────────
def test_no_current_app_logger_in_celery_tasks():
    """current_app.logger падает вне Flask app-context (Celery)."""
    violations = []
    for f in (ROOT / "app" / "tasks").glob("*.py"):
        content = f.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            if "current_app.logger" in line and "import" not in line:
                if line.strip().startswith("#"):
                    continue
                violations.append(f"{f.name}:{i}")
    assert not violations, f"current_app.logger in Celery tasks (RuntimeError): {violations}"


# ── HTML: нет дублирующихся атрибутов ────────────────────────────
def test_no_duplicate_html_attributes():
    """Два class= на одном элементе — браузер игнорирует второй."""
    violations = []
    for f in (ROOT / "templates").rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<\w+[^>]*>', content):
            tag = m.group(0)
            attrs = re.findall(r'\s(\w[\w-]*)=', tag)
            seen = set()
            for a in attrs:
                if a in seen:
                    line = content[:m.start()].count("\n") + 1
                    violations.append(f"{f.name}:{line} dup:{a}")
                    break
                seen.add(a)
    assert not violations, f"Duplicate HTML attributes: {violations}"


# ── SW: версия кэша актуальна ────────────────────────────────────
def test_sw_cache_version_consistent():
    """CACHE_VERSION и CACHE_NAME в sw.js должны совпадать."""
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    ver = re.search(r"CACHE_VERSION = '([^']+)'", sw)
    name = re.search(r"CACHE_NAME = '([^']+)'", sw)
    assert ver and name, "CACHE_VERSION/CACHE_NAME not found in sw.js"
    assert ver.group(1) == name.group(1), f"Version mismatch: {ver.group(1)} != {name.group(1)}"


# ── SW: ключевые пути исключены из navigation ────────────────────
def test_sw_excludes_critical_paths():
    """SW не должен перехватывать навигацию на /chat/, /messenger/, /profile/."""
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    for path in ["/chat", "/messenger", "/my-applications", "/admin", "/logout"]:
        assert path in sw, f"SW missing exclusion for {path} (Navigation error risk)"
