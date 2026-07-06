"""
F29: Проверка использования <search> для поисковых форм.

Требования:
- Поисковые формы должны использовать <search> тег или role="search"
- Поисковые input должны иметь aria-label
"""
import re
from pathlib import Path


def test_search_forms_use_search_element():
    """Проверяет, что поисковые формы используют <search> тег или role="search"."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем формы с id содержащим "search"
        search_form_pattern = r'<form[^>]*id="[^"]*search[^"]*"[^>]*>'
        matches = re.findall(search_form_pattern, content, re.IGNORECASE)
        
        for match in matches:
            # Проверяем, обёрнута ли форма в <search> или имеет role="search"
            if 'role="search"' not in match.lower():
                # Проверяем контекст - есть ли <search> перед формой
                form_pos = content.find(match)
                before_form = content[max(0, form_pos-100):form_pos]
                if '<search>' not in before_form.lower():
                    violations.append(f"{html_file.name}: поисковая форма без <search> или role='search'")
    
    assert not violations, \
        f"Найдены поисковые формы без <search>:\n" + "\n".join(violations)


def test_search_inputs_have_aria_label():
    """Проверяет, что поисковые input имеют aria-label."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем input с placeholder содержащим "поиск" или "search"
        search_input_pattern = r'<input[^>]*placeholder="[^"]*(?:поиск|search)[^"]*"[^>]*>'
        matches = re.findall(search_input_pattern, content, re.IGNORECASE)
        
        for match in matches:
            if 'aria-label=' not in match.lower():
                violations.append(f"{html_file.name}: поисковый input без aria-label: {match[:50]}...")
    
    assert not violations, \
        f"Найдены поисковые input без aria-label:\n" + "\n".join(violations)
