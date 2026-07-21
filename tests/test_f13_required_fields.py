"""F13: Обязательные поля форм должны иметь required и aria-required атрибуты."""
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


def _extract_inputs_with_required(html):
    """Извлечь все input/select/textarea с required атрибутом."""
    pattern = re.compile(r'<(input|select|textarea)\s[^>]*\brequired\b[^>]*>', re.IGNORECASE | re.DOTALL)
    return pattern.findall(html)


def _has_aria_required(tag):
    """Проверить, имеет ли тег aria-required="true"."""
    return bool(re.search(r'aria-required=["\']true["\']', tag, re.IGNORECASE))


def test_required_fields_have_aria_required():
    """Все поля с required должны также иметь aria-required="true"."""
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        # Ищем все теги с required (как отдельный атрибут, не часть aria-required)
        # required может быть: в начале атрибутов, после пробела, или в конце
        tags = re.findall(r'<(?:input|select|textarea)\s[^>]*(?:\s|^)required(?:\s|=|>)[^>]*>', html, re.IGNORECASE | re.DOTALL)
        for tag in tags:
            if not _has_aria_required(tag):
                short_tag = tag[:100] + '...' if len(tag) > 100 else tag
                violations.append(f"{fname}: {short_tag}")
    assert not violations, (
        "Следующие обязательные поля не имеют aria-required=\"true\":\n" +
        "\n".join(violations)
    )
