"""Админка заданий: воспроизводит admin_jobs + applications Flask.

Бизнес-правила (паритет Flask):
- удаление — RPC delete_job_cascade, bulk ≤ 50;
- запрет completed → open при существующих оценках (RLS/RPC-инвариант);
- cancel/restore — RPC cancel_job_atomic / restore_job_atomic.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.admin import ModelAdmin, TabularInline
from django.utils import timezone

from core.audit import AuditAdminMixin, log_admin_action
from core.models import (
    Application, ArchiveContactPayment, EmployerSubscription, Invitation,
    Job, JobFavorite, JobPayment, JobPhoto, JobSkill, Rating,
)
from core.notifications import enqueue_notification
from core.rpc import call_rpc

BULK_DELETE_LIMIT = 50


class JobPhotoInline(AuditAdminMixin, TabularInline):
    model = JobPhoto
    extra = 0
    fields = ("photo_url", "order_num")
    verbose_name = "фото"
    verbose_name_plural = "Фото задания"


class JobAdmin(AuditAdminMixin, ModelAdmin):
    list_display = (
        "work_type", "organization_name", "employer", "city", "status",
        "moderation_status", "payment_amount", "date_time", "workers_progress",
        "is_promoted", "created_at",
    )
    list_filter = ("status", "moderation_status", "is_promoted", "tariff", "city", "created_at")
    search_fields = ("organization_name", "work_type", "city", "address", "detailed_description")
    list_select_related = ("employer",)
    raw_id_fields = ("employer",)
    date_hierarchy = "created_at"
    list_per_page = 50
    actions = (
        "action_moderation_approve", "action_moderation_reject",
        "action_cancel", "action_restore", "action_delete_cascade",
        "action_set_status_open",
    )
    inlines = (JobPhotoInline,)

    fieldsets = (
        (None, {"fields": ("employer", "work_type", "organization_name", "status", "date_time")}),
        ("Описание", {"fields": (
            "org_description", "object_description", "detailed_description",
            "address", "city", "lat", "lng",
        )}),
        ("Условия", {"fields": (
            "payment_amount", "max_workers", "current_workers", "photo_urls",
        )}),
        ("Продвижение/оплата", {"fields": ("tariff", "is_paid", "paid_at", "expires_at", "is_promoted", "promoted_until")}),
        ("Модерация", {"fields": ("moderation_status", "moderation_reason")}),
        ("Служебное (RO)", {"fields": ("id", "created_at", "updated_at", "skills_display")}),
    )
    readonly_fields = ("id", "created_at", "updated_at", "current_workers", "skills_display")

    @staticmethod
    def workers_progress(obj):
        return "%d / %s" % (obj.current_workers or 0, obj.max_workers or "—")

    workers_progress.short_description = "работники"

    @staticmethod
    def skills_display(obj):
        names = list(JobSkill.objects.filter(job=obj).select_related("skill")
                     .values_list("skill__name", flat=True))
        return ", ".join(names) if names else "—"

    skills_display.short_description = "навыки"

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            old = Job.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
            if old == Job.Status.COMPLETED and obj.status == Job.Status.OPEN:
                if Rating.objects.filter(job=obj).exists():
                    messages.error(
                        request,
                        "Нельзя вернуть в «Открыта» завершённое задание с оценками.",
                    )
                    return
        super().save_model(request, obj, form, change)

    def action_moderation_approve(self, request, queryset):
        approved = 0
        for job in queryset.filter(moderation_status=Job.ModerationStatus.REVIEW):
            Job.objects.filter(pk=job.pk).update(
                moderation_status=Job.ModerationStatus.OK, moderation_reason=None,
            )
            enqueue_notification(
                job.employer_id, "job_moderation", "Задание одобрено",
                "Ваше задание «%s» опубликовано в каталоге." % (job.work_type or "Задание"),
                {"job_id": str(job.pk), "link": "/jobs/%s" % job.pk},
            )
            log_admin_action(request, "moderation_approve", "jobs", job.pk)
            approved += 1
        messages.info(request, "Одобрено заданий: %d." % approved)

    action_moderation_approve.short_description = "Модерация: одобрить"

    def action_moderation_reject(self, request, queryset):
        rejected = 0
        for job in queryset.exclude(moderation_status=Job.ModerationStatus.REJECTED):
            reason = "Отклонено модератором"
            Job.objects.filter(pk=job.pk).update(
                moderation_status=Job.ModerationStatus.REJECTED,
                moderation_reason=reason,
            )
            enqueue_notification(
                job.employer_id, "job_moderation", "Задание отклонено",
                "Задание «%s» не прошло модерацию. Исправьте описание и сохраните его."
                % (job.work_type or "Задание"),
                {"job_id": str(job.pk), "link": "/jobs/%s" % job.pk},
            )
            log_admin_action(request, "moderation_reject", "jobs", job.pk)
            rejected += 1
            recent_rejected = Job.objects.filter(
                employer_id=job.employer_id,
                moderation_status=Job.ModerationStatus.REJECTED,
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).count()
            if recent_rejected >= 5:
                is_admin = job.employer.role == "admin"
                if not is_admin:
                    call_rpc(
                        "suspend_user", job.employer_id,
                        "Авто-модерация: %d отклонённых заданий за 24ч" % recent_rejected,
                    )
        messages.info(request, "Отклонено заданий: %d." % rejected)

    action_moderation_reject.short_description = "Модерация: отклонить"

    def action_cancel(self, request, queryset):
        for job in queryset:
            result = call_rpc("cancel_job_atomic", job.pk, job.employer_id) or {}
            log_admin_action(request, "cancel_job_atomic", "jobs", job.pk, new_data=result)
        messages.info(request, "Отмена выполнена (RPC): %d." % queryset.count())

    action_cancel.short_description = "Отменить (cancel_job_atomic)"

    def action_restore(self, request, queryset):
        for job in queryset:
            result = call_rpc("restore_job_atomic", job.pk, job.employer_id) or {}
            log_admin_action(request, "restore_job_atomic", "jobs", job.pk, new_data=result)
        messages.info(request, "Восстановление выполнено (RPC): %d." % queryset.count())

    action_restore.short_description = "Восстановить (restore_job_atomic)"

    def action_set_status_open(self, request, queryset):
        blocked = [str(j.pk) for j in queryset if j.status == Job.Status.COMPLETED
                   and Rating.objects.filter(job=j).exists()]
        if blocked:
            messages.error(request, "Запрещено completed→open при оценках: %s" % ", ".join(blocked[:5]))
            return
        queryset.exclude(status=Job.Status.OPEN).update(status=Job.Status.OPEN)
        for job in queryset:
            log_admin_action(request, "set_status_open", "jobs", job.pk)
        messages.info(request, "Статус: open.")

    action_set_status_open.short_description = "Открыть (guard: без оценок)"

    def action_delete_cascade(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        if len(ids) > BULK_DELETE_LIMIT:
            messages.error(request, "Массовое удаление: не больше %d за раз." % BULK_DELETE_LIMIT)
            return
        deleted = 0
        for jid in ids:
            result = call_rpc("delete_job_cascade", jid) or {}
            log_admin_action(request, "delete_job_cascade", "jobs", jid, new_data=result)
            if result.get("success", True):
                deleted += 1
        messages.info(request, "Удалено каскадом: %d из %d." % (deleted, len(ids)))

    action_delete_cascade.short_description = "Удалить каскадно (≤%d)" % BULK_DELETE_LIMIT

    def delete_model(self, request, obj):
        result = call_rpc("delete_job_cascade", obj.pk) or {}
        log_admin_action(request, "delete_job_cascade", "jobs", obj.pk, new_data=result)

    def delete_queryset(self, request, queryset):
        self.action_delete_cascade(request, queryset)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ApplicationAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "job", "worker", "status", "contact_paid", "created_at", "updated_at")
    list_filter = ("status", "contact_paid", "created_at")
    search_fields = ("job__work_type", "job__organization_name", "worker__full_name", "worker__email")
    autocomplete_fields = ("job", "worker")
    list_select_related = ("job", "worker")
    list_per_page = 50

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("id", "job", "worker", "created_at", "updated_at")
        return ("id", "created_at", "updated_at")


class RatingAdmin(AuditAdminMixin, ModelAdmin):
    list_display = (
        "rated_user", "rater_user", "job", "rating", "rating_type", "target_type",
        "moderation_status", "published_at", "created_at",
    )
    list_filter = ("rating", "rating_type", "target_type", "moderation_status", "created_at")
    raw_id_fields = ("rated_user", "rater_user", "job")
    search_fields = ("rated_user__full_name", "rater_user__full_name", "comment")
    actions = ("action_moderation_approve", "action_moderation_hide")

    def action_moderation_approve(self, request, queryset):
        from django.utils import timezone

        approved = 0
        for rating in queryset:
            Rating.objects.filter(pk=rating.pk).update(
                moderation_status=Rating.ModerationStatus.OK,
                moderation_reason=None,
                published_at=rating.published_at or timezone.now(),
            )
            log_admin_action(request, "rating_approve", "ratings", rating.pk)
            approved += 1
        messages.info(request, "Одобрено отзывов: %d." % approved)

    action_moderation_approve.short_description = "Отзывы: одобрить и опубликовать"

    def action_moderation_hide(self, request, queryset):
        hidden = 0
        for rating in queryset:
            Rating.objects.filter(pk=rating.pk).update(
                moderation_status=Rating.ModerationStatus.HIDDEN,
                moderation_reason="Скрыто модератором",
            )
            log_admin_action(request, "rating_hide", "ratings", rating.pk)
            hidden += 1
        messages.info(request, "Скрыто отзывов: %d." % hidden)

    action_moderation_hide.short_description = "Отзывы: скрыть"

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("id", "created_at", "updated_at", "published_at", "rating_type", "target_type")
        return ("id", "created_at", "updated_at", "published_at")


class InvitationAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("job", "worker", "status", "created_at", "responded_at")
    list_filter = ("status",)
    raw_id_fields = ("job", "employer", "worker")
    search_fields = ("job__work_type", "worker__full_name")


class JobFavoriteAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("user", "job", "created_at")
    raw_id_fields = ("user", "job")
    search_fields = ("user__full_name", "job__work_type")


class EmployerSubscriptionAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("employer", "tariff", "jobs_remaining", "is_promoted", "promoted_until", "updated_at")
    list_filter = ("tariff", "is_promoted")
    raw_id_fields = ("employer",)
    search_fields = ("employer__full_name", "employer__email")


class JobPaymentAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("job", "employer", "amount", "tariff", "type", "status", "paid_at", "created_at")
    list_filter = ("status", "tariff", "type")
    raw_id_fields = ("job", "employer")
    search_fields = ("transaction_id",)


class ArchiveContactPaymentAdmin(AuditAdminMixin, ModelAdmin):
    list_display = ("id", "employer_id", "worker_id", "amount", "status", "created_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("transaction_id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # архив — только просмотр


def register(site):
    site.register(Job, JobAdmin)
    site.register(Application, ApplicationAdmin)
    site.register(Rating, RatingAdmin)
    site.register(Invitation, InvitationAdmin)
    site.register(JobFavorite, JobFavoriteAdmin)
    site.register(EmployerSubscription, EmployerSubscriptionAdmin)
    site.register(JobPayment, JobPaymentAdmin)
    site.register(ArchiveContactPayment, ArchiveContactPaymentAdmin)
