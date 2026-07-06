"""
F28: Проверка использования нативного <dialog> элемента для модальных окон.

Требования:
- Модальные окна должны использовать нативный <dialog> тег
- <dialog> должен иметь aria-labelledby атрибут
"""
import os
import re
from pathlib import Path


def test_modals_use_native_dialog_element():
    """Проверяет, что модальные окна используют нативный <dialog> тег."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Паттерны для поиска кастомных модальных окон
    # (div с классами modal, modal-backdrop, modal-content и т.п.)
    custom_modal_patterns = [
        r'<div[^>]*class="[^"]*modal-backdrop[^"]*"[^>]*>',
        r'<div[^>]*id="[^"]*modal[^"]*"[^>]*>',
    ]
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for pattern in custom_modal_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                violations.append(f"{html_file.name}: найдены кастомные модальные окна вместо <dialog>")
    
    assert not violations, \
        f"Найдены кастомные модальные окна вместо <dialog>:\n" + "\n".join(violations)


def test_dialog_elements_have_aria_labelledby():
    """Проверяет, что все <dialog> элементы имеют aria-labelledby атрибут."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <dialog> теги
        dialog_pattern = r'<dialog[^>]*>'
        dialog_tags = re.findall(dialog_pattern, content, re.IGNORECASE)
        
        for dialog_tag in dialog_tags:
            # Проверяем наличие aria-labelledby атрибута
            if 'aria-labelledby=' not in dialog_tag.lower():
                violations.append(f"{html_file.name}: <dialog> без aria-labelledby атрибута: {dialog_tag}")
    
    assert not violations, \
        f"Найдены <dialog> без aria-labelledby:\n" + "\n".join(violations)
