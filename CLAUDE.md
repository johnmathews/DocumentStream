# DocumentStream — K8s Document Processing Pipeline

## Project Overview
Portfolio project for RaboBank Data Engineer interview demonstrating Kubernetes, CI/CD,
and data engineering on Azure. A document processing pipeline for commercial real estate
loan documents.

## Stack
- **Language:** Python 3.13
- **API:** FastAPI
- **PDF generation:** fpdf2 + Faker (nl_NL locale)
- **Text extraction:** PyMuPDF (fitz)
- **Rule-based classification:** Weighted keyword scoring (privacy level)
- **Semantic classification:** sentence-transformers + anchor embeddings (environmental impact, industries)
- **Testing:** pytest + coverage
- **Linting:** ruff
- **Deps:** uv
- **CI:** GitHub Actions (lint + test on push to main)

### Implemented (Day 2)
- **Queue:** Redis Streams (pipeline message broker)
- **Database:** PostgreSQL with pgvector (metadata + embeddings)

### Implemented (Day 3)
- **Autoscaling:** KEDA ScaledObjects (queue-depth based, YAMLs in k8s/scaling/)
- **Monitoring:** Prometheus + Grafana dashboard (grafana/documentstream-dashboard.json)
- **Chaos engineering:** Chaos Mesh experiments (k8s/chaos/)
- **Load testing:** Locust (locust/locustfile.py)
- **CI/CD:** GitHub Actions deploy workflow (.github/workflows/deploy.yml)

### Implemented (Day 4)
- **Blob storage:** Azure Blob Storage (PDFs uploaded on generate, tracked in PostgreSQL)
- **Custom metrics:** Prometheus counters for blob uploads (count + bytes by doc_type)
- **Dashboard:** 9 Grafana panels (added blob count/size by doc type)
- **ServiceMonitor:** Prometheus scrape config for kube-prometheus-stack

### Not yet done
- Apply Chaos Mesh experiments on live cluster
- CI/CD deploy workflow needs AZURE_CREDENTIALS secret
- Demo rehearsal

## Project Structure
- `src/gateway/` — FastAPI API + web UI (dual-mode: sync or async via Redis)
- `src/worker/` — Extract, classify, semantic, store modules + Redis queue + worker runners
- `src/generator/` — PDF document generator (5 templates, CLI tool)
- `demo_samples/` — One complete loan scenario (5 PDFs, committed to git for visibility)
- `tests/` — All tests (92 tests)
- `k8s/base/` — Kubernetes base manifests (10 files: namespace, configmap, deployments, service, ingress, kustomization, servicemonitor)
- `k8s/scaling/` — KEDA ScaledObjects for extract, classify, store workers
- `k8s/chaos/` — Chaos Mesh experiments (pod-kill, network-delay, cpu-stress)
- `infra/` — Azure setup/teardown/helm-install scripts
- `locust/` — Locust load test (locustfile.py)
- `grafana/` — Grafana dashboard JSON (9 panels)
- `docs/` — Documentation (architecture, classification, demo guide, dictionary, implementation plan)
- `journal/` — Development journal

## Commands
- `make test` — Run tests with pytest
- `make lint` — Run ruff linter
- `make generate` — Generate 10 scenarios (50 PDFs) in `generated_docs/` (gitignored)
- `make demo-samples` — Regenerate `demo_samples/` with one fresh loan scenario (committed to git)
- `make dev` — Start local dev environment (docker-compose)

## Key Patterns
- All documents in a loan scenario share the same loan_id, client, and property data
- 5 document types: loan_application, valuation_report, kyc_report, contract, invoice
- Two classifiers run on every document:
  - Rule-based: privacy level (Public/Confidential/Secret) via keyword scoring
  - Semantic: environmental impact (None/Low/Medium/High) + industry sectors via embeddings
- Document embeddings stored for later pgvector semantic search
- Anchor texts are descriptive paragraphs, not keyword lists
- Gateway is dual-mode: sync (no REDIS_URL) or async (REDIS_URL set)
- Workers use Redis consumer groups for at-least-once delivery
- SIGTERM graceful shutdown on all workers (finish current message before exiting)

### Architecture
- Each pipeline stage is a separate K8s Deployment scaled by KEDA
- Documents flow through Redis Streams: raw-docs → extracted → classified → stored
- Store worker persists to PostgreSQL (pgvector) + Azure Blob Storage
- CI/CD: ci.yml (lint+test), docker.yml (ghcr.io push), deploy.yml (ACR build + AKS deploy)
