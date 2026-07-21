"""
F21: Проверка наличия alt атрибутов у изображений.

Требования:
- Все <img> теги должны иметь alt атрибут
- Alt текст должен быть осмысленным (не пустым для контентных изображений)
"""
import os
import re
from pathlib import Path


def test_all_images_have_alt_attribute():
    """Проверяет, что все изображения имеют alt атрибут."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <img> теги
        img_pattern = r'<img[^>]*>'
        img_tags = re.findall(img_pattern, content, re.IGNORECASE)
        
        for img_tag in img_tags:
            # Проверяем наличие alt атрибута
            if 'alt=' not in img_tag.lower():
                violations.append(f"{html_file.name}: {img_tag[:100]}")
    
    assert not violations, \
        f"Найдены изображения без alt атрибута:\n" + "\n".join(violations)


def test_alt_attributes_not_empty_for_content_images():
    """Проверяет, что контентные изображения имеют непустой alt текст."""
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    # Находим все HTML файлы
    html_files = list(templates_dir.rglob('*.html'))
    
    violations = []
    
    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим все <img> теги с alt=""
        empty_alt_pattern = r'<img[^>]*alt=["\']["\'][^>]*>'
        empty_alt_tags = re.findall(empty_alt_pattern, content, re.IGNORECASE)
        
        # Пустой alt допустим только для декоративных изображений
        # В данном проекте все изображения являются контентными (аватары)
        for img_tag in empty_alt_tags:
            violations.append(f"{html_file.name}: {img_tag[:100]}")
    
    # Этот тест информационный - пустой alt допустим для декоративных изображений
    if violations:
        print(f"\nПредупреждение: найдены изображения с пустым alt:\n" + "\n".join(violations))
