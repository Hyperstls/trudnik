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
    """ASGI middleware: WebSocket → FastAPI, HTTP → Flask, Lifespan → handled here, /health → FastAPI."""
    
    def __init__(self, ws_app, flask_asgi):
        self.ws_app = ws_app
        self.flask_asgi = flask_asgi
    
    async def _handle_lifespan(self, receive, send):
        """Handle ASGI lifespan protocol to suppress uvicorn warning."""
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                # FastAPI lifespan is called separately if needed for Redis
                await send({'type': 'lifespan.startup.complete'})
            elif event['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        if scope["type"] == "websocket" or scope.get("path", "").startswith("/ws"):
            import logging
            logging.getLogger(__name__).warning(f"[ASGI_ROUTER] type={scope.get('type')} path={scope.get('path')}")
        if scope["type"] in ("websocket",):
            # WebSocket goes to FastAPI
            await self.ws_app(scope, receive, send)
        else:
            # HTTP goes to Flask
            await self.flask_asgi(scope, receive, send)


application = RouterMiddleware(ws_app, flask_asgi)
