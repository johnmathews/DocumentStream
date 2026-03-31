#!/usr/bin/env bash
# Reset DocumentStream demo data — clears all processed documents.
#
# This wipes:
#   - PostgreSQL documents table (truncate, keep schema)
#   - Redis streams and status hashes (flushdb)
#   - Gateway in-memory document store (restart pods)
#
# Usage:
#   ./infra/reset-demo.sh

set -euo pipefail

NAMESPACE="documentstream"

echo "==> Clearing PostgreSQL documents table..."
kubectl exec -n "$NAMESPACE" deployment/postgres -- \
    psql -U documentstream -d documentstream -c "TRUNCATE TABLE documents;"

echo "==> Deleting Redis streams..."
kubectl exec -n "$NAMESPACE" redis-master-0 -- \
    redis-cli DEL raw-docs extracted classified

echo "==> Deleting Redis doc status hashes..."
kubectl exec -n "$NAMESPACE" redis-master-0 -- \
    sh -c 'redis-cli KEYS "doc:*" | xargs -r redis-cli DEL'

echo "==> Restarting gateway (clears in-memory document store)..."
kubectl rollout restart deployment/gateway -n "$NAMESPACE"
kubectl rollout status deployment/gateway -n "$NAMESPACE" --timeout=60s

echo ""
echo "==> Demo reset complete. All data cleared."
echo "    - PostgreSQL: documents table truncated"
echo "    - Redis: all streams and hashes flushed"
echo "    - Gateway: restarted with empty in-memory store"
