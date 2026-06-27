FROM python:3.12-slim

WORKDIR /app

# ═══════════════════════════════════════════════════════════
# Amvera: направляем изменяемые runtime-файлы в /data
# (persistent volume) — это обязательное условие для
# "быстрых сборок" и сохранения кэша между перезагрузками
# ═══════════════════════════════════════════════════════════
ENV PIP_CACHE_DIR=/data/pip-cache
ENV PYTHONPYCACHEPREFIX=/data/pycache

# Установка системных зависимостей + Python-зависимостей + очистка
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    pip install -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Копирование кода приложения
COPY . .

# Предкомпиляция Python-байткода (устраняет нагрев при старте)
RUN python -m compileall -q /app

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data/pip-cache /data/pycache && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD uvicorn asgi:application --host 0.0.0.0 --port 8000 --workers 1
