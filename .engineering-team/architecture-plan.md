# DocumentStream — Transaction Document Scanner & K8s Demo Platform

## Architecture & Implementation Plan

**Project:** Portfolio demo for RaboBank Data Engineer interview
**Timeline:** 3 days (2026-03-28 to 2026-03-31)
**Demo:** 5-10 minute live walkthrough with dashboards + printed architecture diagrams

---

## 1. Concept: "DocumentStream"

A Kubernetes-native document processing pipeline that ingests, extracts, classifies, and stores
financial documents from **commercial real estate loan lifecycles** by sensitivity level.

### Scenario

A commercial real estate developer applies for a loan to renovate an office building. The loan
lifecycle generates a chain of related documents — from application through due diligence to
contracting and construction. Each document in the chain shares the same loan ID, client, and
property, just as they would in a real bank.

For the stress test: "It's quarter-end. 200 loans are under simultaneous review." The generator
creates full document chains for N loans and floods the pipeline.

### Document Types (5 templates)

| Document | Classification | Text Volume | Semantic Search? |
|---|---|---|---|
| **Loan application** | Confidential | Low (structured fields) | No |
| **Property valuation report** | Confidential | High (500+ words — location, condition, risks) | **Yes** |
| **KYC / Due diligence report** | Secret | High (300+ words — client background, risk factors) | **Yes** |
| **Loan agreement (contract)** | Secret | High (1000+ words — clauses, terms, conditions) | **Yes** |
| **Contractor invoice** | Public | Low (structured line items) | No |

### Classification Levels

| Level | Meaning |
|---|---|
| **Public** | No restrictions. Contractor invoices, general correspondence |
| **Confidential** | Internal use. Loan applications, property valuations |
| **Secret** | Restricted access. KYC reports, loan agreements, client financial data |

*Note: Top Secret (fraud investigations, SARs, board M&A docs) would use the same classification
logic with stricter access controls. Not generated for this demo.*

### Vector Search

The three text-heavy document types (valuation reports, KYC reports, contracts) are embedded
using sentence-transformers and stored in PostgreSQL with pgvector. This enables semantic
queries like "find loans with environmental contamination risk" matching a valuation report
that mentions "soil quality concerns from prior industrial use."

The system demonstrates production K8s patterns: autoscaling, self-healing, rolling updates,
chaos engineering, queue-based pipelines, and full observability.

---

## 2. Architecture Overview

```
                        ┌─────────────────────────────────────────────────────┐
                        │                    AKS Cluster                      │
                        │                                                     │
  ┌──────────┐          │  ┌──────────┐    ┌─────────┐    ┌──────────────┐   │
  │  Locust   │─────────│─▶│ Ingress  │───▶│ FastAPI  │───▶│ Redis Queue  │   │
  │ Load Gen  │         │  │ (nginx)  │    │ Gateway  │    │ (raw-docs)   │   │
  └──────────┘          │  └──────────┘    └─────────┘    └──────┬───────┘   │
                        │                                        │           │
  ┌──────────┐          │                                        ▼           │
  │  Web UI   │─────────│─▶  (same ingress)           ┌──────────────────┐   │
  │ (control) │         │                              │ Extract Workers  │   │
  └──────────┘          │                              │ (PyMuPDF, KEDA) │   │
                        │                              └────────┬─────────┘   │
  ┌──────────┐          │                                       │            │
  │  Chaos   │          │                              ┌────────▼─────────┐  │
  │  Mesh    │──────────│─▶  (CRDs in cluster)         │ Classify Workers │  │
  │ Dashboard│          │                              │ (rules+ML, KEDA) │  │
  └──────────┘          │                              └────────┬─────────┘  │
                        │                                       │            │
  ┌──────────┐          │                              ┌────────▼─────────┐  │
  │ Grafana  │◀─────────│── Prometheus ◀── metrics     │  Store Workers   │  │
  │Dashboard │          │                              │  (KEDA)          │  │
  └──────────┘          │                              └────────┬─────────┘  │
                        │                                       │            │
                        └───────────────────────────────────────┼────────────┘
                                                                │
                                          ┌─────────────────────┼──────────────┐
                                          │     Azure Services   │              │
                                          │                      ▼              │
                                          │  ┌────────────┐  ┌────────────┐    │
                                          │  │ Blob Store │  │ PostgreSQL │    │
                                          │  │ (PDFs)     │  │ Flex Server│    │
                                          │  └────────────┘  └────────────┘    │
                                          └─────────────────────────────────────┘
```

### Pipeline Flow

```
Upload PDF ──▶ Redis:raw-docs ──▶ Extract (PyMuPDF) ──▶ Redis:extracted
                                                              │
              Redis:classified ◀── Classify (rules+ML) ◀─────┘
                    │
                    ▼
              Store ──▶ PostgreSQL (metadata + classification)
                   ──▶ Blob Storage (original PDF)
```

Each pipeline stage is a separate K8s Deployment, independently scaled by KEDA based on
Redis queue depth. This is the key architectural feature — it visually demonstrates how
K8s handles varying workloads.

---

## 3. Technology Stack

### Application Layer

| Component | Technology | Purpose |
|---|---|---|
| API Gateway | **FastAPI** | REST API for document upload, status, results |
| Web UI | **FastAPI + Jinja2 templates** | Control panel for traffic/demos (simple, no JS framework) |
| Document Generator | **fpdf2 + Faker (nl_NL)** | Generate synthetic financial docs at scale |
| Text Extraction | **PyMuPDF (fitz)** | Extract text from PDFs (~10-50ms/page) |
| Classification | **Rule-based + scikit-learn** | Keyword scoring + TF-IDF classifier |
| Queue | **Redis** | Pipeline message broker (Redis Streams) |

### Azure Services

| Service | Tier | Cost/hour | Purpose |
|---|---|---|---|
| **AKS** | Free control plane, 3x B2ms nodes | ~€0.25/hr | Container orchestration |
| **ACR** | Basic | ~€0.007/hr | Container image registry |
| **PostgreSQL Flexible** | Burstable B1ms | ~€0.017/hr | Document metadata + classifications |
| **Blob Storage** | Hot, LRS | ~€0.00/hr | PDF file storage |
| **Azure Monitor** | Prometheus metrics | ~€0.00/hr | Cluster metrics |
| **Managed Grafana** | Essential (free) | €0.00/hr | Dashboards |

**Total running cost: ~€0.28/hour** (well under €10/hr target)

**Cost when stopped:** ~€0.01/hr (disk storage only). Use `az aks stop` + `az postgres flexible-server stop`.

### K8s Infrastructure (Helm charts)

| Component | Chart | Purpose |
|---|---|---|
| **kube-prometheus-stack** | prometheus-community | Monitoring + Grafana |
| **Redis** | bitnami/redis | Message queue |
| **KEDA** | kedacore/keda | Queue-depth autoscaling |
| **Chaos Mesh** | chaos-mesh/chaos-mesh | Chaos engineering with web UI |
| **NGINX Ingress** | ingress-nginx | HTTP routing + TLS |

### CI/CD

| Component | Technology |
|---|---|
| Source control | **GitHub** (ghcr.io/johnmathews/k8s) |
| CI/CD | **GitHub Actions** |
| Image registry | **Azure Container Registry** |
| Deployment | **GitHub Actions → kubectl apply to AKS** |

---

## 4. Demo Script (8 minutes)

This is what the live demo looks like. Every architectural decision below serves this flow.

### Minute 0-1: "Here's the system"
- Show the running web UI: document upload form, classification results table
- Show the Grafana dashboard: all green, 3 pods per stage, low traffic
- "This is a document processing pipeline running on AKS with 4 stages"

### Minute 1-3: "Watch it scale"
- Open Locust web UI, set to 50 users, start generating traffic
- Switch to Grafana: watch request rate climb, queue depths increase
- Watch KEDA scale extract/classify/store workers from 1 → 5+ pods
- "KEDA monitors Redis queue depth. When documents pile up, it adds workers automatically"

### Minute 3-5: "Watch it heal"
- Open Chaos Mesh dashboard, create a PodChaos experiment: kill 2 classify workers
- Switch to Grafana: watch pods die and instantly restart
- Show brief latency spike, then recovery
- "Kubernetes detected the failed pods and restarted them in seconds. No documents were lost — they stayed in the queue"

### Minute 5-7: "Watch it handle a bad deployment"
- Deploy a "buggy" version (returns 500 errors) using `kubectl set image`
- Show rolling update: old pods still serving while new pods start failing readiness probes
- K8s stops the rollout automatically (maxUnavailable protects the system)
- Run `kubectl rollout undo` — instant rollback
- "The readiness probe caught the bug. K8s stopped the rollout before it affected users. One command to rollback"

### Minute 7-8: "The CI/CD pipeline"
- Show the GitHub Actions workflow (on screen or paper)
- Show the architecture diagram (paper printout)
- "Every push to main builds the images, pushes to ACR, and deploys to AKS"
- Show cost: "This entire cluster costs €0.28/hour. When I'm not demoing, I stop it for near-zero cost"

---

## 5. Project Structure

```
k8s/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Lint + test on PR
│       └── deploy.yml                # Build → ACR → AKS on push to main
├── src/
│   ├── gateway/                      # FastAPI API + Web UI
│   │   ├── app.py                    # Main FastAPI application
│   │   ├── templates/                # Jinja2 HTML templates
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── worker/                       # Pipeline workers (shared base)
│   │   ├── extract.py                # Text extraction stage
│   │   ├── classify.py               # Classification stage
│   │   ├── store.py                  # Storage stage
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── generator/                    # Document generator (CLI tool)
│       ├── generate.py               # PDF generation with templates
│       ├── templates/                # Loan app, valuation, KYC, contract, invoice
│       ├── Dockerfile
│       └── pyproject.toml
├── k8s/                              # Kubernetes manifests
│   ├── base/                         # Base manifests (Kustomize)
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── gateway-deployment.yaml
│   │   ├── gateway-service.yaml
│   │   ├── extract-deployment.yaml
│   │   ├── classify-deployment.yaml
│   │   ├── store-deployment.yaml
│   │   ├── ingress.yaml
│   │   └── configmap.yaml
│   ├── scaling/                      # KEDA ScaledObjects
│   │   ├── extract-scaledobject.yaml
│   │   ├── classify-scaledobject.yaml
│   │   └── store-scaledobject.yaml
│   └── chaos/                        # Chaos Mesh experiments
│       ├── pod-kill.yaml
│       ├── network-delay.yaml
│       └── cpu-stress.yaml
├── infra/                            # Azure infrastructure setup
│   ├── setup.sh                      # az CLI commands to create all Azure resources
│   ├── teardown.sh                   # az CLI commands to destroy everything
│   └── helm-install.sh               # Install all Helm charts
├── locust/                           # Load testing
│   ├── locustfile.py                 # Load test scenarios
│   └── Dockerfile
├── grafana/                          # Custom Grafana dashboards
│   └── documentstream-dashboard.json       # Pre-configured dashboard
├── tests/                            # All tests
│   ├── test_generator.py
│   ├── test_extract.py
│   ├── test_classify.py
│   ├── test_store.py
│   ├── test_gateway.py
│   └── conftest.py
├── docs/                             # Documentation
│   ├── architecture.md               # System architecture
│   ├── setup.md                      # How to set up from scratch
│   ├── demo-guide.md                 # Step-by-step demo script
│   ├── cost-analysis.md              # Azure cost breakdown
│   └── k8s-concepts.md              # K8s concepts demonstrated
├── journal/                          # Development journal
│   └── 260328-project-kickoff.md
├── docker-compose.yml                # Local development (all services)
├── Makefile                          # Common commands
├── pyproject.toml                    # Root project config (ruff, shared settings)
├── CLAUDE.md                         # Project-specific instructions
└── README.md
```

---

## 6. Three-Day Implementation Plan

### Day 1: Foundation (Saturday March 28)

**Morning — Azure & cluster setup (3-4 hours)**

| # | Task | Details |
|---|---|---|
| 1.1 | Azure account setup | Create subscription, install `az` CLI, authenticate |
| 1.2 | Create resource group | `az group create -n documentstream-rg -l westeurope` |
| 1.3 | Create ACR | `az acr create -n documentstreamacr -g documentstream-rg --sku Basic` |
| 1.4 | Create AKS cluster | 3x B2ms nodes, attach ACR, enable monitoring |
| 1.5 | Install Helm charts | kube-prometheus-stack, Redis, KEDA, Chaos Mesh, ingress-nginx |
| 1.6 | Verify cluster | `kubectl get nodes`, access Grafana, access Chaos Mesh dashboard |

**Afternoon — Application code (4-5 hours)**

| # | Task | Details |
|---|---|---|
| 1.7 | Init project | `git init`, pyproject.toml, ruff config, Makefile |
| 1.8 | Build document generator | 3 templates (receipt, invoice, contract), 4 classification levels, fpdf2 + Faker |
| 1.9 | Build text extractor | PyMuPDF wrapper, batch processing |
| 1.10 | Build classifier | Rule-based keyword scorer + scikit-learn TF-IDF backup |
| 1.11 | Write tests | Generator, extractor, classifier unit tests |
| 1.12 | Build gateway | FastAPI app with upload endpoint, health check, simple web UI |

**Evening — Containerize & first deploy (2-3 hours)**

| # | Task | Details |
|---|---|---|
| 1.13 | Write Dockerfiles | Multi-stage builds for gateway + worker + generator |
| 1.14 | docker-compose.yml | Local development stack (gateway + redis + postgres) |
| 1.15 | Build & push to ACR | `az acr build` for each image |
| 1.16 | Write K8s manifests | Deployments, Services, ConfigMap for gateway + workers |
| 1.17 | First K8s deploy | `kubectl apply`, verify pods running, test endpoint |

**Day 1 exit criteria:** Application runs locally via docker-compose AND on AKS. Can upload a PDF and see it classified.

---

### Day 2: Pipeline & Chaos (Sunday March 29)

**Morning — Pipeline integration (4-5 hours)**

| # | Task | Details |
|---|---|---|
| 2.1 | Implement Redis queue | Workers consume from Redis Streams, acknowledge on completion |
| 2.2 | Wire pipeline stages | Gateway → Redis:raw-docs → Extract → Redis:extracted → Classify → Redis:classified → Store |
| 2.3 | Azure Blob Storage | Upload original PDFs to blob storage, store URL in PostgreSQL |
| 2.4 | Azure PostgreSQL | Create Flexible Server (B1ms), connect from store worker |
| 2.5 | KEDA ScaledObjects | Configure queue-depth scaling for each worker deployment |
| 2.6 | Test pipeline E2E | Generate 100 docs, watch them flow through all stages |

**Afternoon — Observability & chaos (4-5 hours)**

| # | Task | Details |
|---|---|---|
| 2.7 | Custom Grafana dashboard | 6-8 panels: pod count, CPU, memory, request rate, queue depth, error rate |
| 2.8 | Prometheus metrics | Add custom metrics to FastAPI (request latency, docs processed, queue depth) |
| 2.9 | Chaos experiments | Create YAML for: pod-kill, network-delay, cpu-stress |
| 2.10 | Test self-healing | Kill pods, verify restart and zero data loss |
| 2.11 | Test HPA/KEDA scaling | Generate burst traffic, verify workers scale up/down |
| 2.12 | Rolling update test | Deploy v2, observe rollout, test rollback |

**Day 2 exit criteria:** Full pipeline working on AKS with autoscaling. Grafana dashboard shows all key metrics. Chaos experiments work and system self-heals.

---

### Day 3: Polish & Demo Prep (Monday March 30)

**Morning — CI/CD & load testing (3-4 hours)**

| # | Task | Details |
|---|---|---|
| 3.1 | GitHub Actions CI | Lint + test on PR (ruff, pytest) |
| 3.2 | GitHub Actions deploy | Build → push to ACR → deploy to AKS on push to main |
| 3.3 | GHCR workflow | Build and push images to ghcr.io/johnmathews/k8s |
| 3.4 | Locust load testing | Write scenarios (document upload, burst traffic, mixed workload) |
| 3.5 | Deploy Locust to cluster | Or run locally targeting AKS endpoint |
| 3.6 | End-to-end demo run | Full demo script with timing |

**Afternoon — Documentation & materials (3-4 hours)**

| # | Task | Details |
|---|---|---|
| 3.7 | Architecture diagram | Clean diagram for printout (using draw.io or similar) |
| 3.8 | Documentation | architecture.md, setup.md, demo-guide.md, cost-analysis.md, k8s-concepts.md |
| 3.9 | Demo script | Exact commands, timing, talking points |
| 3.10 | Printable materials | Architecture diagram, K8s manifest highlights, cost breakdown |
| 3.11 | Practice demo | Run through 2-3 times, adjust timing |
| 3.12 | Create stop/start scripts | `infra/setup.sh` and `infra/teardown.sh` for cost management |

**Day 3 exit criteria:** Full demo rehearsed. All documentation complete. CI/CD pipeline working. Printable materials ready.

---

## 7. K8s Concepts Demonstrated

This project demonstrates the following Kubernetes concepts, mapped to interview talking points:

| K8s Concept | How It's Demonstrated | Interview Talking Point |
|---|---|---|
| **Pods & Deployments** | Each pipeline stage is a Deployment | "Smallest deployable unit, declarative desired state" |
| **Services** | ClusterIP for internal, LoadBalancer for gateway | "Service discovery and stable networking" |
| **Horizontal Pod Autoscaler** | KEDA scales workers on queue depth | "Automatic scaling based on real demand, not just CPU" |
| **Self-healing** | Chaos Mesh kills pods, K8s restarts them | "Desired state reconciliation — K8s always converges" |
| **Rolling updates** | Zero-downtime deploys, automatic rollback | "Progressive delivery with safety nets" |
| **Liveness/readiness probes** | Health checks on all pods | "K8s only routes to healthy pods" |
| **Resource limits** | CPU/memory limits on all containers | "Prevent noisy neighbors, enable bin-packing" |
| **ConfigMaps & Secrets** | DB credentials, Redis URLs, feature flags | "Separate config from code, 12-factor app" |
| **Namespaces** | `documentstream`, `monitoring`, `chaos-mesh`, `keda` | "Logical isolation, RBAC boundaries" |
| **Ingress** | NGINX ingress with path-based routing | "L7 routing, TLS termination, single entry point" |
| **Persistent Volumes** | Redis and PostgreSQL data persistence | "Stateful workloads in K8s" |
| **RBAC** | Service accounts per component | "Principle of least privilege" |
| **Kustomize** | Base manifests with overlays | "Environment-specific config without duplication" |

---

## 8. Risk Mitigations

| Risk | Mitigation | Fallback |
|---|---|---|
| AKS setup takes too long | Use `az aks create` with minimal flags, not Terraform | Use Minikube locally for Day 1 dev |
| Azure account setup issues | Start this FIRST on Day 1 morning | Free trial gives $200 credit |
| KEDA doesn't work with Redis | Test KEDA + Redis integration early on Day 2 | Fall back to HPA with CPU-based scaling |
| Chaos Mesh dashboard issues | Pre-create YAML experiments | `kubectl apply -f chaos/pod-kill.yaml` works without dashboard |
| Pipeline too complex | Start with 2 stages (ingest → process), expand to 4 | Even 2 stages shows the pattern |
| Running out of time on Day 3 | Documentation is higher priority than polish | A working demo with good docs beats a polished demo with no docs |

---

## 9. Azure Setup Commands (Quick Reference)

```bash
# Variables
RG=documentstream-rg
LOCATION=westeurope
CLUSTER=documentstream-aks
ACR=documentstreamacr
PG_SERVER=documentstream-pg
STORAGE=documentstreamstorage

# Resource Group
az group create -n $RG -l $LOCATION

# Container Registry
az acr create -n $ACR -g $RG --sku Basic

# AKS Cluster (Free tier, 3x B2ms)
az aks create \
  -n $CLUSTER -g $RG \
  --node-count 3 \
  --node-vm-size Standard_B2ms \
  --attach-acr $ACR \
  --enable-managed-identity \
  --generate-ssh-keys \
  --tier free

# Get credentials
az aks get-credentials -n $CLUSTER -g $RG

# PostgreSQL Flexible Server
az postgres flexible-server create \
  -n $PG_SERVER -g $RG \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --admin-user documentstream \
  --admin-password '<generate-secure-password>'

# Blob Storage
az storage account create \
  -n $STORAGE -g $RG \
  --sku Standard_LRS \
  --kind StorageV2

# Stop everything when not demoing
az aks stop -n $CLUSTER -g $RG
az postgres flexible-server stop -n $PG_SERVER -g $RG

# Start for demo
az aks start -n $CLUSTER -g $RG
az postgres flexible-server start -n $PG_SERVER -g $RG
```

---

## 10. What Makes This Impressive for a Data Engineer Interview

1. **Production-grade architecture** — Not a toy. Queue-based pipeline, autoscaling workers,
   observability, chaos testing. This is how real data platforms work.

2. **Azure-native** — Uses AKS, ACR, PostgreSQL Flexible, Blob Storage, Managed Grafana.
   Shows you can build on the platform RaboBank actually uses.

3. **Data engineering fundamentals** — Unstructured data ingestion, text extraction, classification,
   storage. The pipeline pattern (ingest → extract → transform → load) is core data engineering.

4. **Operational maturity** — CI/CD, monitoring, chaos engineering, cost management. Shows you
   think about the full lifecycle, not just writing code.

5. **Document classification for banking** — Uses realistic Dutch banking classification levels
   (Openbaar → Vertrouwelijk → Geheim → Zeer Geheim). Shows domain awareness.

6. **Live demo capability** — Not slides. Real traffic, real scaling, real failures, real recovery.
   The interviewer can see it working, not just hear about it.
