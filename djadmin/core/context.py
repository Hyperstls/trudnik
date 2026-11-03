"""Контекст-процессоры публичных шаблонов djadmin."""
from django.db.models import Q

from .models import Message, Notification


def notifications_unread(request):
    """Бейджи непрочитанных уведомлений и сообщений в навигации."""
    if not request.user.is_authenticated:
        return {"unread_count": 0, "unread_chats_count": 0}
    return {
        "unread_count": Notification.objects.filter(
            user=request.user, is_read=False,
        ).count(),
        "unread_chats_count": Message.objects.filter(
            Q(application__worker=request.user) | Q(application__job__employer=request.user),
            application__status="accepted",
            read_at__isnull=True,
        ).exclude(sender=request.user).count(),
    }
