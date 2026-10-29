"""Auth-бридж: bcrypt-совместимость с Flask/pgcrypto + fail-closed правила."""
import bcrypt
from django.test import TestCase

from core.models import Profile


def make_profile(email="user@example.com", password="Aa1!aaaa", **kw):  # pragma: allowlist secret
    kw.setdefault("full_name", "Иван Тестов")
    return Profile.objects.create_user(email=email, password=password, **kw)


class AuthBridgeTests(TestCase):
    def setUp(self):
        self.email = "bridge@example.com"
        self.password = "Aa1!aaaa"  # pragma: allowlist secret
        self.user = make_profile(self.email, self.password)

    def test_password_hash_bcrypt_2b(self):
        # пишем строго $2a$: его проверяет pgcrypto crypt() (login_direct_sql Flask)
        self.assertTrue(self.user.password.startswith("$2a$"))
        self.assertTrue(self.user.check_password(self.password))
        self.assertFalse(self.user.check_password("wrong"))

    def test_check_password_accepts_2b_hashes_too(self):
        """Существующие хэши, созданные python-bcrypt с $2b$ (Flask-side), тоже валидны."""
        self.user.password = bcrypt.hashpw(
            b"Aa1!aaaa", bcrypt.gensalt(rounds=4, prefix=b"2b")
        ).decode("ascii")
        self.assertTrue(self.user.check_password("Aa1!aaaa"))

    def test_set_password_keeps_bcrypt(self):
        self.user.set_password("Bb2!bbbb")
        self.user.save(update_fields=["password", "password_changed_at"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.password.startswith(("$2a$", "$2b$")))
        self.assertTrue(self.user.check_password("Bb2!bbbb"))

    def test_pgcrypto_can_verify_django_hash(self):
        """Ключевой паритет: pgcrypto crypt() (login_direct_sql Flask) проверяет
        хэш, записанный Django, без миграций данных."""
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute(
                "SELECT crypt(%s, password_hash) = password_hash FROM profiles WHERE id = %s",
                [self.password, self.user.pk],
            )
            self.assertTrue(cur.fetchone()[0])

    def test_email_stored_lowercase(self):
        self.assertEqual(Profile.objects.get(pk=self.user.pk).email, self.email)

    def test_admin_flags_from_role(self):
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        admin = Profile.objects.create_superuser("admin@example.com", "Aa1!aaaa")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.email_verified)

    def test_suspended_is_inactive(self):
        self.user.suspended = True
        self.assertFalse(self.user.is_active)

    def test_login_success(self):
        ok = self.client.login(username=self.email, password=self.password)
        self.assertTrue(ok)

    def test_login_wrong_password(self):
        self.assertFalse(self.client.login(username=self.email, password="nope"))  # pragma: allowlist secret

    def test_login_unverified_email_rejected(self):
        unverified = make_profile("unverified@example.com", email_verified=False)
        self.assertFalse(self.client.login(username="unverified@example.com", password="Aa1!aaaa"))  # pragma: allowlist secret

    def test_login_suspended_rejected(self):
        self.user.suspended = True
        self.user.save(update_fields=["suspended"])
        self.assertFalse(self.client.login(username=self.email, password=self.password))

    def test_lockout_after_failures(self):
        from core.auth_backend import ProfileBackend

        key = "login:%s" % self.email
        ProfileBackend._lockout.pop(key, None)
        for _ in range(5):
            self.client.login(username=self.email, password="bad")  # pragma: allowlist secret
        # после 5 неудач ключ заблокирован: успех по правильному паролю невозможен
        self.assertFalse(self.client.login(username=self.email, password=self.password))
        ProfileBackend._lockout.pop(key, None)  # чистим за другими тестами
