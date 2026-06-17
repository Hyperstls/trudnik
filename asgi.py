"""
Единая точка входа ASGI для Render (Unified Uvicorn).
Uvicorn обслуживает FastAPI (WebSocket + /health),
Flask монтируется через WSGIMiddleware на корень для всех HTTP-запросов.

Запуск:
    uvicorn asgi:application --host 0.0.0.0 --port $PORT --workers 2 --timeout-keep-alive 120
"""

from fastapi.middleware.wsgi import WSGIMiddleware
from app import app as flask_app
from websocket_server.main import app as ws_app

# Монтируем Flask на корень FastAPI.
# WSGI-приложение обрабатывает все HTTP-запросы,
# WebSocket /ws обслуживается напрямую FastAPI (WSGI не поддерживает WebSocket).
ws_app.mount("/", WSGIMiddleware(flask_app))

# Точка входа для uvicorn
application = ws_app
