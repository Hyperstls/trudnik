"""
F19: Проверка наличия поддержки prefers-reduced-motion.

Требования:
- CSS файл должен содержать медиа-запрос @media (prefers-reduced-motion: reduce)
- Все анимации и переходы должны быть отключены для пользователей с reduced motion
"""
import os
import re
from pathlib import Path


def test_css_has_reduced_motion_support():
    """Проверяет, что app.css содержит медиа-запрос для prefers-reduced-motion."""
    css_path = Path(__file__).parent.parent / 'static' / 'css' / 'app.css'
    
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие медиа-запроса
    assert '@media (prefers-reduced-motion: reduce)' in content, \
        "app.css должен содержать медиа-запрос @media (prefers-reduced-motion: reduce)"
    
    # Проверяем, что внутри медиа-запроса отключаются анимации
    reduced_motion_pattern = r'@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{[^}]*animation-duration:\s*0\.01ms'
    assert re.search(reduced_motion_pattern, content, re.DOTALL), \
        "Медиа-запрос должен отключать animation-duration"
    
    # Проверяем, что внутри медиа-запроса отключаются переходы
    transition_pattern = r'@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{[^}]*transition-duration:\s*0\.01ms'
    assert re.search(transition_pattern, content, re.DOTALL), \
        "Медиа-запрос должен отключать transition-duration"


def test_reduced_motion_applies_to_all_elements():
    """Проверяет, что медиа-запрос применяется ко всем элементам."""
    css_path = Path(__file__).parent.parent / 'static' / 'css' / 'app.css'
    
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, что медиа-запрос содержит селекторы *, *::before, *::after
    universal_selector_pattern = r'@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{[^}]*\*[^}]*\*::before[^}]*\*::after'
    assert re.search(universal_selector_pattern, content, re.DOTALL), \
        "Медиа-запрос должен применяться к *, *::before, *::after"
