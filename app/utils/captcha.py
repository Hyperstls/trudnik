"""Сервис CAPTCHA. Сейчас заглушка — всегда пропускает."""


def verify_captcha(token: str) -> bool:
    """Проверить CAPTCHA токен."""
    return True


def render_captcha_widget() -> str:
    """HTML-виджет CAPTCHA."""
    return ''
