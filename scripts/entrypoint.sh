#!/bin/bash
set -e

echo "============================================"
echo "  Trudnik Entrypoint — Starting Deploy"
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# Миграции отключены: применяются только вручную через
#   MIGRATIONS_ENABLED=true python scripts/apply_migrations.py
#
echo ""
echo "Starting application..."
exec "$@"
