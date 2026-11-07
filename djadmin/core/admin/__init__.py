"""Регистрация админки «Трудник»: собственный AdminSite с дашбордом.

Модули: users (профили/верификация/навыки), jobs (задания/отклики/платежи),
support (жалобы/уведомления/логи/аудит), dictionaries (справочники/контент).
"""
from django.contrib.admin import AdminSite

from . import dictionaries, error_events, jobs, support, users

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


def _is_secret_name(name):
    """Имя переменной секретное: значение на /admin/env/ показывается только
    поштучно superuser'ом через POST-раскрытие."""
    upper = name.upper()
    return any(marker in upper for marker in SECRET_ENV_MARKERS)


def mask_env(environ):
    """Имена переменных + факт наличия; секретные значения заменяются маской."""
    masked = {}
    for name, value in environ.items():
        if _is_secret_name(name):
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
            path("2fa/", self.admin_view(self.twofa_view), name="admin_2fa"),
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
        секретные значения маскируются, значения не логируются и не кэшируются.
        Superuser может поштучно раскрыть секрет POST-формой (аудит — env_reveal,
        только имя, без значения)."""
        import os

        from django.core.exceptions import PermissionDenied
        from django.shortcuts import render

        from core.audit import log_admin_action

        environ = os.environ
        secret_names = {name for name in environ if _is_secret_name(name)}
        revealed = None
        if request.method == "POST":
            if not request.user.is_superuser:
                raise PermissionDenied
            reveal = request.POST.get("reveal")
            if reveal and reveal in environ and _is_secret_name(reveal):
                revealed = {"name": reveal, "value": environ[reveal]}
                log_admin_action(
                    request, "env_reveal", "env", None,
                    new_data={"name": reveal},
                )
        response = render(request, "admin/env.html", {
            **self.each_context(request),
            "title": "Переменные окружения",
            "env": dict(sorted(mask_env(environ).items())),
            "secret_names": secret_names,
            "revealed": revealed,
        })
        response["Cache-Control"] = "no-store, max-age=0"
        response["Pragma"] = "no-cache"
        return response

    def twofa_view(self, request):
        """Экран второго шага входа staff (R030): код из письма на email.

        Выключенный флаг и не-staff уходят на индекс админки; уже проверенная
        сессия форму не показывает. next принимается только внутри /admin/.
        """
        from django.conf import settings
        from django.contrib import messages
        from django.core.cache import cache
        from django.shortcuts import redirect, render
        from django.urls import reverse
        from django.utils.http import url_has_allowed_host_and_scheme

        from core.admin_2fa import issue_code, is_verified, mark_verified, verify_code

        index_url = reverse("admin:index")
        if not getattr(settings, "ADMIN_2FA_REQUIRED", False) or not request.user.is_staff:
            return redirect(index_url)

        next_raw = request.POST.get("next") or request.GET.get("next") or index_url
        next_url = index_url
        if next_raw.startswith("/admin/") and url_has_allowed_host_and_scheme(
            next_raw,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = next_raw

        if is_verified(request):
            return redirect(next_url)

        if request.method == "POST":
            if verify_code(request.user, request.POST.get("code", "")):
                mark_verified(request)
                return redirect(next_url)
            messages.error(request, "Неверный или истёкший код. Запросите новый код.")
        elif cache.add("admin_2fa_sent:%s" % request.user.pk, 1, 60):
            issue_code(request.user)
            messages.success(request, "Код отправлен на email")

        return render(request, "admin/2fa.html", {
            **self.each_context(request),
            "title": "Двухфакторная аутентификация",
            "email": request.user.email,
            "next": next_url,
            "code_ttl_minutes": 10,
        })

    def dashboard_view(self, request):
        from datetime import timedelta

        from django.db.models import Avg, F
        from django.shortcuts import render
        from django.urls import reverse
        from django.utils import timezone

        from core.models import (
            Application, ErrorEvent, Job, Profile, Rating, RatingReport, UserReport,
        )
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
        now = timezone.now()
        publish_delay = Rating.objects.filter(
            published_at__isnull=False,
            published_at__gte=now - timedelta(days=30),
        ).aggregate(delay=Avg(F("published_at") - F("created_at")))["delay"]
        quick = {
            "Новые пользователи (сегодня)": Profile.objects.filter(created_at__date=today).count(),
            "Новые задания (сегодня)": Job.objects.filter(created_at__date=today).count(),
            "Отклики (сегодня)": Application.objects.filter(created_at__date=today).count(),
            "Жалобы в очереди": UserReport.objects.exclude(status="reviewed").count(),
            "Задания на модерации": Job.objects.filter(moderation_status="review").count(),
            "Отзывы на модерации": Rating.objects.filter(moderation_status="review").count(),
            "Отзывы ждут публикации": Rating.objects.filter(
                moderation_status=Rating.ModerationStatus.OK, published_at__isnull=True,
            ).count(),
            "Отзывы скрыты модерацией": Rating.objects.filter(
                moderation_status=Rating.ModerationStatus.HIDDEN,
            ).count(),
            "Средняя задержка публикации (ч)": (
                "%.1f" % (publish_delay.total_seconds() / 3600)
                if publish_delay is not None else "—"
            ),
            "Жалобы на отзывы": RatingReport.objects.filter(status="new").count(),
            "Верификация на проверке": Profile.objects.filter(verification_status="pending").count(),
            "События ошибок (24 ч)": ErrorEvent.objects.filter(
                created_at__gte=now - timedelta(hours=24),
            ).count(),
        }
        links = [
            ("Профили", reverse("admin:core_profile_changelist")),
            ("Задания", reverse("admin:core_job_changelist")),
            ("Отклики", reverse("admin:core_application_changelist")),
            ("Жалобы", reverse("admin:core_userreport_changelist")),
            ("Отзывы", reverse("admin:core_rating_changelist")),
            ("Жалобы на отзывы", reverse("admin:core_ratingreport_changelist")),
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
error_events.register(site)
