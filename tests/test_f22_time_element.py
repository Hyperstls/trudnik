"""
F22: Проверка наличия <time> тегов для дат.

Требования:
- Все даты должны быть обёрнуты в <time datetime="...">
"""
import os
import re
from pathlib import Path


def test_dates_wrapped_in_time_tags():
    """Проверяет, что даты обёрнуты в <time> теги."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Паттерны для поиска дат без <time> тегов
    date_patterns = [
        r'\{\{[^}]*created_at[^}]*\|[^}]*format_date[^}]*\}\}',
        r'\{\{[^}]*date_time[^}]*\|[^}]*format_date[^}]*\}\}',
        r'\{\{[^}]*created_at\[\d+:\d+\][^}]*\}\}',
    ]
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                # Проверяем, находится ли дата внутри <time> тега
                start = max(0, match.start() - 100)
                context = content[start:match.end() + 50]
                
                # Если нет <time перед датой, это нарушение
                if '<time' not in context or '</time>' not in context:
                    violations.append(f"{html_file.name}: {match.group()}")
    
    assert not violations, \
        f"Найдены даты без <time> тегов:\n" + "\n".join(violations)


def test_time_tags_have_datetime_attribute():
    """Проверяет, что все <time> теги имеют datetime атрибут."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <time> теги
        time_pattern = r'<time[^>]*>'
        time_tags = re.findall(time_pattern, content, re.IGNORECASE)
        
        for time_tag in time_tags:
            # Проверяем наличие datetime атрибута
            if 'datetime=' not in time_tag.lower():
                violations.append(f"{html_file.name}: {time_tag}")
    
    assert not violations, \
        f"Найдены <time> теги без datetime атрибута:\n" + "\n".join(violations)
