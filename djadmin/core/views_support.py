"""Public support page: email fallback + contact form (J144)."""
import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from .forms_support import SupportForm
from .ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def support(request):
    form = SupportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            enforce_ip_limit(request, "support", 5, 3600)
        except RateLimitExceeded:
            messages.error(request, _("Слишком много обращений. Попробуйте позже или напишите на email."))
            return redirect("core:support")
        except RateLimitUnavailable:
            pass

        data = form.cleaned_data
        topic_label = dict(form.fields["topic"].choices).get(data["topic"], data["topic"])
        body = (
            "Обращение с сайта «Трудник»\n\n"
            "Имя: %s\nEmail: %s\nТема: %s\n\n%s"
            % (data.get("name") or "—", data["email"], topic_label, data["message"])
        )
        try:
            EmailMessage(
                "Трудник: обращение — %s" % topic_label,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                reply_to=[data["email"]],
            ).send(fail_silently=False)
        except Exception as exc:
            from .privacy import mask_text

            # без exc_info: трейсбек SMTP-исключения содержит адреса (R078)
            logger.warning(
                "support email failed (%s): %s",
                type(exc).__name__, mask_text(str(exc))[:300],
            )
            messages.error(
                request,
                _("Не удалось отправить сообщение. Напишите на %s.") % settings.SUPPORT_EMAIL,
            )
        else:
            messages.success(request, _("Сообщение отправлено. Ответим на указанный email."))
            return redirect("core:support")
    return render(request, "core/support.html", {
        "form": form, "support_email": settings.SUPPORT_EMAIL,
    })
