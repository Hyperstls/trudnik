"""
F20: Проверка наличия color-scheme meta tag и dark mode поддержки.

Требования:
- base.html должен содержать <meta name="color-scheme" content="light dark">
- app.css должен содержать @media (prefers-color-scheme: dark) с color-scheme: dark
"""
import os
import re
from pathlib import Path


def test_base_html_has_color_scheme_meta():
    """Проверяет, что base.html содержит color-scheme meta tag."""
    base_path = Path(__file__).parent.parent / 'templates' / 'base.html'
    
    with open(base_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие meta tag
    assert '<meta name="color-scheme" content="light dark">' in content, \
        "base.html должен содержать <meta name=\"color-scheme\" content=\"light dark\">"


def test_css_has_dark_mode_support():
    """Проверяет, что app.css содержит поддержку dark mode."""
    css_path = Path(__file__).parent.parent / 'static' / 'css' / 'app.css'
    
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие медиа-запроса
    assert '@media (prefers-color-scheme: dark)' in content, \
        "app.css должен содержать медиа-запрос @media (prefers-color-scheme: dark)"
    
    # Проверяем, что внутри медиа-запроса устанавливается color-scheme: dark
    dark_mode_pattern = r'@media\s*\(\s*prefers-color-scheme:\s*dark\s*\)\s*\{[^}]*color-scheme:\s*dark'
    assert re.search(dark_mode_pattern, content, re.DOTALL), \
        "Медиа-запрос должен устанавливать color-scheme: dark"
