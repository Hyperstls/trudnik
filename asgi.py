"""
Unified ASGI entry point for Amvera.
Routes /ws WebSocket to FastAPI, everything else to Flask via WSGIMiddleware.
"""
from a2wsgi import WSGIMiddleware
from app import create_app
from websocket_server.main import app as ws_app

flask_app = create_app()
flask_asgi = WSGIMiddleware(flask_app, workers=15)


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

# ВРЕМЕННО (восстановление msk1): DNS-проба + env-инвентаризация — удалить после.
import socket as _socket
import logging as _logging
import os as _os
_dnslog = _logging.getLogger('dns-probe')
for _k in sorted(_os.environ):
    if any(w in _k.upper() for w in ('AMVERA','REDIS','POSTGREST','PGRST','CNPG','SERVICE','HOST')):
        _dnslog.warning('ENV %s=%s', _k, _os.environ.get(_k,'')[:60] if 'PASS' not in _k.upper() and 'SECRET' not in _k.upper() and 'TOKEN' not in _k.upper() else '<masked>')
for _h in ('run-trudnik-redis', 'run-trudnik-pr', 'cnpg-trudnik-db-rw',
           'run-trudnik-redis.tenant-ru-hyperstls', 'run-trudnik-pr.tenant-ru-hyperstls', 'cnpg-trudnik-db-rw.tenant-ru-hyperstls'):
    try:
        _socket.getaddrinfo(_h, None)
        _dnslog.warning('DNS OK: %s', _h)
    except Exception:
        _dnslog.warning('DNS FAIL: %s', _h)
