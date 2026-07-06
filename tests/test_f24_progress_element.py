"""
F24: Проверка использования нативного <progress> элемента для прогресс-баров.

Требования:
- Прогресс-бары должны использовать нативный <progress> тег
- <progress> должен иметь value, max и aria-label атрибуты
"""
import os
import re
from pathlib import Path


def test_progress_bars_use_native_element():
    """Проверяет, что прогресс-бары используют нативный <progress> тег."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Паттерны для поиска кастомных прогресс-баров
    # (div с классами progress-bar, progress, bar и т.п.)
    custom_progress_patterns = [
        r'<div[^>]*class="[^"]*progress-bar[^"]*"[^>]*>',
        r'<div[^>]*class="[^"]*progress[^"]*"[^>]*>',
        r'<div[^>]*id="progress-bar"[^>]*>',
    ]
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for pattern in custom_progress_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                violations.append(f"{html_file.name}: найдены кастомные прогресс-бары")
    
    assert not violations, \
        f"Найдены кастомные прогресс-бары вместо <progress>:\n" + "\n".join(violations)


def test_progress_elements_have_required_attributes():
    """Проверяет, что все <progress> элементы имеют value, max и aria-label."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <progress> теги
        progress_pattern = r'<progress[^>]*>'
        progress_tags = re.findall(progress_pattern, content, re.IGNORECASE)
        
        for progress_tag in progress_tags:
            # Проверяем наличие value атрибута
            if 'value=' not in progress_tag.lower():
                violations.append(f"{html_file.name}: <progress> без value атрибута: {progress_tag}")
            
            # Проверяем наличие max атрибута
            if 'max=' not in progress_tag.lower():
                violations.append(f"{html_file.name}: <progress> без max атрибута: {progress_tag}")
            
            # Проверяем наличие aria-label атрибута
            if 'aria-label=' not in progress_tag.lower():
                violations.append(f"{html_file.name}: <progress> без aria-label атрибута: {progress_tag}")
    
    assert not violations, \
        f"Найдены <progress> без обязательных атрибутов:\n" + "\n".join(violations)
