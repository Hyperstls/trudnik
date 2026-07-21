"""
F1: Тест проверяет, что все icon-only кнопки имеют aria-label.

Icon-only кнопка — это кнопка, которая содержит только SVG/emoji иконку
без текстового содержимого (или с текстом, скрытым через hidden sm:inline).
"""
import os
import re
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def find_html_files():
    """Находит все HTML-файлы в директории templates."""
    return list(TEMPLATES_DIR.rglob("*.html"))


def is_icon_only_button(button_html: str) -> bool:
    """
    Определяет, является ли кнопка icon-only.
    
    Кнопка считается icon-only, если:
    1. Содержит <svg> или emoji (🚫, ★, ❤️ и т.д.)
    2. Не содержит видимого текста (текст может быть в <span class="hidden sm:inline">)
    """
    # Удаляем атрибуты кнопки для анализа содержимого
    content_match = re.search(r'>(.*?)</button>', button_html, re.DOTALL)
    if not content_match:
        return False
    
    content = content_match.group(1)
    
    # Проверяем наличие SVG
    has_svg = '<svg' in content
    
    # Проверяем наличие emoji
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    has_emoji = bool(emoji_pattern.search(content))
    
    # Проверяем наличие видимого текста (не в hidden span)
    # Удаляем все теги
    text_only = re.sub(r'<[^>]+>', '', content).strip()
    # Удаляем пробелы и переносы
    text_only = re.sub(r'\s+', '', text_only)
    
    # Если есть SVG/emoji и нет видимого текста — это icon-only
    return (has_svg or has_emoji) and len(text_only) == 0


def has_aria_label(button_html: str) -> bool:
    """Проверяет наличие aria-label в кнопке."""
    return 'aria-label=' in button_html


def extract_buttons(html_content: str) -> list:
    """Извлекает все <button> элементы из HTML."""
    # Паттерн для поиска полных button элементов
    pattern = r'<button[^>]*>.*?</button>'
    return re.findall(pattern, html_content, re.DOTALL)


def test_icon_only_buttons_have_aria_label():
    """
    Тест проверяет, что все icon-only кнопки имеют aria-label.
    
    Проходит по всем HTML-файлам в templates/ и проверяет:
    1. Если кнопка содержит только иконку (SVG/emoji)
    2. То она должна иметь aria-label
    """
    html_files = find_html_files()
    assert len(html_files) > 0, "Не найдены HTML-файлы в templates/"
    
    violations = []
    
    for html_file in html_files:
        # Пропускаем email шаблоны
        if 'email' in str(html_file):
            continue
            
        content = html_file.read_text(encoding='utf-8')
        buttons = extract_buttons(content)
        
        for button in buttons:
            if is_icon_only_button(button) and not has_aria_label(button):
                # Извлекаем первую строку кнопки для сообщения об ошибке
                first_line = button.split('\n')[0][:100]
                violations.append(f"{html_file.name}: {first_line}...")
    
    if violations:
        msg = "Найдены icon-only кнопки без aria-label:\n" + "\n".join(f"  - {v}" for v in violations)
        assert False, msg


def test_svg_elements_have_aria_hidden():
    """
    Тест проверяет, что декоративные SVG внутри кнопок имеют aria-hidden="true".
    
    Это улучшает доступность для screen readers.
    """
    html_files = find_html_files()
    
    violations = []
    
    for html_file in html_files:
        if 'email' in str(html_file):
            continue
            
        content = html_file.read_text(encoding='utf-8')
        buttons = extract_buttons(content)
        
        for button in buttons:
            if is_icon_only_button(button):
                # Проверяем, что SVG имеет aria-hidden
                if '<svg' in button and 'aria-hidden="true"' not in button:
                    first_line = button.split('\n')[0][:100]
                    violations.append(f"{html_file.name}: {first_line}...")
    
    if violations:
        msg = "Найдены SVG без aria-hidden=\"true\" в icon-only кнопках:\n" + "\n".join(f"  - {v}" for v in violations)
        assert False, msg


if __name__ == "__main__":
    test_icon_only_buttons_have_aria_label()
    test_svg_elements_have_aria_hidden()
    print("Все тесты F1 пройдены!")
