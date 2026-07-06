"""F11: Все внешние ссылки должны иметь rel="noopener noreferrer" и target="_blank"."""
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


def _find_external_links(html):
    """Найти <a> с href, указывающим на внешний ресурс (http/https, не /static)."""
    # Ищем <a href="http..."> или <a href='http...'>
    pattern = re.compile(r'<a\s[^>]*href=["\']https?://[^"\']+["\'][^>]*>', re.IGNORECASE)
    return pattern.findall(html)


def _find_target_blank_links(html):
    """Найти <a> с target="_blank"."""
    pattern = re.compile(r'<a\s[^>]*target=["\']_blank["\'][^>]*>', re.IGNORECASE)
    return pattern.findall(html)


def test_external_links_have_noopener_noreferrer():
    """Все <a> с target="_blank" должны иметь rel="noopener noreferrer"."""
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        links = _find_target_blank_links(html)
        for link in links:
            if 'rel=' not in link:
                violations.append(f"{fname}: {link} — нет rel атрибута")
            elif 'noopener' not in link or 'noreferrer' not in link:
                violations.append(f"{fname}: {link} — rel не содержит noopener noreferrer")
    assert not violations, "\n".join(violations)


def test_no_external_links_without_target_blank():
    """Все внешние <a href="http..."> ссылки должны иметь target="_blank"."""
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        links = _find_external_links(html)
        for link in links:
            if 'target=' not in link:
                violations.append(f"{fname}: {link} — нет target атрибута")
    assert not violations, "\n".join(violations)
