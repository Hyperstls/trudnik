"""Регистрация админки «Трудник»: собственный AdminSite с дашбордом.

Модули: users (профили/верификация/навыки), jobs (задания/отклики/платежи),
support (жалобы/уведомления/логи/аудит), dictionaries (справочники/контент).
"""
from django.contrib.admin import AdminSite

from . import dictionaries, jobs, support, users


class TrudnikAdminSite(AdminSite):
    site_header = "Трудник — админка (Django)"
    site_title = "Трудник"
    index_title = "Управление платформой"

    def get_urls(self):
        from django.urls import path

        # ВАЖНО: до super().get_urls() — штатный список заканчивается catch-all
        urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="dashboard"),
            path("env/", self.admin_view(self.env_view), name="env"),
        ] + super().get_urls()
        return urls

    def env_view(self, request):
        """Инвентарь переменных окружения прод-процесса. ТОЛЬКО staff;
        значения НЕ логируются и не кэшируются — только рендер этого шаблона."""
        import os

        from django.shortcuts import render

        return render(request, "admin/env.html", {
            **self.each_context(request),
            "title": "Переменные окружения",
            "env": dict(sorted(os.environ.items())),
        })

    def dashboard_view(self, request):
        from django.shortcuts import render

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
        context = dict(
            self.each_context(request),
            title="Дашборд",
            stats=stats,
            job_stats=job_stats,
            errors=errors,
        )
        return render(request, "admin/dashboard.html", context)


site = TrudnikAdminSite(name="admin")

users.register(site)
jobs.register(site)
support.register(site)
dictionaries.register(site)
