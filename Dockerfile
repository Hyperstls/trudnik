FROM python:3.12-slim

WORKDIR /app

# ═══════════════════════════════════════════════════════════
# Git version for build identification
# ═══════════════════════════════════════════════════════════
ARG GIT_VERSION=dev
ENV GIT_VERSION=$GIT_VERSION

# ═══════════════════════════════════════════════════════════
# Amvera: направляем изменяемые runtime-файлы в /data
# (persistent volume) — это обязательное условие для
# "быстрых сборок" и сохранения кэша между перезагрузками
# ═══════════════════════════════════════════════════════════
ENV PIP_CACHE_DIR=/data/pip-cache
ENV PYTHONPYCACHEPREFIX=/data/pycache

# Установка системных зависимостей + Python-зависимостей + очистка
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 supervisor && \
    pip install -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Копирование кода приложения
COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Предкомпиляция Python-байткода (устраняет нагрев при старте)
RUN python -m compileall -q /app

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data/pip-cache /data/pycache && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
