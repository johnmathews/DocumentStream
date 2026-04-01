# DocumentStream — Implementation Plan

**Timeline:** 3 days (2026-03-28 to 2026-03-30) + Day 4 enhancements
**Interview:** After Day 3
**Last updated:** 2026-04-01

---

## Progress Dashboard

| Stage | What | Priority | Est. | Status |
|---|---|---|---|---|
| -- | **Day 1: Foundation** | -- | -- | **DONE** |
| 0 | Tool setup (helm, kustomize) | MUST | 15min | DONE |
| 1 | Azure infrastructure | MUST | 1.5-2h | DONE (AKS + ACR + Helm charts running) |
| 2 | Redis Streams pipeline refactor | MUST | 2.5-3h | DONE |
| 3 | K8s manifests | MUST | 2-2.5h | DONE |
| 4 | Build, push, deploy to AKS | MUST | 1-1.5h | DONE (pipeline running at 51.138.91.82) |
| 5 | KEDA autoscaling | MUST | 1-1.5h | DONE (applied, verified scaling 1→8→1) |
| 6 | Grafana dashboard | HIGH | 1.5-2h | DONE (9 panels, including blob storage metrics) |
| 7 | Chaos Mesh experiments | MEDIUM | 1h | PARTIAL (YAMLs written, Chaos Mesh installed, needs apply) |
| 8 | Locust load testing | MEDIUM | 1h | DONE (ran against AKS, verified KEDA scaling) |
| 9 | CI/CD deploy workflow | MEDIUM | 1h | PARTIAL (workflow written, needs AZURE_CREDENTIALS secret) |
| 10 | Rolling update demo prep | LOW | 30min | TODO (live demo technique) |
| 11 | Polish and demo rehearsal | MUST | 1.5-2h | TODO |
| -- | **Day 4: Enhancements** | -- | -- | **DONE** |
| 12 | Azure Blob Storage integration | HIGH | 2h | DONE (PDFs stored in Azure, metrics in Grafana) |

**If time runs short:** Cut from the bottom. Stages 0-5 + 11 are non-negotiable. Stage 6 (Grafana) is
the most important "nice to have" because it's the visual centerpiece of the demo. Stages 7-10 can
be done live during the interview with `kubectl apply` if needed.

---

## Day 1: Foundation (March 28) -- DONE

Everything below is built and working.

| Component | Files | Status |
|---|---|---|
| FastAPI gateway (synchronous) | `src/gateway/app.py`, `src/gateway/templates/index.html` | DONE |
| PDF generator (5 templates) | `src/generator/scenario.py`, `templates.py`, `generate.py` | DONE |
| Text extractor | `src/worker/extract.py` | DONE |
| Rule-based classifier | `src/worker/classify.py` | DONE |
| Semantic classifier | `src/worker/semantic.py` | DONE |
| Tests (51 passing, 94% coverage) | `tests/test_*.py`, `tests/conftest.py` | DONE |
| Gateway Dockerfile | `src/gateway/Dockerfile` | DONE |
| Docker Compose (gateway + redis + postgres) | `docker-compose.yml` | DONE |
| CI workflow (lint + test) | `.github/workflows/ci.yml` | DONE |
| Docker build+push to ghcr.io | `.github/workflows/docker.yml` | DONE |
| Documentation | `docs/architecture.md`, `classification.md`, `demo-guide.md`, `dictionary.md` | DONE |
| Demo samples (1 loan, 5 PDFs) | `demo_samples/CRE-729976/` | DONE |
| README | `README.md` | DONE |

**Current architecture:** PDF upload -> FastAPI -> `extract_text()` -> `classify_text()` + `classify_semantic()` -> return results. All synchronous, all in-memory. Redis and PostgreSQL containers exist in docker-compose but the gateway doesn't connect to them yet.

---

## Stage 0: Tool Setup (15 min)

| # | Task | Exit Criteria | Done |
|---|---|---|---|
| 0.1 | `brew install helm kustomize` | `helm version` and `kustomize version` succeed | [ ] |

---

## Stage 1: Azure Infrastructure (1.5-2h)

Start this first -- AKS provisioning takes 5-10 minutes. Write Stage 2 code while it provisions.

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 1.1 | Write Azure setup script | `infra/setup.sh` | Creates resource group, ACR (Basic), AKS (3x Standard_B2ms, Free tier), PostgreSQL Flexible (Burstable B1ms, pg16), Storage Account (Standard_LRS) + blob container | [ ] |
| 1.2 | Write teardown script | `infra/teardown.sh` | `az group delete` for full teardown. Separate `stop()` and `start()` functions for cost management | [ ] |
| 1.3 | Write Helm install script | `infra/helm-install.sh` | Installs 5 charts: ingress-nginx, kube-prometheus-stack, bitnami/redis, kedacore/keda, chaos-mesh. Each in its own namespace | [ ] |
| 1.4 | Run setup.sh | -- | `kubectl get nodes` shows 3 Ready nodes | [ ] |
| 1.5 | Run helm-install.sh | -- | All Helm releases show `deployed` status | [ ] |

**Dependencies:** None. This is the first thing to start.

---

## Stage 2: Redis Streams Pipeline Refactor (2.5-3h)

This is the highest-risk stage. The gateway currently calls worker functions directly
(`src/gateway/app.py` lines 107-113). This must become: gateway publishes to Redis,
workers consume and process independently.

### Stream Design

```
raw-docs       {doc_id, filename, pdf_b64}              -> extract-group
extracted      {doc_id, filename, text, page_count,     -> classify-group
                word_count, pdf_b64}
classified     {doc_id, filename, text, pdf_b64,        -> store-group
                classification, confidence,
                semantic_privacy, environmental_impact,
                industries, embedding}
```

Redis hash `doc:{doc_id}` tracks status for gateway polling (queued -> extracting -> classifying -> completed).

### Tasks

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 2.1 | Redis Streams utility module | `src/worker/queue.py` | `publish()`, `consume()`, `ack()`, `set_doc_status()`, `get_doc_status()`. Consumer group auto-creation with MKSTREAM. Configurable via env vars (`REDIS_URL`, stream names). PDF bytes base64-encoded. | [ ] |
| 2.2 | Refactor gateway to dual-mode | `src/gateway/app.py` | If `REDIS_URL` is set: upload publishes to `raw-docs`, returns `status: queued`, list/get read from Redis hash. If not set: existing synchronous behavior unchanged. | [ ] |
| 2.3 | Extract worker runner | `src/worker/extract_runner.py` | Infinite loop: XREADGROUP from `raw-docs`, call `extract_text()`, publish to `extracted`, XACK. SIGTERM graceful shutdown. | [ ] |
| 2.4 | Classify worker runner | `src/worker/classify_runner.py` | XREADGROUP from `extracted`, call `classify_text()` + `classify_semantic()`, publish to `classified`, XACK. | [ ] |
| 2.5 | Store worker | `src/worker/store.py` | PostgreSQL insertion: metadata + classification + vector(384) via pgvector. Optional Azure Blob upload for original PDF. | [ ] |
| 2.6 | Store worker runner | `src/worker/store_runner.py` | XREADGROUP from `classified`, call store logic, update status to `completed`, XACK. | [ ] |
| 2.7 | Database schema | `src/worker/schema.sql` | `CREATE EXTENSION IF NOT EXISTS vector; CREATE TABLE documents(...)` with pgvector column. | [ ] |
| 2.8 | Worker Dockerfile | `src/worker/Dockerfile` | Single image (python:3.13-slim + uv), CMD overridden per K8s deployment. | [ ] |
| 2.9 | Update docker-compose for local pipeline test | `docker-compose.yml` | Add extract-worker, classify-worker, store-worker services. `docker compose up` -> upload PDF -> document lands in PostgreSQL. | [ ] |
| 2.10 | Tests for queue module | `tests/test_queue.py` | Test publish/consume/ack with mocked Redis. | [ ] |
| 2.11 | Verify existing tests still pass | -- | All 51 tests pass (sync fallback preserved). | [ ] |

**Dependencies:** None for code (2.1-2.8, 2.10-2.11). Task 2.9 needs docker-compose running. Stage 1 is NOT required -- local testing uses docker-compose.

**Key design decision:** Dual-mode gateway preserves all existing tests. No test refactoring needed.

---

## Stage 3: K8s Manifests (2-2.5h)

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 3.1 | Namespace | `k8s/base/namespace.yaml` | Namespace `documentstream` | [ ] |
| 3.2 | ConfigMap | `k8s/base/configmap.yaml` | `REDIS_URL`, `DATABASE_URL`, stream names | [ ] |
| 3.3 | Gateway Deployment + Service | `k8s/base/gateway-deployment.yaml`, `k8s/base/gateway-service.yaml` | 2 replicas, 128Mi-256Mi mem, 100m-250m CPU, liveness+readiness on `/health`, ClusterIP port 8000 | [ ] |
| 3.4 | Extract worker Deployment | `k8s/base/extract-deployment.yaml` | 1 replica, command: `python -m worker.extract_runner` | [ ] |
| 3.5 | Classify worker Deployment | `k8s/base/classify-deployment.yaml` | 1 replica, 512Mi mem (sentence-transformers model ~80MB, process ~300-400MB total) | [ ] |
| 3.6 | Store worker Deployment | `k8s/base/store-deployment.yaml` | 1 replica, env includes database secret | [ ] |
| 3.7 | Ingress | `k8s/base/ingress.yaml` | NGINX ingress routing to gateway service | [ ] |
| 3.8 | Kustomization | `k8s/base/kustomization.yaml` | Lists all resources, common labels | [ ] |

**Manifest patterns to demonstrate:**
- Resource requests AND limits on every container
- `terminationGracePeriodSeconds: 30` on workers (finish in-flight messages before SIGTERM)
- `imagePullPolicy: Always`
- `app` label on all pods (used by KEDA selector and Chaos Mesh targeting)

**Dependencies:** Stage 2 code must be written (manifests reference worker runner commands and env vars).

---

## Stage 4: Build, Push, Deploy (1-1.5h)

| # | Task | Exit Criteria | Done |
|---|---|---|---|
| 4.1 | Build images to ACR | `az acr build -r documentstreamacr -t gateway:latest` and `-t worker:latest` | Images visible in ACR | [ ] |
| 4.2 | Create K8s secrets | `kubectl create secret` for PostgreSQL password and Blob connection string | Secret exists in cluster | [ ] |
| 4.3 | Initialize PostgreSQL schema | Run `schema.sql` against Azure PostgreSQL | `documents` table exists with vector extension | [ ] |
| 4.4 | Apply manifests | `kubectl apply -k k8s/base/` | All pods Running, gateway `/health` returns 200 via port-forward | [ ] |
| 4.5 | End-to-end test on AKS | Upload PDF via `/api/documents` or hit `/api/generate` | Document flows through all stages, lands in PostgreSQL | [ ] |

**Dependencies:** Stages 1 (Azure running), 2 (code ready), 3 (manifests ready).

---

## Stage 5: KEDA Autoscaling (1-1.5h)

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 5.1 | Extract ScaledObject | `k8s/scaling/extract-scaledobject.yaml` | Redis Streams scaler, `pollingInterval: 15`, `cooldownPeriod: 60`, min 1 / max 8, `lagCount: "5"` | [ ] |
| 5.2 | Classify ScaledObject | `k8s/scaling/classify-scaledobject.yaml` | Same pattern as 5.1 | [ ] |
| 5.3 | Store ScaledObject | `k8s/scaling/store-scaledobject.yaml` | Same pattern as 5.1 | [ ] |
| 5.4 | Verify scaling | -- | Generate 50+ docs. `kubectl get pods -w` shows workers scaling 1 -> 3+. After queue drains (60s), back to 1. | [ ] |

**Dependencies:** Stage 4 (pipeline running on AKS).

**Day 2 gate: Pipeline running on AKS with KEDA scaling visible.**

---

## Stage 6: Grafana Dashboard (1.5-2h)

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 6.1 | Build dashboard from existing metrics | `grafana/documentstream-dashboard.json` | 6-8 panels using metrics already collected (no custom app instrumentation needed) | [ ] |
| 6.2 | Import dashboard into Grafana | -- | Dashboard visible in Grafana UI, all panels populated | [ ] |

**Dashboard panels (all from existing Prometheus metrics):**

| Panel | Metric Source |
|---|---|
| Pod count per deployment | `kube_deployment_status_replicas` (kube-state-metrics) |
| CPU usage per pod | `container_cpu_usage_seconds_total` (cAdvisor) |
| Memory usage per pod | `container_memory_working_set_bytes` (cAdvisor) |
| Redis stream lengths | Redis exporter (bitnami/redis chart) |
| Pod restarts (self-healing) | `kube_pod_container_status_restarts_total` |
| KEDA scaling decisions | `keda_metrics_adapter_scaler_metrics_value` |

**Stretch:** Add `prometheus-client` to gateway for custom metrics (request rate, latency histogram). Optional -- the dashboard above is sufficient for a compelling demo.

**Dependencies:** Stage 4 (cluster running with metrics flowing).

---

## Stage 7: Chaos Mesh Experiments (1h)

| # | Task | Files | Demo Value | Done |
|---|---|---|---|---|
| 7.1 | Pod kill experiment | `k8s/chaos/pod-kill.yaml` | Kill 2 classify-worker pods. K8s restarts in seconds. Redis re-delivers unacked messages. Zero data loss. | [ ] |
| 7.2 | Network delay experiment | `k8s/chaos/network-delay.yaml` | 500ms latency on store-worker. Pipeline slows but doesn't break. Grafana shows latency spike. | [ ] |
| 7.3 | CPU stress experiment | `k8s/chaos/cpu-stress.yaml` | 80% CPU burn on classify-worker. KEDA scales up additional pods to compensate. | [ ] |

**Dependencies:** Stage 5 (KEDA must be active to show compensating scale-up for 7.3).

---

## Stage 8: Locust Load Testing (1h)

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 8.1 | Write load test scenarios | `locust/locustfile.py` | Two tasks: (1) upload pre-generated PDF, (2) hit `/api/generate?count=1`. Ramp 1 to 50 users. | [ ] |
| 8.2 | Run against AKS | -- | Locust UI shows request rate climbing. KEDA scaling visible in `kubectl get pods -w`. | [ ] |

**Fallback:** A bash `for` loop with `curl` is sufficient for the demo if Locust proves problematic.

**Dependencies:** Stage 4 (pipeline running on AKS).

---

## Stage 9: CI/CD Deploy Workflow (1h)

| # | Task | Files | Exit Criteria | Done |
|---|---|---|---|---|
| 9.1 | Write deploy workflow | `.github/workflows/deploy.yml` | On push to main: `az acr build` for both images, `kubectl apply -k k8s/base/`. Requires `AZURE_CREDENTIALS` GitHub secret. | [ ] |

**Dependencies:** Stage 4 (AKS running, images in ACR).

---

## Stage 10: Rolling Update Demo (30 min)

| # | Task | Exit Criteria | Done |
|---|---|---|---|
| 10.1 | Prepare bad image tag | Use nonexistent tag like `worker:v999` to trigger `ImagePullBackOff`. Old pods keep serving (rolling update strategy). `kubectl rollout undo` restores health. | [ ] |

No new files. This is a live demo technique using existing manifests.

**Dependencies:** Stage 4 (pipeline running on AKS).

---

## Stage 11: Polish and Demo Rehearsal (1.5-2h)

| # | Task | Exit Criteria | Done |
|---|---|---|---|
| 11.1 | Update docs to reflect actual deployment | `docs/architecture.md`, `docs/demo-guide.md`, `README.md` reflect real AKS state | [ ] |
| 11.2 | Dry-run full 8-minute demo | Run every demo step against live cluster with timing | [ ] |
| 11.3 | Prepare printable materials | Architecture diagram, cost breakdown, K8s concepts list | [ ] |
| 11.4 | Stop cluster for cost management | `az aks stop` + `az postgres flexible-server stop`. Document restart commands. | [ ] |

**Dependencies:** All previous stages complete (or explicitly cut).

---

## Day-by-Day Schedule

### Day 2 (March 29) -- Target: ~9.5 hours

| Time | Stage | Hours |
|---|---|---|
| Morning start | Stage 0: Tool setup | 0.25 |
| +15min | Stage 1: Azure infra (start AKS, write Stage 2 code while it provisions) | 1.75 |
| +2h | Stage 2: Redis Streams pipeline refactor | 2.5 |
| Break | -- | -- |
| Afternoon | Stage 3: K8s manifests | 2.0 |
| +2h | Stage 4: Build, push, deploy | 1.5 |
| +1.5h | Stage 5: KEDA autoscaling | 1.5 |

**Day 2 gate:** Pipeline running on AKS. KEDA scaling workers up and down under load.

### Day 3 (March 30) -- Target: ~7.5 hours

| Time | Stage | Hours |
|---|---|---|
| Morning start | Stage 6: Grafana dashboard | 2.0 |
| +2h | Stage 7: Chaos Mesh experiments | 1.0 |
| +1h | Stage 8: Locust load testing | 1.0 |
| Break | -- | -- |
| Afternoon | Stage 9: CI/CD deploy workflow | 1.0 |
| +1h | Stage 10: Rolling update demo | 0.5 |
| +30min | Stage 11: Polish + demo rehearsal | 2.0 |

**Day 3 gate:** Full demo rehearsed end-to-end against live cluster. All docs updated.

---

## Risk Mitigations

| Risk | Mitigation | Fallback |
|---|---|---|
| AKS provisioning slow | Start Stage 1 FIRST. Write Stage 2 code in parallel. | Use Minikube locally for Day 1-2 dev. |
| Redis Streams integration bugs | Test locally with `docker compose up` before touching AKS. Keep sync fallback. | Demo with synchronous mode if pipeline isn't ready. |
| KEDA Redis scaler misconfigured | Check `kubectl logs -n keda deployment/keda-operator`. Consumer group must exist first. | Fall back to HPA with CPU-based scaling. |
| sentence-transformers OOM | Set memory limit to 768Mi or 1Gi. Model is ~80MB, process ~300-400MB total. | Use rule-based only, skip semantic. |
| Helm chart conflicts | Pin chart versions in `helm-install.sh`. | Install components one at a time. |
| Running out of time | Stages 0-5 + 11 are MUST. Cut 6-10 from the bottom. | Even without Grafana, `kubectl get pods -w` shows scaling live. |

---

## New Files Summary (~28 files)

**Infrastructure (3):**
`infra/setup.sh`, `infra/teardown.sh`, `infra/helm-install.sh`

**Worker code (7):**
`src/worker/queue.py`, `src/worker/extract_runner.py`, `src/worker/classify_runner.py`,
`src/worker/store.py`, `src/worker/store_runner.py`, `src/worker/schema.sql`, `src/worker/Dockerfile`

**K8s base manifests (8):**
`k8s/base/namespace.yaml`, `k8s/base/configmap.yaml`, `k8s/base/gateway-deployment.yaml`,
`k8s/base/gateway-service.yaml`, `k8s/base/extract-deployment.yaml`,
`k8s/base/classify-deployment.yaml`, `k8s/base/store-deployment.yaml`,
`k8s/base/ingress.yaml`, `k8s/base/kustomization.yaml`

**K8s scaling (3):**
`k8s/scaling/extract-scaledobject.yaml`, `k8s/scaling/classify-scaledobject.yaml`,
`k8s/scaling/store-scaledobject.yaml`

**K8s chaos (3):**
`k8s/chaos/pod-kill.yaml`, `k8s/chaos/network-delay.yaml`, `k8s/chaos/cpu-stress.yaml`

**Observability (1):**
`grafana/documentstream-dashboard.json`

**Load testing (1):**
`locust/locustfile.py`

**CI/CD (1):**
`.github/workflows/deploy.yml`

**Tests (1):**
`tests/test_queue.py`
