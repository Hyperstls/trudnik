from django.urls import path

from . import views, views_flow

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("jobs", views.jobs_list, name="jobs"),
    path("jobs/new", views_flow.job_create, name="job_create"),
    path("jobs/<uuid:job_id>", views.job_detail, name="job_detail"),
    path("jobs/<uuid:job_id>/edit", views_flow.job_edit, name="job_edit"),
    path("jobs/<uuid:job_id>/apply", views_flow.job_apply, name="job_apply"),
    path("jobs/<uuid:job_id>/unapply", views_flow.job_unapply, name="job_unapply"),
    path("jobs/<uuid:job_id>/applicants", views_flow.job_applicants, name="job_applicants"),
    path("jobs/<uuid:job_id>/favorite", views_flow.job_favorite_toggle, name="job_favorite_toggle"),
    path("jobs/<uuid:job_id>/<str:action>", views_flow.job_action, name="job_action"),
    path("applications/<uuid:app_id>/<str:action>", views_flow.application_action, name="application_action"),
    path("workers", views.workers_list, name="workers"),
    path("workers/<uuid:user_id>", views.worker_detail, name="worker_detail"),
    path("my-jobs", views_flow.my_jobs, name="my_jobs"),
    path("my-applications", views_flow.my_applications, name="my_applications"),
    path("favorite-jobs", views_flow.favorite_jobs, name="favorite_jobs"),
    path("login", views_flow.login_view, name="login"),
    path("logout", views_flow.logout_view, name="logout"),
    path("terms", views.legal_page, {"slug": "terms"}, name="terms"),
    path("privacy", views.legal_page, {"slug": "privacy"}, name="privacy"),
    path("safety", views.legal_page, {"slug": "safety"}, name="safety"),
    path("robots.txt", views.robots, name="robots"),
]
