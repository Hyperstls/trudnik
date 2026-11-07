"""Админка внутреннего error tracking: только чтение, без ПДн (R040)."""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.admin import ModelAdmin
from django.utils import timezone
from django.utils.html import format_html

from core.audit import AuditAdminMixin
from core.models import ErrorEvent

PURGE_AFTER_DAYS = 90


class ErrorEventAdmin(AuditAdminMixin, ModelAdmin):
    """События необработанных 500: просмотр, фильтры, очистка старых.

    Read-only: события пишет middleware, ручное редактирование бессмысленно и
    опасно. В списке нет email/full_name — только user_id (псевдоним).
    """

    list_display = ("created_at", "exception_type", "method", "path", "status_code", "user_id")
    list_filter = ("exception_type", "method", "created_at")
    search_fields = ("path", "exception_type")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    # FK user и сырой frames исключены: иначе read-only change-view рендерит
    # Profile.__str__ (full_name + email) и дублирует фреймы. Показываем только
    # user_id и frames_pretty.
    exclude = ("user", "frames")
    readonly_fields = (
        "id", "created_at", "exception_type", "path", "method",
        "status_code", "user_id", "frames_pretty",
    )
    actions = ("action_purge_old",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def frames_pretty(self, obj):
        if not obj.frames:
            return "—"
        return format_html(
            "<pre style=\"white-space:pre-wrap;margin:0\">{}</pre>",
            json.dumps(obj.frames, ensure_ascii=False, indent=2),
        )

    frames_pretty.short_description = "фреймы"

    def action_purge_old(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=PURGE_AFTER_DAYS)
        deleted, _ = ErrorEvent.objects.filter(created_at__lt=cutoff).delete()
        messages.info(
            request,
            "Удалено событий старше %d дней: %d." % (PURGE_AFTER_DAYS, deleted),
        )

    action_purge_old.short_description = "Удалить события старше 90 дней"

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


def register(site):
    site.register(ErrorEvent, ErrorEventAdmin)
