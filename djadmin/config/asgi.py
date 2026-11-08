"""ASGI: HTTP (Django) + WebSocket (channels) в одном процессе (uvicorn).

Прод: uvicorn config.asgi:application --workers 2 (см. supervisord.djadmin.conf).
Сессии — DB-backed, поэтому AuthMiddlewareStack даёт request.user и в WS.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from core.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # R052: CSWSH — чужая страница не может открыть wss:// с куками жертвы;
    # Origin обязан совпадать с ALLOWED_HOSTS (в DEBUG — '*').
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
