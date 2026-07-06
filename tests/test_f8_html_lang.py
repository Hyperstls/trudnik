"""
F8: Тест проверяет наличие lang="ru" и meta description в base.html.

Требования:
- Атрибут lang="ru" у тега <html>
- Meta description с описанием сайта
- Meta viewport для адаптивности
"""
from pathlib import Path


BASE_HTML = Path(__file__).parent.parent / "templates" / "base.html"


def test_html_has_lang_attribute():
    """Проверяет наличие атрибута lang="ru" у тега <html>."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие lang="ru"
    assert '<html lang="ru">' in content, \
        "Тег <html> должен иметь атрибут lang='ru'"


def test_meta_description_exists():
    """Проверяет наличие meta description."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие meta description
    assert '<meta name="description"' in content, \
        "Должен быть meta description"
    
    # Проверяем, что description не пустой
    assert 'content="' in content, \
        "Meta description должен иметь атрибут content"


def test_meta_viewport_exists():
    """Проверяет наличие meta viewport."""
    content = BASE_HTML.read_text(encoding='utf-8')
    
    # Проверяем наличие meta viewport
    assert '<meta name="viewport"' in content, \
        "Должен быть meta viewport"
    
    # Проверяем наличие width=device-width
    assert 'width=device-width' in content, \
        "Meta viewport должен содержать width=device-width"
    
    # Проверяем наличие initial-scale=1
    assert 'initial-scale=1' in content, \
        "Meta viewport должен содержать initial-scale=1"


if __name__ == "__main__":
    test_html_has_lang_attribute()
    test_meta_description_exists()
    test_meta_viewport_exists()
    print("Все тесты F8 пройдены!")
