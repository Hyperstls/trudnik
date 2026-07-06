"""
F23: Проверка использования <details> и <summary> для FAQ/accordion.

Требования:
- Accordion-элементы должны использовать нативный <details><summary>
"""
import os
import re
from pathlib import Path


def test_accordion_uses_details_summary():
    """Проверяет, что accordion-элементы используют <details>/<summary>."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Паттерны для поиска кастомных accordion-элементов
    # (элементы с классами accordion, collapse, expandable и т.п.)
    accordion_patterns = [
        r'class="[^"]*accordion[^"]*"',
        r'class="[^"]*collapse[^"]*"',
        r'class="[^"]*expandable[^"]*"',
        r'class="[^"]*faq-item[^"]*"',
    ]
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for pattern in accordion_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Проверяем, используются ли <details>/<summary>
                if '<details' not in content or '<summary' not in content:
                    violations.append(f"{html_file.name}: найдены accordion-элементы без <details>/<summary>")
    
    # Если нарушений нет, тест проходит
    assert not violations, \
        f"Найдены accordion-элементы без <details>/<summary>:\n" + "\n".join(violations)


def test_details_elements_have_summary():
    """Проверяет, что все <details> элементы имеют <summary>."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <details> теги
        details_pattern = r'<details[^>]*>(.*?)</details>'
        details_blocks = re.findall(details_pattern, content, re.DOTALL | re.IGNORECASE)
        
        for block in details_blocks:
            # Проверяем наличие <summary> внутри <details>
            if '<summary' not in block.lower():
                violations.append(f"{html_file.name}: <details> без <summary>")
    
    assert not violations, \
        f"Найдены <details> без <summary>:\n" + "\n".join(violations)
