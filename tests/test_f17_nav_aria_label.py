"""F17: Все навигационные блоки должны иметь aria-label."""
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


def _find_nav_elements(html):
    """Найти все <nav> элементы."""
    return re.findall(r'<nav[^>]*>', html, re.IGNORECASE)


def _has_aria_label(tag):
    """Проверить, имеет ли тег aria-label атрибут."""
    return bool(re.search(r'aria-label=["\'][^"\']+["\']', tag, re.IGNORECASE))


def test_all_nav_elements_have_aria_label():
    """Все <nav> элементы должны иметь aria-label."""
    templates = _read_all_templates()
    violations = []
    
    for fname, html in templates.items():
        nav_elements = _find_nav_elements(html)
        for nav in nav_elements:
            if not _has_aria_label(nav):
                short_tag = nav[:100] + '...' if len(nav) > 100 else nav
                violations.append(f"{fname}: {short_tag}")
    
    assert not violations, (
        "Следующие <nav> элементы не имеют aria-label:\n" +
        "\n".join(violations)
    )
