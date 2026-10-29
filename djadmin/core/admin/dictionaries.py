"""Справочники: навыки (CRUD + RPC-удаление) и вероисповедания."""
from django.contrib import messages
from django.contrib.admin import ModelAdmin

from core.audit import AuditAdminMixin, log_admin_action
from core.models import Religion, Skill
from core.rpc import call_rpc


class SkillAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("name", "sort_order", "created_at", "users_count")
    search_fields = ("name",)
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    list_per_page = 100
    actions = ("action_delete_cascade",)

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_users_count=Count("user_skills"))

    def users_count(self, obj):
        return obj._users_count

    users_count.admin_order_field = "_users_count"
    users_count.short_description = "используют"

    def delete_model(self, request, obj):
        result = call_rpc("delete_skill_cascade", obj.pk) or {}
        log_admin_action(request, "delete_skill_cascade", "skills", obj.pk, new_data=result)

    def action_delete_cascade(self, request, queryset):
        deleted = 0
        for skill in queryset:
            result = call_rpc("delete_skill_cascade", skill.pk) or {}
            log_admin_action(request, "delete_skill_cascade", "skills", skill.pk, new_data=result)
            if result.get("success", True):
                deleted += 1
        messages.info(request, "Удалено каскадно: %d из %d." % (deleted, queryset.count()))

    action_delete_cascade.short_description = "Удалить каскадно (delete_skill_cascade)"

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ReligionAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("name", "sort_order", "created_at", "profiles_count")
    search_fields = ("name",)
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    list_per_page = 100

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_profiles_count=Count("profiles"))

    def profiles_count(self, obj):
        return obj._profiles_count

    profiles_count.admin_order_field = "_profiles_count"
    profiles_count.short_description = "профилей"


def register(site):
    site.register(Skill, SkillAdmin)
    site.register(Religion, ReligionAdmin)
