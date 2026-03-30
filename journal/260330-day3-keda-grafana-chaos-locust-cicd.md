# Day 3: KEDA, Grafana, Chaos Mesh, Locust, and CI/CD Deploy

**Date:** 2026-03-30

## What Was Done

Completed Stages 5-9 of the implementation plan. All files are written and ready to
apply once the AKS cluster is provisioned. No new Python application code — this was
entirely infrastructure/config work.

### Stage 5: KEDA ScaledObjects
- Created 3 ScaledObject manifests in `k8s/scaling/`
- Each targets a worker deployment and watches its corresponding Redis stream
- Config: pollingInterval 15s, cooldownPeriod 60s, min 1 / max 8 replicas, lagCount threshold 5
- Uses the `redis-streams` trigger type pointing at `redis-master.documentstream.svc.cluster.local:6379`

### Stage 6: Grafana Dashboard
- Created `grafana/documentstream-dashboard.json` with 7 panels
- Row 1: Pod count (bar gauge), Redis queue depth (stat), Pod restarts (stat)
- Row 2: CPU usage per pod (timeseries), Memory usage per pod (timeseries)
- Row 3: KEDA scaling metrics (timeseries), Network I/O (timeseries)
- 5-second auto-refresh for live demo, color thresholds on stat panels

### Stage 7: Chaos Mesh Experiments
- `k8s/chaos/pod-kill.yaml` — Kills 2 classify-worker pods (demonstrates self-healing)
- `k8s/chaos/network-delay.yaml` — 500ms latency on store-workers (demonstrates resilience)
- `k8s/chaos/cpu-stress.yaml` — 80% CPU burn on classify-workers (demonstrates KEDA scale-up)
- All include descriptive comments and usage commands

### Stage 8: Locust Load Test
- `locust/locustfile.py` with 4 weighted tasks
- Upload PDF (weight 3), generate scenario (weight 1), list docs (weight 5), health check (weight 2)
- PDF generated once at class level, reused per request
- Supports local, AKS, and headless (CI) modes

### Stage 9: CI/CD Deploy Workflow
- `.github/workflows/deploy.yml` — triggers on push to main when src/ or k8s/ files change
- Builds both gateway and worker images to ACR with SHA tags
- Applies K8s manifests and waits for rollout status
- Added `workflow_call` trigger to `ci.yml` so deploy.yml can reuse it as a gate

### Documentation Updates
- Updated CLAUDE.md to reflect all new files and current project state
- Updated architecture.md with deploy.yml reference
- Updated implementation-plan.md progress dashboard

### AKS Deployment (evening session)

Successfully deployed the full pipeline to AKS:

- Built Docker images locally (ARM64→AMD64 cross-compile) and pushed to ACR
- Installed 5 Helm charts: Redis, ingress-nginx, KEDA, Prometheus+Grafana, Chaos Mesh
- Deployed all 4 app services + PostgreSQL with pgvector
- Initialized database schema
- Pipeline confirmed working: `curl http://51.138.91.82/health` → `{"mode":"async"}`

**Fixes during deployment:**
- extract-worker memory limit bumped 128Mi → 256Mi (OOMKilled on AMD64)
- ConfigMap DATABASE_URL updated to match in-cluster Postgres service name
- Created `k8s/base/postgres-deployment.yaml` — Bitnami PostgreSQL chart was incompatible
  with the pgvector image, so we deployed PostgreSQL directly as a simple Deployment+Service

## What's Left

1. Apply KEDA ScaledObjects (`kubectl apply -f k8s/scaling/`)
2. Import Grafana dashboard
3. Apply Chaos Mesh experiments
4. Run Locust load test against live cluster
5. Demo rehearsal

## Test Status
- 83 tests passing, 88% coverage
- No new tests needed (all new files are YAML/JSON/config)
