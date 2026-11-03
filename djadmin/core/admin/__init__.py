"""Регистрация админки «Трудник»: собственный AdminSite с дашбордом.

Модули: users (профили/верификация/навыки), jobs (задания/отклики/платежи),
support (жалобы/уведомления/логи/аудит), dictionaries (справочники/контент).
"""
from django.contrib.admin import AdminSite

from . import dictionaries, jobs, support, users

# Подстроки в имени переменной окружения, означающие секрет: значение такой
# переменной на /admin/env/ НЕ выводится (только факт наличия).
SECRET_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "KEY",
    "DATABASE_URL",
    "DATABASE_ADMIN_URL",
    "DJANGO_DATABASE_URL",
    "REDIS_URL",
    "SMTP_",
    "MAX_BOT",
    "PGRST",
    "VAPID",
    "WEBSOCKET_JWT",
    "METRICS",
)


def mask_env(environ):
    """Имена переменных + факт наличия; секретные значения заменяются маской."""
    masked = {}
    for name, value in environ.items():
        upper = name.upper()
        if any(marker in upper for marker in SECRET_ENV_MARKERS):
            masked[name] = "****** (set)" if value else "(empty)"
        else:
            masked[name] = value
    return masked


class TrudnikAdminSite(AdminSite):
    site_header = "Трудник — админка (Django)"
    site_title = "Трудник"
    index_title = "Управление платформой"
    index_template = "admin/trudnik_index.html"

    def get_urls(self):
        from django.urls import path

        # ВАЖНО: до super().get_urls() — штатный список заканчивается catch-all
        urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="dashboard"),
            path("env/", self.admin_view(self.env_view), name="env"),
            path("analytics/", self.admin_view(self.analytics_view), name="analytics"),
        ] + super().get_urls()
        return urls

    def analytics_view(self, request):
        from core.views_analytics import render_dashboard
        return render_dashboard(request, self)

    def env_view(self, request):
        """Инвентарь переменных окружения прод-процесса. ТОЛЬКО staff;
        секретные значения маскируются, значения не логируются и не кэшируются."""
        import os

        from django.shortcuts import render

        return render(request, "admin/env.html", {
            **self.each_context(request),
            "title": "Переменные окружения",
            "env": dict(sorted(mask_env(os.environ).items())),
        })

    def dashboard_view(self, request):
        from django.shortcuts import render
        from django.urls import reverse
        from django.utils import timezone

        from core.models import Application, Job, Profile, UserReport
        from core.rpc import call_rpc

        stats, job_stats = {}, {}
        errors = []
        try:
            stats = call_rpc("get_admin_dashboard_stats") or {}
        except Exception as exc:  # fail-open для просмотра: показываем ошибку
            errors.append("get_admin_dashboard_stats: %s" % exc)
        try:
            job_stats = call_rpc("get_job_stats") or {}
        except Exception as exc:
            errors.append("get_job_stats: %s" % exc)
        today = timezone.localdate()
        quick = {
            "Новые пользователи (сегодня)": Profile.objects.filter(created_at__date=today).count(),
            "Новые задания (сегодня)": Job.objects.filter(created_at__date=today).count(),
            "Отклики (сегодня)": Application.objects.filter(created_at__date=today).count(),
            "Жалобы в очереди": UserReport.objects.exclude(status="reviewed").count(),
            "Задания на модерации": Job.objects.filter(moderation_status="review").count(),
            "Верификация на проверке": Profile.objects.filter(verification_status="pending").count(),
        }
        links = [
            ("Профили", reverse("admin:core_profile_changelist")),
            ("Задания", reverse("admin:core_job_changelist")),
            ("Отклики", reverse("admin:core_application_changelist")),
            ("Жалобы", reverse("admin:core_userreport_changelist")),
            ("Навыки", reverse("admin:core_skill_changelist")),
            ("Страницы", reverse("admin:core_sitepage_changelist")),
            ("Аудит", reverse("admin:core_auditlog_changelist")),
            ("Аналитика", reverse("admin:analytics")),
        ]
        context = dict(
            self.each_context(request),
            title="Дашборд",
            stats=stats,
            job_stats=job_stats,
            errors=errors,
            quick=quick,
            links=links,
        )
        return render(request, "admin/dashboard.html", context)


site = TrudnikAdminSite(name="admin")

users.register(site)
jobs.register(site)
support.register(site)
dictionaries.register(site)
