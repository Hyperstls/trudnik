"""URLconf Django-компаньона: публичные read-only страницы + админка + health."""
from django.contrib import admin as django_admin  # noqa: F401 — чтобы auth/admin загрузились
from django.urls import include, path

from core import admin as core_admin
from core import views

urlpatterns = [
    path("admin/", core_admin.site.urls),
    path("", include("core.urls")),
]

# /health и /ready — наружу (healthcheck контейнера/платформы), без статики.
urlpatterns += [
    path("health", views.health, name="health"),
    path("ready", views.health, name="ready"),
]
