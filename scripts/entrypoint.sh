#!/bin/bash
set -e

echo "============================================"
echo "  Trudnik Entrypoint — Starting Deploy"
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

echo ""
echo "Applying database migrations..."
python scripts/apply_migrations.py

echo ""
echo "Starting application..."
exec "$@"
