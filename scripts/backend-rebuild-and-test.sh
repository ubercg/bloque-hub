#!/usr/bin/env bash
# Reconstruye el backend, aplica migraciones y ejecuta tests pendientes (fulfillment montaje).
# Uso: desde la raíz del repo, ./scripts/backend-rebuild-and-test.sh

set -e
cd "$(dirname "$0")/.."

echo "=== 1. Reconstruir imagen backend ==="
docker compose build backend

echo "=== 2. Levantar backend ==="
docker compose up -d backend

echo "=== 3. Esperar que el backend esté listo ==="
sleep 5
for i in 1 2 3 4 5 6 7 8 9 10; do
  if docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" 2>/dev/null; then
    echo "Backend respondiendo."
    break
  fi
  echo "Intento $i/10..."
  sleep 3
done

echo "=== 4. Aplicar migraciones ==="
docker compose exec -T backend alembic upgrade head

echo "=== 5. Ejecutar tests de fulfillment montaje (TASK-063) ==="
docker compose exec -T backend pytest tests/test_fulfillment_montage.py -v --tb=short

echo "=== Listo ==="
