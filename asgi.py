"""
Unified ASGI entry point for Amvera.
Routes /ws WebSocket to FastAPI, everything else to Flask via WSGIMiddleware.
"""
from a2wsgi import WSGIMiddleware
from app import app as flask_app
from websocket_server.main import app as ws_app

# Wrap Flask as ASGI
flask_asgi = WSGIMiddleware(flask_app)


class RouterMiddleware:
    """ASGI middleware: WebSocket → FastAPI, HTTP → Flask, Lifespan → FastAPI, /health → FastAPI."""
    
    def __init__(self, ws_app, flask_asgi):
        self.ws_app = ws_app
        self.flask_asgi = flask_asgi
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket" or scope["path"].startswith("/ws"):
            import logging
            logging.getLogger(__name__).warning(f"[ASGI_ROUTER] type={scope.get('type')} path={scope.get('path')}")
        if scope["type"] in ("websocket", "lifespan"):
            # WebSocket and lifespan go to FastAPI (needs lifespan for Redis)
            await self.ws_app(scope, receive, send)
        elif scope["type"] == "http" and scope.get("path") == "/health":
            # Health check goes to FastAPI (Amvera platform health-check)
            await self.ws_app(scope, receive, send)
        else:
            # HTTP goes to Flask
            await self.flask_asgi(scope, receive, send)


application = RouterMiddleware(ws_app, flask_asgi)
