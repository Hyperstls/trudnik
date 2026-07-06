"""
F10: Тест проверяет наличие autocomplete атрибутов на формах.

Требования:
- Форма входа: autocomplete="email" и autocomplete="current-password"
- Форма регистрации: autocomplete="new-password"
- Форма профиля: autocomplete="name", autocomplete="tel"
"""
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def test_login_form_has_autocomplete():
    """Проверяет наличие autocomplete атрибутов в форме входа."""
    login_html = TEMPLATES_DIR / "login.html"
    content = login_html.read_text(encoding='utf-8')
    
    # Проверяем autocomplete="email" для email поля
    assert 'autocomplete="email"' in content, \
        "Email поле в форме входа должно иметь autocomplete='email'"
    
    # Проверяем autocomplete="current-password" для password поля
    assert 'autocomplete="current-password"' in content, \
        "Password поле в форме входа должно иметь autocomplete='current-password'"


def test_register_form_has_autocomplete():
    """Проверяет наличие autocomplete атрибутов в форме регистрации."""
    register_html = TEMPLATES_DIR / "register.html"
    content = register_html.read_text(encoding='utf-8')
    
    # Проверяем autocomplete="name" для имени
    assert 'autocomplete="name"' in content, \
        "Поле имени в форме регистрации должно иметь autocomplete='name'"
    
    # Проверяем autocomplete="email" для email
    assert 'autocomplete="email"' in content, \
        "Email поле в форме регистрации должно иметь autocomplete='email'"
    
    # Проверяем autocomplete="new-password" для password
    assert 'autocomplete="new-password"' in content, \
        "Password поле в форме регистрации должно иметь autocomplete='new-password'"


def test_profile_form_has_autocomplete():
    """Проверяет наличие autocomplete атрибутов в форме профиля."""
    profile_html = TEMPLATES_DIR / "profile.html"
    content = profile_html.read_text(encoding='utf-8')
    
    # Проверяем autocomplete="name" для имени
    assert 'autocomplete="name"' in content, \
        "Поле имени в форме профиля должно иметь autocomplete='name'"
    
    # Проверяем autocomplete="tel" для телефона
    assert 'autocomplete="tel"' in content, \
        "Поле телефона в форме профиля должно иметь autocomplete='tel'"


if __name__ == "__main__":
    test_login_form_has_autocomplete()
    test_register_form_has_autocomplete()
    test_profile_form_has_autocomplete()
    print("Все тесты F10 пройдены!")
