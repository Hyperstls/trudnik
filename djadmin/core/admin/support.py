"""Служебные админки: жалобы, уведомления/outbox, чат, логи, аудит, push.

Паритет Flask: разбор жалоб — RPC review_complaint (block | dismiss) с авто-заморозкой.
"""
from django.contrib import messages
from django.contrib.admin import ModelAdmin

from core.audit import AuditAdminMixin, log_admin_action
from core.models import (
    AuditLog, Blacklist, EmailLog, Favorite, Message, MonetizationSetting,
    Notification, NotificationOutbox, PushSubscription, Receipt, SitePage,
    TariffSetting, UserReport,
)
from core.rpc import call_rpc


class UserReportAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "reporter", "reported", "reason", "status", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("reason", "reporter__full_name", "reported__full_name")
    raw_id_fields = ("reporter", "reported", "reviewed_by")
    actions = ("action_review_block", "action_review_dismiss")

    def get_readonly_fields(self, request, obj=None):
        base = ("id", "created_at", "reviewed_at")
        return base if obj is None else base + ("reporter", "reported", "reason", "status", "reviewed_by")

    def has_add_permission(self, request):
        return False

    def _review(self, request, queryset, action: str):
        for report in queryset.exclude(status="reviewed"):
            result = call_rpc("review_complaint", report.pk, action, request.user.pk) or {}
            log_admin_action(request, "review_complaint_%s" % action, "user_reports",
                             report.pk, new_data=result)
        messages.info(request, "Жалобы обработаны (%s)." % action)

    def action_review_block(self, request, queryset):
        self._review(request, queryset, "block")

    action_review_block.short_description = "Разобрать: нарушитель — блокировка (RPC review_complaint)"

    def action_review_dismiss(self, request, queryset):
        self._review(request, queryset, "dismiss")

    action_review_dismiss.short_description = "Разобрать: отклонить жалобу"


class NotificationAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "user", "type", "title", "is_read", "job", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "message", "user__full_name", "user__email")
    raw_id_fields = ("user", "job", "application")
    actions = ("action_mark_read",)
    date_hierarchy = "created_at"

    def action_mark_read(self, request, queryset):
        queryset.exclude(is_read=True).update(is_read=True)

    action_mark_read.short_description = "Отметить прочитанными"


class NotificationOutboxAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "user", "type", "title", "status", "attempts", "processed_at", "created_at")
    list_filter = ("status", "type")
    search_fields = ("title", "body", "user__email")
    raw_id_fields = ("user",)
    actions = ("action_retry",)
    ordering = ("-created_at",)

    def action_retry(self, request, queryset):
        for item in queryset.filter(status__in=("failed", "skipped")):
            item.status = "pending"
            item.attempts = 0
            item.processed_at = None
            item.save(update_fields=["status", "attempts", "processed_at"])
            log_admin_action(request, "outbox_retry", "notification_outbox", item.pk)
        messages.info(request, "Выбранные failed/skipped возвращены в очередь (drain подхватит).")

    action_retry.short_description = "Вернуть в очередь (retry)"


class MessageAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "application", "sender", "snippet", "client_message_id", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "sender__full_name")
    raw_id_fields = ("sender", "application")
    date_hierarchy = "created_at"

    @staticmethod
    def snippet(obj):
        return (obj.content or "")[:80]

    snippet.short_description = "текст"

    def has_add_permission(self, request):
        return False


class FavoriteAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("user", "target", "favorite_type", "created_at")
    raw_id_fields = ("user", "target")
    search_fields = ("user__full_name", "target__full_name")


class BlacklistAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("user", "blocked_user", "created_at")
    raw_id_fields = ("user", "blocked_user")
    search_fields = ("user__full_name", "blocked_user__full_name")


class EmailLogAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "user", "to_email", "subject", "status", "attempts", "sent_at", "created_at")
    list_filter = ("status", "template_name")
    search_fields = ("to_email", "subject", "error_message")

    def has_add_permission(self, request):
        return False


class PushSubscriptionAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "user", "endpoint_snippet", "created_at", "updated_at")
    raw_id_fields = ("user",)
    search_fields = ("endpoint", "user__email")

    @staticmethod
    def endpoint_snippet(obj):
        return obj.endpoint[:60]

    endpoint_snippet.short_description = "endpoint"

    def has_add_permission(self, request):
        return False


class AuditLogAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "user", "action", "table_name", "record_id", "ip_address", "created_at")
    list_filter = ("action", "table_name")
    search_fields = ("action", "table_name", "record_id")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReceiptAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "church_name", "amount", "status", "created_at", "resent_at")
    list_filter = ("status",)
    search_fields = ("church_name", "church_inn", "service_description")


class SitePageAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("slug", "title", "updated_at")
    search_fields = ("slug", "title", "content")


class MonetizationSettingAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("key", "value", "updated_at")
    search_fields = ("key",)


class TariffSettingAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("tariff_key", "price", "duration_days", "renewal_price", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("tariff_key",)


def register(site):
    site.register(UserReport, UserReportAdmin)
    site.register(Notification, NotificationAdmin)
    site.register(NotificationOutbox, NotificationOutboxAdmin)
    site.register(Message, MessageAdmin)
    site.register(Favorite, FavoriteAdmin)
    site.register(Blacklist, BlacklistAdmin)
    site.register(EmailLog, EmailLogAdmin)
    site.register(PushSubscription, PushSubscriptionAdmin)
    site.register(AuditLog, AuditLogAdmin)
    site.register(Receipt, ReceiptAdmin)
    site.register(SitePage, SitePageAdmin)
    site.register(MonetizationSetting, MonetizationSettingAdmin)
    site.register(TariffSetting, TariffSettingAdmin)
