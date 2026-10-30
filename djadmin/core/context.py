"""Контекст-процессоры публичных шаблонов djadmin."""
from .models import Notification


def notifications_unread(request):
    """Бейдж непрочитанных в навигации (только для аутентифицированных)."""
    if request.user.is_authenticated:
        return {"unread_count": Notification.objects.filter(
            user=request.user, is_read=False).count()}
    return {"unread_count": 0}
