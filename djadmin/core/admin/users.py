"""Админка профилей: воспроизводит admin_users + admin_verification Flask.

Бизнес-правила (паритет Flask):
- смену роли запрещаем себе и другим админам;
- удаление — только RPC delete_user_cascade, bulk ≤ 20, админов удалять нельзя;
- suspend/unsuspend — RPC suspend_user/unsuspend_user;
- верификация: verification_status → approved/rejected + verified_at/provider=manual;
- навыки — отдельный редактор (raw SQL, составной PK).
"""
import uuid

from django.contrib import messages
from django.contrib.admin import ModelAdmin, TabularInline
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone

from core.audit import AuditAdminMixin, log_admin_action
from core.models import EmployerDetail, Profile, Skill, UserSkill
from core.rpc import call_rpc, call_rpc_void, sync_user_skills_raw

BULK_DELETE_LIMIT = 20


class EmployerDetailInline(AuditAdminMixin, TabularInline):
    model = EmployerDetail
    extra = 0
    fields = ("name", "company_name", "inn", "city", "address", "is_self_employed")
    verbose_name = "карточка работодателя"
    verbose_name_plural = "Карточка работодателя"


class ProfileAdmin(AuditAdminMixin, ModelAdmin):
    list_display = (
        "full_name", "email", "role", "city", "verification_status",
        "email_verified", "suspended", "worker_visibility", "rating", "created_at",
    )
    list_filter = ("role", "verification_status", "suspended", "email_verified", "worker_visibility", "created_at")
    search_fields = ("full_name", "email", "city", "phone", "inn")
    ordering = ("-created_at",)
    list_per_page = 50
    actions = (
        "action_suspend", "action_unsuspend", "action_verify_approve", "action_verify_reject",
        "action_set_email_verified", "action_delete_cascade",
    )
    inlines = (EmployerDetailInline,)

    fieldsets = (
        (None, {"fields": ("email", "password_hint", "role", "full_name")}),
        ("Контакты и анкета", {"fields": (
            "phone", "city", "age", "bio", "experience", "desired_payment",
            "religion", "portfolio_link", "contact", "email_public",
            "inn", "is_self_employed",
        )}),
        ("Статусы", {"fields": (
            "email_verified", "verification_status", "verification_provider",
            "suspended", "suspended_reason", "worker_visibility",
        )}),
        ("Служебное (RO)", {"fields": (
            "id", "avatar_url", "photo_url", "rating", "total_reviews", "ratings_count",
            "created_at", "updated_at", "consented_at", "password_changed_at",
            "notification_prefs", "messenger_user_id",
        )}),
    )
    readonly_fields = (
        "id", "password_hint", "avatar_url", "photo_url", "rating", "total_reviews",
        "ratings_count", "created_at", "updated_at", "consented_at", "password_changed_at",
        "notification_prefs", "messenger_user_id",
    )

    @staticmethod
    def password_hint(obj):
        return "установлен" if obj.password else "НЕТ"

    password_hint.short_description = "пароль"

    def get_readonly_fields(self, request, obj=None):
        # Собственный профиль: роль менять нельзя (паритет guard'а Flask).
        if obj and obj.pk == request.user.pk:
            return tuple(self.readonly_fields) + ("role",)
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if change:
            old_role = Profile.objects.filter(pk=obj.pk).values_list("role", flat=True).first()
            if obj.pk == request.user.pk and "role" in form.changed_data:
                messages.error(request, "Нельзя менять собственную роль.")
                return
            if old_role == Profile.Role.ADMIN and "role" in form.changed_data:
                messages.error(request, "Запрещено менять роль администратора.")
                return
        if "verification_status" in form.changed_data and (
            obj.verification_status == Profile.VerificationStatus.APPROVED
        ):
            obj.verified_at = obj.verified_at or timezone.now()
            obj.verification_provider = "manual"
        super().save_model(request, obj, form, change)

    # ── Действия ──────────────────────────────────────────────────────────
    def action_suspend(self, request, queryset):
        admins = queryset.filter(role=Profile.Role.ADMIN)
        if admins.exists():
            messages.error(request, "Администратора нельзя заблокировать.")
            return
        for profile in queryset:
            call_rpc_void("suspend_user", profile.pk, "Django admin: блокировка")
            log_admin_action(request, "suspend_user", "profiles", profile.pk,
                             new_data={"reason": "Django admin"})
        messages.info(request, "Блокировка выполнена (RPC suspend_user): %d." % queryset.count())

    action_suspend.short_description = "Заблокировать (suspend_user)"

    def action_unsuspend(self, request, queryset):
        for profile in queryset:
            call_rpc_void("unsuspend_user", profile.pk)
            log_admin_action(request, "unsuspend_user", "profiles", profile.pk)
        messages.info(request, "Разблокировка выполнена: %d." % queryset.count())

    action_unsuspend.short_description = "Разблокировать (unsuspend_user)"

    def action_verify_approve(self, request, queryset):
        for profile in queryset:
            profile.verification_status = Profile.VerificationStatus.APPROVED
            profile.verified_at = profile.verified_at or timezone.now()
            profile.verification_provider = "manual"
            profile.save(update_fields=["verification_status", "verified_at", "verification_provider"])
            log_admin_action(request, "verify_approve", "profiles", profile.pk)
        messages.info(request, "Верификация подтверждена: %d." % queryset.count())

    action_verify_approve.short_description = "Верификация: подтвердить"

    def action_verify_reject(self, request, queryset):
        for profile in queryset:
            profile.verification_status = Profile.VerificationStatus.REJECTED
            profile.save(update_fields=["verification_status"])
            log_admin_action(request, "verify_reject", "profiles", profile.pk)
        messages.info(request, "Верификация отклонена: %d." % queryset.count())

    action_verify_reject.short_description = "Верификация: отклонить"

    def action_set_email_verified(self, request, queryset):
        for profile in queryset.exclude(email_verified=True):
            profile.email_verified = True
            profile.save(update_fields=["email_verified"])
            log_admin_action(request, "set_email_verified", "profiles", profile.pk)
        messages.info(request, "Email подтверждён выбранным.")

    action_set_email_verified.short_description = "Подтвердить email"

    def action_delete_cascade(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        if len(ids) > BULK_DELETE_LIMIT:
            messages.error(request, "Массовое удаление: не больше %d за раз." % BULK_DELETE_LIMIT)
            return
        if queryset.filter(role=Profile.Role.ADMIN).exists():
            messages.error(request, "Удаление администраторов запрещено.")
            return
        for pid in ids:
            result = call_rpc("delete_user_cascade", pid) or {}
            log_admin_action(request, "delete_user_cascade", "profiles", pid, new_data=result)
        messages.info(request, "Удалено каскадом: %d." % len(ids))

    action_delete_cascade.short_description = "Удалить каскадно (≤%d, без админов)" % BULK_DELETE_LIMIT

    def delete_model(self, request, obj):
        if obj.role == Profile.Role.ADMIN:
            messages.error(request, "Удаление администратора запрещено.")
            return
        result = call_rpc("delete_user_cascade", obj.pk) or {}
        log_admin_action(request, "delete_user_cascade", "profiles", obj.pk, new_data=result)

    def delete_queryset(self, request, queryset):
        self.action_delete_cascade(request, queryset)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # только каскадное удаление через RPC
        return actions

    # ── Редактор навыков ─────────────────────────────────────────────────
    def get_urls(self):
        urls = super().get_urls()
        my = [
            path(
                "<uuid:object_id>/skills/",
                self.admin_site.admin_view(self.skills_view),
                name="core_profile_skills",
            ),
        ]
        return my + urls

    def skills_view(self, request, object_id):
        profile = get_object_or_404(Profile, pk=object_id)
        all_skills = list(Skill.objects.order_by("sort_order", "name").values("id", "name"))
        selected = set(UserSkill.objects.filter(user=profile).values_list("skill_id", flat=True))
        if request.method == "POST":
            chosen = {uuid.UUID(s) for s in request.POST.getlist("skills") if s}
            with transaction.atomic():
                count = sync_user_skills_raw(profile.pk, chosen)
            log_admin_action(request, "sync_user_skills", "user_skills", profile.pk,
                             new_data={"count": count, "skills": [str(c) for c in sorted(chosen)]})
            messages.info(request, "Навыки обновлены: %d." % count)
            return HttpResponseRedirect(reverse("admin:core_profile_skills", args=[profile.pk]))
        return render(request, "admin/skills_editor.html", {
            **self.admin_site.each_context(request),
            "title": "Навыки: %s" % profile,
            "profile": profile,
            "all_skills": all_skills,
            "selected": selected,
        })


def register(site):
    site.register(Profile, ProfileAdmin)
