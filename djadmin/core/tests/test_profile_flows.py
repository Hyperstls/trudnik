"""Фаза 2в: профиль, смена пароля, избранное людей, чёрный список, приглашения."""
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Application, Blacklist, Favorite, Invitation, Job, Profile, Religion, Skill, UserSkill,
)
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = make_profile("prof-me@example.com")
        self.skill = Skill.objects.create(name="Проф-навык")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/profile").status_code, 302)

    def test_edit_fields_and_skills(self):
        response = self.client.post("/profile", {
            "action": "profile",
            "full_name": "Обновлённое Имя", "city": "Загорск",
            "desired_payment": "1234.00", "worker_visibility": "on",
            "religion": "", "skills": [str(self.skill.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Обновлённое Имя")
        self.assertEqual(self.user.city, "Загорск")
        self.assertEqual(
            list(UserSkill.objects.filter(user=self.user).values_list("skill_id", flat=True)),
            [self.skill.pk],
        )

    def test_profile_edit_cannot_modify_other_user(self):
        """IDOR (AUTH-P1-12): id другого пользователя в POST не меняет его профиль."""
        other = make_profile(
            "prof-other@example.com", full_name="Чужой Профиль", city="Чужойгород",
        )
        response = self.client.post("/profile", {
            "action": "profile",
            "id": str(other.pk),
            "full_name": "Взломанное Имя", "city": "Взломанск",
            "worker_visibility": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.user.full_name, "Взломанное Имя")
        self.assertEqual(self.user.city, "Взломанск")
        self.assertEqual(other.full_name, "Чужой Профиль")
        self.assertEqual(other.city, "Чужойгород")

    def test_skills_only_action(self):
        self.client.post("/profile", {"action": "skills", "skills": [str(self.skill.pk)]})
        self.assertTrue(UserSkill.objects.filter(user=self.user, skill=self.skill).exists())

    def test_profile_invalid_inn_rejected(self):
        # формат 12 цифр, но контрольная сумма не сходится (P102)
        response = self.client.post("/profile", {
            "action": "profile",
            "full_name": "Обновлённое Имя", "worker_visibility": "on",
            "inn": "500100732258",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "контрольную сумму")
        self.user.refresh_from_db()
        self.assertEqual(self.user.inn, "")

    def test_profile_invalid_contact_rejected(self):
        for contact in ("ab", "!!@@@$$"):
            response = self.client.post("/profile", {
                "action": "profile",
                "full_name": "Обновлённое Имя", "worker_visibility": "on",
                "contact": contact,
            })
            self.assertEqual(response.status_code, 200)
            self.user.refresh_from_db()
            self.assertFalse(self.user.contact)
        self.assertContains(response, "корректный контакт")

    def test_religion_not_editable(self):
        """P0-04 (152-ФЗ ст.10): вероисповедание не выбирается и не меняется."""
        religion = Religion.objects.create(name="Тестовое вероисповедание")
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="religion"')

        response = self.client.post("/profile", {
            "action": "profile",
            "full_name": "Без вероисповедания", "worker_visibility": "on",
            "religion": str(religion.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.religion_id)

        from core.admin.users import ProfileAdmin

        admin_fields = [f for _, opts in ProfileAdmin.fieldsets for f in opts["fields"]]
        self.assertNotIn("religion", admin_fields)

    def test_password_change_rpc_and_b10_stamp(self):
        old_stamp = self.user.password_changed_at
        response = self.client.post("/profile", {
            "action": "password",
            "current_password": "Aa1!aaaa", "new_password": "Aa1!zzzz",  # pragma: allowlist secret
            "confirm_password": "Aa1!zzzz",  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Aa1!zzzz"))
        self.assertFalse(self.user.check_password("Aa1!aaaa"))
        self.assertGreater(self.user.password_changed_at, old_stamp or timezone.now() - timedelta(days=1))
        # новая сессия с новым паролем
        self.assertTrue(self.client.login(username="prof-me@example.com", password="Aa1!zzzz"))  # pragma: allowlist secret

    def test_password_change_wrong_current(self):
        self.client.post("/profile", {
            "action": "password",
            "current_password": "WRONG", "new_password": "Aa1!zzzz",  # pragma: allowlist secret
            "confirm_password": "Aa1!zzzz",  # pragma: allowlist secret
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Aa1!aaaa"))

    def test_password_change_invalidates_other_sessions(self):
        """P1-06: текущая сессия жива, остальные сессии пользователя — нет."""
        client_a = Client()
        client_b = Client()
        client_a.force_login(self.user)
        client_b.force_login(self.user)

        response = client_a.post("/profile", {
            "action": "password",
            "current_password": "Aa1!aaaa", "new_password": "Aa1!zzzz",  # pragma: allowlist secret
            "confirm_password": "Aa1!zzzz",  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 302)

        other = client_b.get("/profile")
        self.assertEqual(other.status_code, 302)
        self.assertIn("/login", other.url)

        self.assertEqual(client_a.get("/profile").status_code, 200)


class PeopleRelationsTests(TestCase):
    def setUp(self):
        self.me = make_profile("rel-me@example.com")
        self.other = make_profile("rel-other@example.com", role="worker")
        self.client.force_login(self.me)

    def test_favorite_toggle(self):
        self.client.post(reverse("core:people_favorite_toggle", args=[self.other.pk]))
        self.assertTrue(Favorite.objects.filter(user=self.me, target=self.other).exists())
        self.client.post(reverse("core:people_favorite_toggle", args=[self.other.pk]))
        self.assertFalse(Favorite.objects.filter(user=self.me, target=self.other).exists())

    def test_cannot_favorite_self(self):
        self.client.post(reverse("core:people_favorite_toggle", args=[self.me.pk]))
        self.assertFalse(Favorite.objects.filter(user=self.me).exists())

    def test_block_unblock(self):
        self.client.post(reverse("core:people_block", args=[self.other.pk]))
        self.assertTrue(Blacklist.objects.filter(user=self.me, blocked_user=self.other).exists())
        self.client.post(reverse("core:people_unblock", args=[self.other.pk]))
        self.assertFalse(Blacklist.objects.exists())


class InvitationTests(TestCase):
    def setUp(self):
        self.employer = make_profile("inv-emp@example.com")
        self.worker = make_profile("inv-worker@example.com", role="worker")
        self.job = make_job(self.employer, work_type="Пригласительная работа")

    def _invite(self):
        self.client.force_login(self.employer)
        return self.client.post(
            reverse("core:invite_worker", args=[self.worker.pk]), {"job_id": str(self.job.pk)}
        )

    def test_invite_creates_pending(self):
        self._invite()
        inv = Invitation.objects.get(job=self.job, worker=self.worker)
        self.assertEqual(inv.status, "pending")

    def test_duplicate_invite_rejected(self):
        self._invite()
        self._invite()
        self.assertEqual(Invitation.objects.filter(job=self.job, worker=self.worker).count(), 1)

    def test_cannot_invite_hidden_worker(self):
        self.worker.worker_visibility = False
        self.worker.save(update_fields=["worker_visibility"])
        self._invite()
        self.assertFalse(Invitation.objects.exists())

    def test_cannot_invite_to_foreign_or_closed_job(self):
        stranger_job = make_job(make_profile("stranger-job@example.com"), work_type="Чужая")
        self.client.force_login(self.employer)
        self.client.post(reverse("core:invite_worker", args=[self.worker.pk]), {"job_id": str(stranger_job.pk)})
        self.client.post(reverse("core:invite_worker", args=[self.worker.pk]), {"job_id": ""})
        self.assertFalse(Invitation.objects.exists())

    def test_accept_via_rpc_creates_application(self):
        self._invite()
        inv = Invitation.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.worker)
        self.client.post(reverse("core:invitation_respond", args=[inv.pk, "accept"]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, "accepted")
        self.assertTrue(Application.objects.filter(job=self.job, worker=self.worker).exists())

    def test_decline(self):
        self._invite()
        inv = Invitation.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.worker)
        self.client.post(reverse("core:invitation_respond", args=[inv.pk, "decline"]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, "rejected")

    def test_respond_twice_rejected(self):
        self._invite()
        inv = Invitation.objects.get(job=self.job, worker=self.worker)
        self.client.force_login(self.worker)
        self.client.post(reverse("core:invitation_respond", args=[inv.pk, "decline"]))
        response = self.client.post(reverse("core:invitation_respond", args=[inv.pk, "accept"]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, "rejected")

    def test_invitations_page_lists_both_sides(self):
        self._invite()
        self.client.force_login(self.worker)
        self.assertContains(self.client.get(reverse("core:invitations")), "Пригласительная работа")
        self.client.force_login(self.employer)
        self.assertContains(self.client.get(reverse("core:invitations")), self.worker.full_name)
