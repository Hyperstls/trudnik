from django.urls import re_path

from .consumers import ChatConsumer
from .consumers_notify import NotificationConsumer

websocket_urlpatterns = [
    re_path(r"^ws/chat/(?P<app_id>[0-9a-f-]{36})/?$", ChatConsumer.as_asgi()),
    re_path(r"^ws/user/?$", NotificationConsumer.as_asgi()),
]
