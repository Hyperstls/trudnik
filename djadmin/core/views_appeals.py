"""R024: страница «Мои отзывы» и подача апелляции на скрытый отзыв.

Автор видит все свои отзывы (включая скрытые модератором), статус
публикации и последнюю апелляцию. Для скрытого отзыва без pending-апелляции
доступна форма причины; создание — через core.appeals.create_appeal.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .appeals import can_appeal, create_appeal
from .models import Rating, RatingAppeal
from .ratelimit import rate_limit_write


@login_required
def my_ratings(request):
    ratings = list(
        Rating.objects.filter(rater_user=request.user)
        .select_related("rated_user", "job")
        .order_by("-created_at")[:100]
    )
    latest_appeals = {}
    if ratings:
        appeals = RatingAppeal.objects.filter(
            appellant=request.user,
            rating_id__in=[rating.pk for rating in ratings],
        ).order_by("-created_at")
        for appeal in appeals:
            latest_appeals.setdefault(appeal.rating_id, appeal)
    rows = [
        {
            "rating": rating,
            "latest_appeal": latest_appeals.get(rating.pk),
            "can_appeal": can_appeal(rating, request.user),
        }
        for rating in ratings
    ]
    return render(request, "core/my_ratings.html", {"rows": rows})


@login_required
@require_POST
@rate_limit_write(limit=5, window=600, redirect_to="/my-ratings")
def rating_appeal_create(request, rating_id):
    rating = Rating.objects.filter(pk=rating_id, rater_user=request.user).first()
    if rating is None:
        raise Http404("Отзыв не найден")
    appeal, error = create_appeal(rating_id, request.user, request.POST.get("reason", ""))
    if error:
        messages.error(request, error)
    else:
        messages.success(request, _("Апелляция отправлена на рассмотрение модератору."))
    return redirect("core:my_ratings")
