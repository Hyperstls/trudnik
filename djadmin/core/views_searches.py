"""Сохранённые поиски: страница, сохранение, уведомления, удаление (R050).

Вынесено из views.py (P2 кодревью №10). Логика и URL не менялись.
"""
import uuid
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .http import safe_next
from .models import Profile, Skill
from .ratelimit import rate_limit_write


def _saved_searches(user):
    prefs = user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    result = []
    for item in items[:10]:
        if not isinstance(item, dict) or not item.get("id") or not item.get("query"):
            continue
        result.append({
            "id": item["id"],
            "name": item.get("name") or _("Мой поиск"),
            "url": reverse("core:jobs") + "?" + item["query"],
            "notify": item.get("notify", True) is not False,
        })
    return result


def _saved_search_data(post):
    skills = []
    for raw in post.getlist("skills"):
        try:
            skills.append(str(UUID(str(raw).strip())))
        except (TypeError, ValueError):
            continue
    skills = list(dict.fromkeys(skills))[:20]
    params = []
    for key in ("q", "city", "status", "payment_min", "payment_max", "filter"):
        value = (post.get(key) or "").strip()[:120]
        if value:
            params.append((key, value))
    for skill in skills:
        params.append(("skills", skill))
    query = urlencode(params)
    city = (post.get("city") or "").strip()
    q = (post.get("q") or "").strip()
    name = city or q or (_("Все задания") if not query else _("Мой поиск"))
    return {"query": query, "name": name[:80]}


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def save_search(request):
    data = _saved_search_data(request.POST)
    if not data["query"]:
        messages.info(request, _("Сначала выберите хотя бы один фильтр."))
        return redirect("core:jobs")
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    items = [item for item in items if isinstance(item, dict)]
    if any(item.get("query") == data["query"] for item in items):
        messages.info(request, _("Такой поиск уже сохранён."))
        return redirect(reverse("core:jobs") + (("?" + data["query"]) if data["query"] else ""))
    items.insert(0, {
        "id": uuid.uuid4().hex, "name": data["name"], "query": data["query"],
        "notify": True,
    })
    prefs["saved_searches"] = items[:10]
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    messages.success(request, _("Поиск сохранён."))
    return redirect(reverse("core:jobs") + (("?" + data["query"]) if data["query"] else ""))


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def toggle_search(request, search_id):
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    found = False
    updated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("id") == search_id:
            item = dict(item)
            item["notify"] = item.get("notify", True) is False
            found = True
        updated.append(item)
    if found:
        prefs["saved_searches"] = updated[:10]
        Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
        messages.info(request, _("Настройка уведомлений поиска обновлена."))
    return redirect(safe_next(request, reverse("core:jobs")))


@login_required
def my_searches(request):
    """Страница сохранённых поисков: открыть, включить/выключить уведомления, удалить."""
    prefs = request.user.notification_prefs or {}
    raw_items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    skill_ids = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        for value in parse_qs(str(item.get("query") or "")).get("skills", []):
            try:
                skill_ids.append(UUID(str(value)))
            except (TypeError, ValueError):
                continue
    skill_names = {
        str(skill.pk): skill.name
        for skill in Skill.objects.filter(pk__in=list(dict.fromkeys(skill_ids)))
    }
    searches = []
    for item in raw_items[:10]:
        if not isinstance(item, dict) or not item.get("id") or not item.get("query"):
            continue
        params = parse_qs(str(item["query"]))
        summary = []
        q_value = (params.get("q") or [""])[0].strip()
        city_value = (params.get("city") or [""])[0].strip()
        status_value = (params.get("status") or [""])[0]
        payment_min = (params.get("payment_min") or [""])[0].strip()
        payment_max = (params.get("payment_max") or [""])[0].strip()
        job_filter = (params.get("filter") or [""])[0]
        if q_value:
            summary.append({"label": _("Запрос"), "value": q_value})
        if city_value:
            summary.append({"label": _("Город"), "value": city_value})
        if status_value == "open":
            summary.append({"label": _("Статус"), "value": _("Открытые")})
        elif status_value == "completed":
            summary.append({"label": _("Статус"), "value": _("Завершённые")})
        if payment_min:
            summary.append({"label": _("Оплата от"), "value": "%s ₽" % payment_min})
        if payment_max:
            summary.append({"label": _("Оплата до"), "value": "%s ₽" % payment_max})
        skills = [
            skill_names.get(str(value), str(value))
            for value in params.get("skills", []) if value
        ]
        if skills:
            summary.append({"label": _("Навыки"), "value": ", ".join(skills)})
        if job_filter == "new":
            summary.append({"label": _("Тип"), "value": _("Новые")})
        elif job_filter == "applied":
            summary.append({"label": _("Тип"), "value": _("Откликнулся")})
        searches.append({
            "id": item["id"],
            "name": item.get("name") or _("Мой поиск"),
            "url": reverse("core:jobs") + "?" + str(item["query"]),
            "query": item["query"],
            "notify": item.get("notify", True) is not False,
            "summary": summary,
        })
    return render(request, "core/my_searches.html", {"searches": searches})


@login_required
@require_POST
@rate_limit_write(limit=20, window=60, redirect_to="/jobs")
def delete_search(request, search_id):
    prefs = request.user.notification_prefs or {}
    items = prefs.get("saved_searches") if isinstance(prefs.get("saved_searches"), list) else []
    prefs["saved_searches"] = [
        item for item in items
        if isinstance(item, dict) and item.get("id") != search_id
    ][:10]
    Profile.objects.filter(pk=request.user.pk).update(notification_prefs=prefs)
    messages.info(request, _("Сохранённый поиск удалён."))
    return redirect(safe_next(request, reverse("core:jobs")))
