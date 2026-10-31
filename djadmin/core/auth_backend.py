"""Auth-бридж: вход в админку по email+bcrypt из profiles.

Совместимость хэшей: один и тот же формат $2b$/$2a$ 12 раундов используют
Flask (app/utils/auth.py), pgcrypto crypt() и Django BCryptPasswordHasher.
Fail-closed: suspended → отказ (is_active=False), неподтверждённый email → отказ.
Лок-аут: 5 неудач → экспоненциальный бэкоф (2**count) в общем кэше
(Redis в проде, не в памяти воркера); сбой кэша → вход временно недоступен.
"""
from django.contrib.auth import backends
from django.core.cache import cache
from django.core.exceptions import PermissionDenied

MAX_FAILS = 5
FAIL_WINDOW = 900  # окно накопления неудач аккаунта, сек
BASE_LOCK_SECONDS = 900  # первая блокировка, далее BASE * 2**count
COUNT_TTL_SECONDS = 86_400  # счётчик серий блокировок живёт сутки
CACHE_UNAVAILABLE_TEXT = "Сервис входа временно недоступен. Попробуйте позже."
LOCKOUT_TEXT = "Аккаунт временно заблокирован по числу неудачных попыток (%d сек.)."


class ProfileBackend(backends.ModelBackend):
    @staticmethod
    def _lock_key(email: str) -> str:
        return "login_lock:%s" % email

    @staticmethod
    def _fail_key(email: str) -> str:
        return "login_fail:%s" % email

    @staticmethod
    def _count_key(email: str) -> str:
        return "login_count:%s" % email

    @classmethod
    def _lock_remaining(cls, lock_key: str) -> int:
        """Секунды до конца блокировки; 0 — не заблокирован. Сбой кэша — fail-closed."""
        try:
            value = cache.get(lock_key)
        except Exception as exc:
            raise PermissionDenied(CACHE_UNAVAILABLE_TEXT) from exc
        return int(value) if value else 0

    @classmethod
    def _register_fail(cls, fail_key: str, lock_key: str, count_key: str) -> int:
        """+1 к неудачам; на 5-й — блокировка с экспонентой 2**(число прошлых блокировок)."""
        try:
            if cache.add(fail_key, 1, FAIL_WINDOW):
                fails = 1
            else:
                try:
                    fails = cache.incr(fail_key)
                except ValueError:  # ключ истёк между add и incr
                    cache.set(fail_key, 1, FAIL_WINDOW)
                    fails = 1
            if fails < MAX_FAILS:
                return 0
            lockouts = int(cache.get(count_key) or 0)
            lock_seconds = BASE_LOCK_SECONDS * (2 ** lockouts)
            cache.set(lock_key, lock_seconds, lock_seconds)
            cache.set(count_key, lockouts + 1, COUNT_TTL_SECONDS)
            cache.delete(fail_key)
        except Exception as exc:
            raise PermissionDenied(CACHE_UNAVAILABLE_TEXT) from exc
        return lock_seconds

    @classmethod
    def _register_success(cls, lock_key: str, fail_key: str, count_key: str) -> None:
        try:
            cache.delete_many([lock_key, fail_key, count_key])
        except Exception as exc:
            raise PermissionDenied(CACHE_UNAVAILABLE_TEXT) from exc

    @classmethod
    def lock_remaining(cls, email: str) -> int:
        """Сколько секунд аккаунт ещё заблокирован (0 — не заблокирован).

        Django's authenticate() глушит PermissionDenied из бэкенда
        (django/contrib/auth/__init__.py), поэтому view уточняет блокировку
        здесь, чтобы показать сообщение вместо общего «неверный пароль».
        """
        email = (email or "").strip().lower()
        if not email:
            return 0
        return cls._lock_remaining(cls._lock_key(email))

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or not password:
            return None
        lock_key, fail_key, count_key = self._lock_key(email), self._fail_key(email), self._count_key(email)
        remaining = self._lock_remaining(lock_key)
        if remaining:
            raise PermissionDenied(LOCKOUT_TEXT % remaining)
        user = super().authenticate(request, username=email, password=password, **kwargs)
        if user is None:
            locked_for = self._register_fail(fail_key, lock_key, count_key)
            if locked_for:
                raise PermissionDenied(LOCKOUT_TEXT % locked_for)
            return None
        self._register_success(lock_key, fail_key, count_key)
        return user

    def user_can_authenticate(self, user):
        # ModelBackend уже отвергает is_active=False (suspended). Добавляем email_verified.
        if not super().user_can_authenticate(user):
            return False
        return bool(getattr(user, "email_verified", False))
