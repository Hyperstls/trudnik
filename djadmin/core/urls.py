from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("jobs", views.jobs_list, name="jobs"),
    path("jobs/<uuid:job_id>", views.job_detail, name="job_detail"),
    path("workers", views.workers_list, name="workers"),
    path("workers/<uuid:user_id>", views.worker_detail, name="worker_detail"),
    path("terms", views.legal_page, {"slug": "terms"}, name="terms"),
    path("privacy", views.legal_page, {"slug": "privacy"}, name="privacy"),
    path("safety", views.legal_page, {"slug": "safety"}, name="safety"),
    path("robots.txt", views.robots, name="robots"),
]
