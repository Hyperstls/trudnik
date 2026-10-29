"""Справочники: навыки (CRUD + RPC-удаление) и вероисповедания."""
from django.contrib import messages
from django.contrib.admin import ModelAdmin

from core.audit import AuditAdminMixin, log_admin_action
from core.models import Religion, Skill, UserSkill
from core.rpc import call_rpc


class SkillAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("name", "sort_order", "created_at", "users_count")
    search_fields = ("name",)
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    actions = ("action_delete_cascade",)

    def users_count(self, obj):
        return UserSkill.objects.filter(skill=obj).count()

    users_count.short_description = "используют"

    def delete_model(self, request, obj):
        result = call_rpc("delete_skill_cascade", obj.pk) or {}
        log_admin_action(request, "delete_skill_cascade", "skills", obj.pk, new_data=result)

    def action_delete_cascade(self, request, queryset):
        for skill in queryset:
            result = call_rpc("delete_skill_cascade", skill.pk) or {}
            log_admin_action(request, "delete_skill_cascade", "skills", skill.pk, new_data=result)
        messages.info(request, "Удалено каскадно: %d." % queryset.count())

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

    def profiles_count(self, obj):
        return obj.profiles.count()

    profiles_count.short_description = "профилей"


def register(site):
    site.register(Skill, SkillAdmin)
    site.register(Religion, ReligionAdmin)
