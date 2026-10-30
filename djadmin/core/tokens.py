"""Токены email-верификации и сброса пароля — ПОЛНЫЙ паритет с Flask
(app/blueprints/auth.py): те же соли, TTL и payload (itsdangerous
URLSafeTimedSerializer по SECRET_KEY). Токены взаимозаменяемы: письмо,
отправленное Flask, подтверждается Django, и наоборот.
"""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from django.conf import settings

PASSWORD_RESET_SALT = "password-reset"  # pragma: allowlist secret (соль, не секрет)
PASSWORD_RESET_MAX_AGE = 3600  # 1 час
EMAIL_VERIFICATION_SALT = "email-verify"  # pragma: allowlist secret (соль, не секрет)
EMAIL_VERIFICATION_MAX_AGE = 86400  # 24 часа


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt=salt)


# ── Сброс пароля ────────────────────────────────────────────────────────────
def generate_reset_token(email: str, password_changed_at: str = "") -> str:
    """Инвалидация при смене пароля — через pwd_changed_at в payload (B11)."""
    return _serializer(PASSWORD_RESET_SALT).dumps({"email": email, "pwd_changed_at": password_changed_at})


def verify_reset_token(token: str, max_age: int = PASSWORD_RESET_MAX_AGE) -> dict | None:
    try:
        result = _serializer(PASSWORD_RESET_SALT).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if isinstance(result, str):  # обратная совместимость со старыми Flask-токенами
        return {"email": result, "pwd_changed_at": ""}
    return result if isinstance(result, dict) else None


# ── Подтверждение email ─────────────────────────────────────────────────────
def generate_email_verification_token(email: str) -> str:
    return _serializer(EMAIL_VERIFICATION_SALT).dumps(email)


def verify_email_verification_token(token: str, max_age: int = EMAIL_VERIFICATION_MAX_AGE) -> str | None:
    try:
        result = _serializer(EMAIL_VERIFICATION_SALT).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return result if isinstance(result, str) else None
