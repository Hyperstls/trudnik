"""Вызов SECURITY DEFINER RPC из Django + raw-SQL синхронизация навыков."""
from django.test import TestCase

from core.models import Profile, Skill, UserSkill
from core.rpc import call_rpc, call_rpc_void, sync_user_skills_raw
from core.tests.test_auth import make_profile


class RpcTests(TestCase):
    def setUp(self):
        self.user = make_profile("rpc@example.com")

    def test_suspend_unsuspend_rpc(self):
        call_rpc_void("suspend_user", self.user.pk, "тест блокировки")
        self.assertTrue(Profile.objects.get(pk=self.user.pk).suspended)
        call_rpc_void("unsuspend_user", self.user.pk)
        self.assertFalse(Profile.objects.get(pk=self.user.pk).suspended)

    def test_call_rpc_returns_dict(self):
        result = call_rpc("suspend_user", self.user.pk, "тест")
        self.assertIsInstance(result, dict)

    def test_sync_user_skills_raw(self):
        s1 = Skill.objects.create(name="Тестовый навык 1", sort_order=1)
        s2 = Skill.objects.create(name="Тестовый навык 2", sort_order=2)
        count = sync_user_skills_raw(self.user.pk, {s1.pk, s2.pk})
        self.assertEqual(count, 2)
        self.assertEqual(
            set(UserSkill.objects.filter(user=self.user).values_list("skill_id", flat=True)),
            {s1.pk, s2.pk},
        )
        # замена набора, а не дополнение
        count = sync_user_skills_raw(self.user.pk, {s1.pk})
        self.assertEqual(count, 1)
        self.assertEqual(
            list(UserSkill.objects.filter(user=self.user).values_list("skill_id", flat=True)),
            [s1.pk],
        )
