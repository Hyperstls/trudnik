"""
F25: Проверка использования <output> для динамических значений.

Требования:
- Динамически обновляемые значения должны использовать <output>
- <output> должен иметь aria-live="polite" атрибут
"""
import os
import re
from pathlib import Path


def test_dynamic_values_use_output_element():
    """Проверяет, что динамические значения используют <output> тег."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Паттерны для поиска динамических значений (count, badge, selected-count)
    dynamic_patterns = [
        r'<span[^>]*id="[^"]*count[^"]*"[^>]*>',
        r'<span[^>]*id="[^"]*badge[^"]*"[^>]*>',
        r'<span[^>]*id="[^"]*selected[^"]*"[^>]*>',
    ]
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for pattern in dynamic_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                violations.append(f"{html_file.name}: найдены динамические значения в <span> вместо <output>")
    
    assert not violations, \
        f"Найдены динамические значения без <output>:\n" + "\n".join(violations)


def test_output_elements_have_aria_live():
    """Проверяет, что все <output> элементы имеют aria-live атрибут."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <output> теги
        output_pattern = r'<output[^>]*>'
        output_tags = re.findall(output_pattern, content, re.IGNORECASE)
        
        for output_tag in output_tags:
            # Проверяем наличие aria-live атрибута
            if 'aria-live=' not in output_tag.lower():
                violations.append(f"{html_file.name}: <output> без aria-live атрибута: {output_tag}")
    
    assert not violations, \
        f"Найдены <output> без aria-live:\n" + "\n".join(violations)
