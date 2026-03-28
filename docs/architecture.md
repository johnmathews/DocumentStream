# DocumentStream — System Architecture

## Overview

DocumentStream is a Kubernetes-native document processing pipeline for commercial real estate
loan documents. It ingests PDFs, extracts text, classifies them across multiple
dimensions (privacy level, environmental impact, industry sectors), stores embeddings
for semantic search, and archives originals in blob storage.

The system is designed to demonstrate production K8s patterns: queue-based pipelines,
event-driven autoscaling, self-healing, rolling updates, chaos engineering, and
full observability.

---

## System Diagram

```
                        ┌────────────────────────────────────────────────────────┐
                        │                     AKS Cluster                        │
                        │                                                        │
  ┌──────────┐          │  ┌──────────┐    ┌──────────┐    ┌────────────────┐   │
  │  Locust   │─────────│─▶│ Ingress  │───▶│ FastAPI  │───▶│  Redis Stream  │   │
  │ Load Gen  │         │  │ (nginx)  │    │ Gateway  │    │  (raw-docs)    │   │
  └──────────┘          │  └──────────┘    └──────────┘    └───────┬────────┘   │
                        │                                          │            │
  ┌──────────┐          │                                          ▼            │
  │  Chaos   │          │                               ┌────────────────────┐  │
  │  Mesh    │──────────│─▶ (CRDs in cluster)           │  Extract Workers   │  │
  │ Dashboard│          │                               │  (PyMuPDF, KEDA)   │  │
  └──────────┘          │                               └─────────┬──────────┘  │
                        │                                         │             │
  ┌──────────┐          │                    Redis Stream          │             │
  │ Grafana  │◀─────────│── Prometheus ◀──   (extracted)  ◀───────┘             │
  │Dashboard │          │    metrics                │                           │
  └──────────┘          │                           ▼                           │
                        │                ┌────────────────────┐                 │
                        │                │  Classify Workers   │                 │
                        │                │  Rules + Semantic   │                 │
                        │                │  (KEDA-scaled)      │                 │
                        │                └─────────┬──────────┘                 │
                        │                          │                            │
                        │                 Redis Stream                          │
                        │                 (classified)                          │
                        │                          │                            │
                        │                          ▼                            │
                        │                ┌────────────────────┐                 │
                        │                │   Store Workers     │                 │
                        │                │   (KEDA-scaled)     │                 │
                        │                └─────────┬──────────┘                 │
                        │                          │                            │
                        └──────────────────────────┼────────────────────────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │  Azure Services             │
                                    │              │              │
                                    │     ┌────────▼────────┐     │
                                    │     │  PostgreSQL      │     │
                                    │     │  Flexible Server │     │
                                    │     │  + pgvector      │     │
                                    │     └─────────────────┘     │
                                    │                             │
                                    │     ┌─────────────────┐     │
                                    │     │  Blob Storage    │     │
                                    │     │  (original PDFs) │     │
                                    │     └─────────────────┘     │
                                    └─────────────────────────────┘
```

---

## Pipeline Flow

### Current (local dev — synchronous)

```
Upload PDF ──▶ Gateway (FastAPI)
                   │
                   ├── Extract (PyMuPDF)
                   ├── Rule-based classify
                   ├── Semantic classify
                   └── Return results (in-memory)
```

Currently all processing happens synchronously in the gateway process.
Results are stored in-memory (no persistence).

### Target (K8s — async, queue-based)

```
Upload PDF
    │
    ▼
Redis:raw-docs ──▶ Extract Workers (PyMuPDF)
                        │
                        ▼
               Redis:extracted ──▶ Classify Workers
                                       │
                                  ┌────┴────┐
                                  │         │
                             Rule-based  Semantic
                             (privacy)   (env impact,
                                          industries,
                                          privacy)
                                  │         │
                                  └────┬────┘
                                       │
                                       ▼
                              Redis:classified ──▶ Store Workers
                                                       │
                                                  ┌────┴────┐
                                                  │         │
                                           PostgreSQL   Blob Storage
                                           (metadata,   (original PDF)
                                            embeddings,
                                            classifications)
```

Each pipeline stage will be a separate K8s Deployment with its own KEDA ScaledObject.
KEDA monitors the Redis stream depth for each stage and scales workers independently.

---

## Component Details

### Gateway (`src/gateway/`)

| Aspect | Detail |
|---|---|
| Framework | FastAPI |
| Endpoints | `/health`, `/api/documents`, `/api/generate`, `/` (web UI) |
| K8s role | Single Deployment with a Service and Ingress |
| Scaling | HPA based on CPU (not queue-based — it handles HTTP, not queue work) |

### Extract Workers (`src/worker/extract.py`)

| Aspect | Detail |
|---|---|
| Library | PyMuPDF (fitz) |
| Input | Redis stream `raw-docs` (PDF bytes) |
| Output | Redis stream `extracted` (full text + metadata) |
| Performance | ~10-50ms per page |
| Scaling | KEDA ScaledObject watching `raw-docs` stream depth |

### Classify Workers (`src/worker/classify.py` + `semantic.py`)

| Aspect | Detail |
|---|---|
| Rule-based | Weighted keyword scoring → Privacy level (Public/Confidential/Secret) |
| Semantic | sentence-transformers embedding → Environmental impact, Industry sectors, Privacy |
| Input | Redis stream `extracted` |
| Output | Redis stream `classified` |
| Model | all-MiniLM-L6-v2 (384 dimensions, ~100ms per document) |
| Scaling | KEDA ScaledObject watching `extracted` stream depth |

### Store Workers (`src/worker/store.py`) — NOT YET IMPLEMENTED

| Aspect | Detail |
|---|---|
| Database | PostgreSQL with pgvector extension |
| Blob store | Azure Blob Storage |
| Input | Redis stream `classified` |
| Stored data | Document metadata, classification results, vector embedding (384 dims), blob URL |
| Scaling | KEDA ScaledObject watching `classified` stream depth |

*Currently, results are stored in-memory in the gateway. The store worker,
Redis queue integration, and PostgreSQL/Blob persistence are Day 2 tasks.*

---

## Infrastructure

### Azure Services

| Service | SKU | Purpose | Cost/hour |
|---|---|---|---|
| AKS | Free tier, 3x Standard_B2ms | Container orchestration | ~€0.25 |
| ACR | Basic | Container image registry | ~€0.007 |
| PostgreSQL Flexible | Burstable B1ms | Metadata + pgvector embeddings | ~€0.017 |
| Blob Storage | Hot, LRS | Original PDF archive | ~€0.00 |
| Managed Grafana | Essential (free) | Monitoring dashboards | €0.00 |
| **Total** | | | **~€0.28/hr** |

When stopped (`az aks stop` + `az postgres flexible-server stop`): ~€0.01/hr (disk only).

### Helm Charts (Day 2)

| Chart | Namespace | Purpose |
|---|---|---|
| kube-prometheus-stack | monitoring | Prometheus + Grafana |
| bitnami/redis | documentstream | Message queue (Redis Streams) |
| kedacore/keda | keda | Event-driven autoscaling |
| chaos-mesh/chaos-mesh | chaos-mesh | Chaos engineering |
| ingress-nginx | ingress-nginx | HTTP routing |

*Not yet installed — these are deployed when the AKS cluster is provisioned.*

### CI/CD

GitHub Actions workflows:
- **ci.yml** — On push to main and PRs: ruff lint, ruff format check, pytest with coverage
- **deploy.yml** — *Not yet created.* Will build images → push to ACR → deploy to AKS

---

## Data Model

### LoanScenario

All documents in a scenario share linked data:

```
LoanScenario
  ├── loan_id: "CRE-917982"
  ├── client
  │     ├── company_name: "Van der Berg B.V."
  │     ├── registration_number: "KVK-12345678"
  │     ├── contact_name: "Jan de Vries"
  │     └── ...
  ├── property
  │     ├── address: "Herengracht 42"
  │     ├── city: "Amsterdam"
  │     ├── property_type: "Office building"
  │     └── ...
  ├── loan_amount_eur: 5_000_000
  ├── interest_rate_pct: 4.25
  └── dates (chronological)
        ├── application_date
        ├── valuation_date
        ├── kyc_date
        ├── contract_date
        └── invoice_date
```

### Document Types

| Type | Privacy | Text Volume | Semantic Search |
|---|---|---|---|
| Loan application | Confidential | Low (~100 words) | No |
| Valuation report | Confidential | High (~900 words) | Yes |
| KYC report | Secret | High (~500 words) | Yes |
| Loan agreement | Secret | High (~1100 words) | Yes |
| Contractor invoice | Public | Low (~100 words) | No |

---

## Key Design Decisions

1. **Redis Streams over Pub/Sub or Lists.** Streams provide at-least-once delivery
   with consumer group acknowledgment. When a worker pod crashes, messages are
   re-delivered — zero data loss.

2. **KEDA over HPA.** Standard HPA scales on CPU/memory. KEDA scales on queue
   depth — the metric that actually matters for a pipeline.

3. **Two classifiers (rules + semantic).** Rules handle structured dimensions
   (privacy level) deterministically. Semantic handles contextual dimensions
   (environmental impact) that rules can't assess.

4. **pgvector over a dedicated vector DB.** Keeps the architecture simple — one
   database for metadata and vectors. Azure PostgreSQL Flexible Server supports
   pgvector natively. For production at scale, Azure AI Search would be the
   enterprise choice.

5. **Descriptive anchor texts over keyword lists.** Anchor texts are natural
   language paragraphs describing each category. The embedding model captures
   meaning, enabling detection of concepts expressed in different words.

6. **Local sentence-transformers over Azure OpenAI.** No API dependency, free,
   runs anywhere. For production, Azure OpenAI text-embedding-3-small would
   provide higher quality embeddings within Azure's data boundary.
