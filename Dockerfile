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
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && \
    pip install -r requirements.txt && \
    apt-get purge -y gcc libpq-dev && \
    apt-get autoremove -y && \
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

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD python scripts/apply_migrations.py && uvicorn asgi:application --host 0.0.0.0 --port 8000 --workers 1
