# DocumentStream

A Kubernetes-native document processing pipeline for commercial real estate loan documents.
Demonstrates production K8s patterns, CI/CD, event-driven autoscaling, and data engineering on Azure.

## What It Does

DocumentStream ingests PDF loan documents, extracts text, and classifies them across multiple
dimensions using two complementary approaches:

- **Rule-based classification** -- weighted keyword scoring for privacy levels (Public / Confidential / Secret)
- **Semantic classification** -- sentence-transformer embeddings for environmental impact, industry sectors, and contextual privacy

Documents flow through a pipeline: Upload -> Extract -> Classify -> Store. Currently runs
synchronously via FastAPI; the target architecture uses Redis Streams with KEDA-scaled
Kubernetes workers for each stage.

## Quick Start

```bash
# Prerequisites: Python 3.13, uv (https://docs.astral.sh/uv/)

# Install dependencies
uv sync

# Run tests
make test

# Start local dev stack (gateway + Redis + PostgreSQL)
make dev

# Open the web UI
open http://localhost:8000
```

The web UI shows a dashboard with document stats, classification results, and a file upload form.

### Generate Test Documents

```bash
# Generate 10 loan scenarios (50 PDFs) into generated_docs/
make generate

# Or look at the committed samples
ls demo_samples/CRE-729976/
```

Each loan scenario produces 5 linked PDFs sharing the same client, property, and loan data:
loan application, valuation report, KYC report, contract, and invoice.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI dashboard |
| `/health` | GET | Liveness probe (status, version, timestamp) |
| `/api/documents` | POST | Upload a PDF for processing |
| `/api/documents` | GET | List documents (filter by classification, limit 1-500) |
| `/api/documents/{id}` | GET | Get a specific document's results |
| `/api/generate` | POST | Generate N loan scenarios for demo/load testing |

### Example: Upload and Classify a Document

```bash
curl -X POST http://localhost:8000/api/documents \
  -F "file=@demo_samples/CRE-729976/kyc_report.pdf"
```

Response includes both rule-based and semantic classification:
```json
{
  "document_id": "...",
  "classification": "Secret",
  "confidence": 0.85,
  "semantic_privacy": "Secret",
  "environmental_impact": "Low",
  "industries": ["Financial Services", "Real Estate"]
}
```

## Classification

### Rule-Based (Privacy)

Weighted keyword scoring assigns a privacy level with confidence and explainability.
Each keyword has a weight (e.g., "KYC" = 4.0, "due diligence" = 3.5). The classifier
returns matched keywords and per-level scores, making decisions auditable.

### Semantic (Environmental Impact + Industries)

Uses `all-MiniLM-L6-v2` (384-dim embeddings) with descriptive anchor texts -- not keyword
lists. This captures meaning: "textile dyeing facility" matches industrial contamination
risk even without the word "contamination" appearing anywhere.

Returns multi-label industry classifications (threshold 0.15) and environmental impact
ratings (None / Low / Medium / High). The document embedding is stored for later
pgvector semantic search.

See [docs/classification.md](docs/classification.md) for the full deep dive.

## Project Structure

```
src/
  gateway/          FastAPI API + web UI + Dockerfile
  worker/           Extract, classify, and semantic modules
  generator/        PDF document generator (5 templates, CLI)
tests/              51 pytest tests
docs/               Architecture, classification, demo guide, dictionary
demo_samples/       One committed loan scenario (5 PDFs)
k8s/                Kubernetes manifests (base, scaling, chaos)
infra/              Azure setup/teardown scripts
locust/             Load testing
grafana/            Dashboard JSON
journal/            Development journal
```

## Commands

| Command | Description |
|---|---|
| `make test` | Run pytest |
| `make test-cov` | Run tests + HTML coverage report |
| `make lint` | Ruff check + format check |
| `make lint-fix` | Auto-fix lint issues |
| `make generate` | Generate 10 scenarios (50 PDFs) |
| `make demo-samples` | Regenerate `demo_samples/` with one fresh scenario |
| `make dev` | Start docker-compose (gateway, Redis, PostgreSQL) |
| `make dev-down` | Tear down docker-compose |
| `make clean` | Remove build artifacts and caches |

## Architecture

### Current (Synchronous)

```
PDF Upload --> FastAPI Gateway --> Extract (PyMuPDF)
                               --> Classify (rules + semantic)
                               --> Return results (in-memory)
```

### Target (Kubernetes + Redis Streams)

```
PDF Upload
  |
  v
Redis:raw-docs --> Extract Workers (PyMuPDF)
  |
  v
Redis:extracted --> Classify Workers (rules + semantic)
  |
  v
Redis:classified --> Store Workers --> PostgreSQL (pgvector)
                                   --> Azure Blob Storage
```

Each stage runs as a separate K8s Deployment. KEDA monitors Redis Stream consumer group
lag and scales workers based on queue depth. See [docs/architecture.md](docs/architecture.md)
for the full design.

## CI/CD

**GitHub Actions workflows:**

- **ci.yml** -- Lint (ruff) + test (pytest with coverage) on every push and PR
- **docker.yml** -- Build and push Docker image to `ghcr.io/johnmathews/documentstream` on push to main

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Redis Streams over Pub/Sub | At-least-once delivery with consumer group acknowledgment; crash-safe |
| KEDA over HPA | Scale on queue depth (actual work), not CPU (misleading for queue workers) |
| Two classifiers | Rules for structured dimensions, semantic for contextual ones |
| pgvector over dedicated vector DB | Keeps architecture simple; PostgreSQL Flexible supports it natively |
| Descriptive anchors (not keyword lists) | Embedding model captures meaning, not just string matches |
| Local sentence-transformers | No API dependency, runs anywhere, free |

## Documentation

- [Architecture](docs/architecture.md) -- System design, pipeline flow, K8s target
- [Classification](docs/classification.md) -- Rule-based vs semantic approaches in detail
- [Demo Guide](docs/demo-guide.md) -- Step-by-step demo script with talking points
- [Dictionary](docs/dictionary.md) -- K8s, Azure, and KEDA concepts

## Stack

Python 3.13, FastAPI, PyMuPDF, fpdf2, Faker, sentence-transformers, Redis, PostgreSQL (pgvector),
Docker, GitHub Actions, uv, pytest, ruff. Target: AKS, KEDA, Prometheus, Grafana, Chaos Mesh.
