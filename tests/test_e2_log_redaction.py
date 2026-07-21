"""
E2: Тест для проверки маскирования чувствительных данных в логах.

Функция _redact_sensitive должна маскировать email и телефоны.
"""
import pytest
from app.utils.helpers import _redact_sensitive


class TestRedactSensitive:
    """Тесты для функции _redact_sensitive."""
    
    def test_redact_email_simple(self):
        """Простой email должен быть замаскирован."""
        text = "User email: user@example.com"
        result = _redact_sensitive(text)
        assert "user@example.com" not in result
        assert "[REDACTED_EMAIL]" in result
    
    def test_redact_email_complex(self):
        """Сложный email с поддоменами должен быть замаскирован."""
        text = "Contact: john.doe+test@sub.domain.co.uk"
        result = _redact_sensitive(text)
        assert "john.doe+test@sub.domain.co.uk" not in result
        assert "[REDACTED_EMAIL]" in result
    
    def test_redact_multiple_emails(self):
        """Несколько email в тексте должны быть замаскированы."""
        text = "From: admin@site.com, To: user@mail.ru"
        result = _redact_sensitive(text)
        assert "admin@site.com" not in result
        assert "user@mail.ru" not in result
        assert result.count("[REDACTED_EMAIL]") == 2
    
    def test_redact_phone_russian_plus7(self):
        """Российский телефон с +7 должен быть замаскирован."""
        text = "Phone: +7 (999) 123-45-67"
        result = _redact_sensitive(text)
        assert "+7 (999) 123-45-67" not in result
        assert "[REDACTED_PHONE]" in result
    
    def test_redact_phone_russian_8(self):
        """Российский телефон с 8 должен быть замаскирован."""
        text = "Call: 8-999-123-45-67"
        result = _redact_sensitive(text)
        assert "8-999-123-45-67" not in result
        assert "[REDACTED_PHONE]" in result
    
    def test_redact_phone_no_separators(self):
        """Телефон без разделителей должен быть замаскирован."""
        text = "Mobile: +79991234567"
        result = _redact_sensitive(text)
        assert "+79991234567" not in result
        assert "[REDACTED_PHONE]" in result
    
    def test_redact_mixed_content(self):
        """Текст с email и телефоном должен быть замаскирован."""
        text = "User: test@example.com, Phone: +7 (123) 456-78-90"
        result = _redact_sensitive(text)
        assert "test@example.com" not in result
        assert "+7 (123) 456-78-90" not in result
        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_PHONE]" in result
    
    def test_no_redaction_needed(self):
        """Текст без чувствительных данных не должен изменяться."""
        text = "Error: database connection failed"
        result = _redact_sensitive(text)
        assert result == text
    
    def test_empty_string(self):
        """Пустая строка должна возвращаться как есть."""
        assert _redact_sensitive("") == ""
    
    def test_none_input(self):
        """None должен возвращаться как есть."""
        assert _redact_sensitive(None) is None
    
    def test_partial_email_not_redacted(self):
        """Неполный email (без домена) не должен маскироваться."""
        text = "Username: user@"
        result = _redact_sensitive(text)
        # Это не валидный email, поэтому не должен маскироваться
        assert "user@" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
