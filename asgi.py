"""
Unified ASGI entry point for Amvera.
Routes /ws WebSocket to FastAPI, everything else to Flask via WSGIMiddleware.
"""
from a2wsgi import WSGIMiddleware
from app import create_app
from websocket_server.main import app as ws_app

flask_app = create_app()
flask_asgi = WSGIMiddleware(flask_app, workers=50)


class RouterMiddleware:
    """ASGI middleware: WebSocket → FastAPI, HTTP → Flask."""

    def __init__(self, ws_app, flask_asgi):
        self.ws_app = ws_app
        self.flask_asgi = flask_asgi

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.ws_app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await self.ws_app(scope, receive, send)
        else:
            await self.flask_asgi(scope, receive, send)


application = RouterMiddleware(ws_app, flask_asgi)