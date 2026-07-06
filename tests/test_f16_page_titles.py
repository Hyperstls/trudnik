"""F16: Все страницы должны иметь уникальный title."""
import os
import re
import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')


def _read_all_templates():
    """Считать все HTML-шаблоны (не email)."""
    result = {}
    for fname in os.listdir(TEMPLATES_DIR):
        if fname.endswith('.html') and 'email' not in fname:
            fpath = os.path.join(TEMPLATES_DIR, fname)
            with open(fpath, encoding='utf-8') as f:
                result[fname] = f.read()
    return result


def _extends_base(html):
    """Проверить, наследуется ли шаблон от base.html."""
    return bool(re.search(r'{%\s*extends\s+["\']base\.html["\']\s*%}', html, re.IGNORECASE))


def _has_title_block(html):
    """Проверить, есть ли block title в шаблоне."""
    return bool(re.search(r'{%\s*block\s+title\s*%}', html, re.IGNORECASE))


def _has_title_tag(html):
    """Проверить, есть ли <title> тег в standalone HTML."""
    return bool(re.search(r'<title[^>]*>', html, re.IGNORECASE))


def test_all_pages_have_titles():
    """Все страницы должны иметь title (block title или <title> тег)."""
    templates = _read_all_templates()
    violations = []
    
    for fname, html in templates.items():
        # Пропускаем компоненты и partials
        if fname.startswith('_'):
            continue
        
        # Если наследуется от base.html - должен быть block title
        if _extends_base(html):
            if not _has_title_block(html):
                violations.append(f"{fname}: наследуется от base.html, но не имеет block title")
        else:
            # Standalone HTML должен иметь <title> тег
            if not _has_title_tag(html):
                violations.append(f"{fname}: standalone HTML без <title> тега")
    
    assert not violations, (
        "Следующие страницы не имеют title:\n" +
        "\n".join(violations)
    )
