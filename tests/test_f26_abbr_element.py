"""
F26: Проверка использования <abbr> для аббревиатур.

Требования:
- Аббревиатуры должны быть обёрнуты в <abbr title="...">
"""
import os
import re
from pathlib import Path


def test_abbreviations_use_abbr_element():
    """Проверяет, что аббревиатуры используют <abbr> тег."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    # Список распространённых аббревиатур
    abbreviations = ['ИНН', 'ФИО', 'ИП', 'ООО', 'ОГРН', 'КПП', 'НДС', 'СНИЛС']
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for abbr in abbreviations:
            # Ищем все вхождения аббревиатуры
            pattern = r'\b' + re.escape(abbr) + r'\b'
            matches = list(re.finditer(pattern, content))
            
            for match in matches:
                # Проверяем, находится ли аббревиатура внутри <abbr> тега
                start = match.start()
                # Ищем ближайший <abbr перед позицией
                before = content[:start]
                after = content[start:]
                
                # Проверяем, есть ли открывающий <abbr без закрывающего </abbr> перед аббревиатурой
                last_abbr_open = before.rfind('<abbr')
                if last_abbr_open != -1:
                    # Проверяем, есть ли </abbr> между <abbr и аббревиатурой
                    between = content[last_abbr_open:start]
                    if '</abbr>' not in between:
                        # Аббревиатура внутри <abbr> тега - OK
                        continue
                
                # Если дошли сюда, значит аббревиатура не обёрнута в <abbr>
                violations.append(f"{html_file.name}: найдена аббревиатура '{abbr}' без <abbr> тега")
    
    assert not violations, \
        f"Найдены аббревиатуры без <abbr>:\n" + "\n".join(violations)


def test_abbr_elements_have_title():
    """Проверяет, что все <abbr> элементы имеют title атрибут."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <abbr> теги
        abbr_pattern = r'<abbr[^>]*>'
        abbr_tags = re.findall(abbr_pattern, content, re.IGNORECASE)
        
        for abbr_tag in abbr_tags:
            # Проверяем наличие title атрибута
            if 'title=' not in abbr_tag.lower():
                violations.append(f"{html_file.name}: <abbr> без title атрибута: {abbr_tag}")
    
    assert not violations, \
        f"Найдены <abbr> без title:\n" + "\n".join(violations)
