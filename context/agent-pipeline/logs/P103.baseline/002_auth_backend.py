"""Auth-бридж: вход в админку по email+bcrypt из profiles.

Совместимость хэшей: один и тот же формат $2b$/$2a$ 12 раундов используют
Flask (app/utils/auth.py), pgcrypto crypt() и Django BCryptPasswordHasher.
Fail-closed: suspended → отказ (is_active=False), неподтверждённый email → отказ.
Лок-аут: 5 неудач → экспоненциальный бэкоф (в памяти процесса; масштаб админки).
"""
import time

from django.contrib.auth import backends
from django.core.exceptions import PermissionDenied

MAX_FAILS = 5
BASE_LOCK_SECONDS = 900
MAX_LOCKOUT_ENTRIES = 10_000  # cap памяти против спама уникальными email
LOCKOUT_TTL_SECONDS = 86_400  # записи старше суток — мусор


class ProfileBackend(backends.ModelBackend):
    _lockout: dict[str, tuple[int, float]] = {}  # key -> (fails, locked_until_ts)

    @classmethod
    def _purge(cls) -> None:
        """Выкидываем истёкшие записи и капим размер (in-process dict, воркеров > 1)."""
        now = time.monotonic()
        for k in [k for k, v in cls._lockout.items() if v[1] and v[1] <= now]:
            cls._lockout.pop(k, None)
        if len(cls._lockout) > MAX_LOCKOUT_ENTRIES:
            overflow = len(cls._lockout) - MAX_LOCKOUT_ENTRIES
            for k, _ in sorted(cls._lockout.items(), key=lambda kv: kv[1][1])[:overflow]:
                cls._lockout.pop(k, None)

    @classmethod
    def _lock_remaining(cls, key: str) -> int:
        cls._purge()
        entry = cls._lockout.get(key)
        if entry and entry[1] > time.monotonic():
            return int(entry[1] - time.monotonic())
        return 0

    @classmethod
    def _register_fail(cls, key: str) -> int:
        fails, locked_until = cls._lockout.get(key, (0, 0.0))
        if locked_until > time.monotonic():
            return 0
        fails += 1
        if fails >= MAX_FAILS:
            locked_until = time.monotonic() + BASE_LOCK_SECONDS * (2 ** (fails - MAX_FAILS))
            cls._lockout[key] = (fails, locked_until)
            return int(locked_until - time.monotonic())
        cls._lockout[key] = (fails, 0.0)
        return 0

    @classmethod
    def _register_success(cls, key: str) -> None:
        cls._lockout.pop(key, None)

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or not password:
            return None
        lock_key = "login:%s" % email
        remaining = self._lock_remaining(lock_key)
        if remaining:
            raise PermissionDenied(
                "Слишком много неудачных попыток. Повторите через %d сек." % remaining
            )
        user = super().authenticate(request, username=email, password=password, **kwargs)
        if user is None:
            locked_for = self._register_fail(lock_key)
            if locked_for:
                raise PermissionDenied(
                    "Аккаунт временно заблокирован по числу неудачных попыток (%d сек.)." % locked_for
                )
            return None
        self._register_success(lock_key)
        return user

    def user_can_authenticate(self, user):
        # ModelBackend уже отвергает is_active=False (suspended). Добавляем email_verified.
        if not super().user_can_authenticate(user):
            return False
        return bool(getattr(user, "email_verified", False))
