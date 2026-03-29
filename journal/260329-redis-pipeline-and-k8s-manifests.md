# Day 2: Redis Streams Pipeline & K8s Manifests

**Date:** 2026-03-29

## What was done

### Stage 0: Tool Setup
- Installed Helm 4.1.3 via Homebrew
- kubectl 1.34.1 already present (includes Kustomize 5.7.1)

### Stage 1: Azure Infrastructure (partial)
- Created resource group `DocumentStream` in westeurope
- Created ACR `acrdocumentstream` (Basic SKU)
- Created AKS `DocumentStreamManagedCluster` (2x Standard_B2s_v2, Free tier, K8s 1.33.7)
  - Hit 4 vCPU quota limit — used B2s_v2 instead of B2ms, 2 nodes instead of 3
  - Standard_B2s (old gen) not available in westeurope, needed v2 suffix
- PostgreSQL Flexible Server and Storage Account not yet provisioned

### Stage 2: Redis Streams Pipeline Refactor
Built the async document processing pipeline:

**New modules:**
- `src/worker/queue.py` — Redis Streams utilities (publish, consume, ack, status tracking,
  base64 PDF encoding, graceful shutdown via SIGTERM)
- `src/worker/extract_runner.py` — Reads from `raw-docs`, extracts text, publishes to `extracted`
- `src/worker/classify_runner.py` — Reads from `extracted`, runs rule-based + semantic classifiers,
  publishes to `classified`
- `src/worker/store.py` — PostgreSQL insert with pgvector embedding storage
- `src/worker/store_runner.py` — Reads from `classified`, persists to PostgreSQL + optional Blob Storage
- `src/worker/schema.sql` — Database schema with pgvector extension and HNSW index
- `src/worker/Dockerfile` — Single worker image, CMD overridden per deployment

**Gateway dual-mode:**
- Modified `src/gateway/app.py` to detect `REDIS_URL` environment variable
- Sync mode (no REDIS_URL): existing behavior, all original tests pass unchanged
- Async mode (REDIS_URL set): publishes to Redis, returns `status: queued`,
  client polls for progress through pipeline stages

**Tests:** 32 new tests (83 total, 88% coverage)
- `tests/test_queue.py` — 15 tests for encode/decode, consumer groups, publish, consume, ack, status
- `tests/test_runners.py` — 3 tests for extract, classify, store runner process_message functions
- `tests/test_gateway_async.py` — 7 tests for async mode upload, status polling, health check
- `tests/test_store.py` — 5 tests for store_document, DocumentRecord, upload_blob

### Stage 3: K8s Manifests
Created 8 manifests in `k8s/base/`:
- Namespace, ConfigMap, Gateway Deployment + Service, 3 worker Deployments, Ingress
- All validated with `kubectl apply --dry-run=client`
- Resource limits tuned for 2-node B2s_v2 cluster (4 vCPU, 16GB total)
- Classify worker gets more memory (384-512Mi) for sentence-transformers model
- 30s terminationGracePeriodSeconds on all workers for graceful shutdown

### Infrastructure Scripts
- `infra/setup.sh` — Full Azure provisioning script
- `infra/teardown.sh` — Stop/start/destroy for cost management
- `infra/helm-install.sh` — Installs Redis, ingress-nginx, KEDA, Prometheus+Grafana, Chaos Mesh

### CI/CD
- Updated `docker.yml` workflow to build both gateway and worker images using a matrix strategy

### Documentation
- Created `docs/pipeline.md` — Redis Streams pipeline documentation
- Updated `docs/architecture.md` — dual-mode pipeline flow, queue module docs
- Updated `docs/implementation-plan.md` — progress dashboard (Stages 0-3 done)
- Updated `CLAUDE.md` — project structure and patterns

## Key decisions
- **Dual-mode gateway** preserves all 51 original tests without modification
- **Single worker Docker image** with CMD override per deployment — simpler than 3 separate images
- **Base64 encoding for PDFs** in Redis — Redis Streams only support string values
- **ON CONFLICT DO NOTHING** for idempotent storage — safe for at-least-once delivery
- **2 nodes instead of 3** due to Azure vCPU quota (4 cores limit)

## Azure quota issue
The subscription has a 4 vCPU limit in westeurope. The original plan called for
3x Standard_B2ms nodes. We used 2x Standard_B2s_v2 (2 vCPU each = 4 total).
This is sufficient for the demo — 2 nodes still shows pod distribution. Could
request a quota increase later if needed.

## Next steps
- Stage 4: Build and push images to ACR, install Helm charts, deploy to AKS
- Stage 5: KEDA autoscaling ScaledObjects
- Remaining Azure infra: PostgreSQL Flexible Server, Storage Account
