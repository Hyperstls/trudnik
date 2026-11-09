"""Справочники: навыки (CRUD + RPC-удаление), вероисповедания и объявления."""
from django.contrib import messages
from django.contrib.admin import ModelAdmin

from core.appeals import resolve_appeal
from core.audit import AuditAdminMixin, log_admin_action
from core.models import Announcement, RatingAppeal, Religion, Skill
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
    # R062: счётчик профилей удалён — FK profiles.religion_id DropColumn (164),
    # related_name "profiles" больше не существует.
    list_display = ("name", "sort_order", "created_at")
    search_fields = ("name",)
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    list_per_page = 100


class AnnouncementAdmin(AuditAdminMixin, ModelAdmin):
    list_display = (
        "kind", "title", "is_pinned", "is_active", "sort_order", "created_at",
    )
    list_display_links = ("kind", "title")
    list_filter = ("kind", "is_pinned", "is_active")
    search_fields = ("title", "body")
    list_editable = ("is_pinned", "is_active", "sort_order")
    ordering = ("-is_pinned", "sort_order", "-created_at")
    fields = (
        "kind", "title", "body", "url", "url_label",
        "is_pinned", "is_active", "sort_order",
    )
    list_per_page = 50
    date_hierarchy = "created_at"


class RatingAppealAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("rating", "appellant", "status", "created_at", "resolved_at")
    list_filter = ("status", "created_at")
    search_fields = ("appellant__email", "reason")
    readonly_fields = (
        "rating", "appellant", "reason", "created_at", "resolved_at",
        "resolver", "resolution_note", "status",
    )
    actions = ("action_approve", "action_reject")

    def has_add_permission(self, request):
        return False

    def action_approve(self, request, queryset):
        approved = 0
        for appeal in queryset:
            if resolve_appeal(appeal.pk, request.user, True) is not None:
                approved += 1
        messages.success(request, "Одобрено апелляций: %d." % approved)

    action_approve.short_description = "Апелляции: одобрить"

    def action_reject(self, request, queryset):
        rejected = 0
        for appeal in queryset:
            if resolve_appeal(appeal.pk, request.user, False) is not None:
                rejected += 1
        messages.success(request, "Отклонено апелляций: %d." % rejected)

    action_reject.short_description = "Апелляции: отклонить"


def register(site):
    site.register(Skill, SkillAdmin)
    site.register(Religion, ReligionAdmin)
    site.register(Announcement, AnnouncementAdmin)
    site.register(RatingAppeal, RatingAppealAdmin)
