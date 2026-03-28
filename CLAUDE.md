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

### Planned (not yet implemented)
- **Queue:** Redis Streams (pipeline message broker)
- **Database:** PostgreSQL with pgvector (metadata + embeddings)
- **Blob storage:** Azure Blob Storage (original PDFs)
- **Autoscaling:** KEDA (queue-depth based)
- **Monitoring:** Prometheus + Grafana
- **Chaos engineering:** Chaos Mesh

## Project Structure
- `src/gateway/` — FastAPI API + web UI (processes documents synchronously for now)
- `src/worker/` — Extract, classify, and semantic classification modules
- `src/generator/` — PDF document generator (5 templates, CLI tool)
- `tests/` — All tests (51 tests)
- `k8s/` — Kubernetes manifests (empty — Day 2)
- `infra/` — Azure setup/teardown scripts (empty — Day 2)
- `locust/` — Load testing (empty — Day 3)
- `grafana/` — Dashboard JSON (empty — Day 2)
- `docs/` — Documentation (architecture, classification, demo guide, dictionary)
- `journal/` — Development journal

## Commands
- `make test` — Run tests with pytest
- `make lint` — Run ruff linter
- `make generate` — Generate sample documents
- `make dev` — Start local dev environment (docker-compose)

## Key Patterns
- All documents in a loan scenario share the same loan_id, client, and property data
- 5 document types: loan_application, valuation_report, kyc_report, contract, invoice
- Two classifiers run on every document:
  - Rule-based: privacy level (Public/Confidential/Secret) via keyword scoring
  - Semantic: environmental impact (None/Low/Medium/High) + industry sectors via embeddings
- Document embeddings stored for later pgvector semantic search
- Anchor texts are descriptive paragraphs, not keyword lists

### Target architecture (Day 2-3)
- Each pipeline stage as a separate K8s Deployment scaled by KEDA
- Documents flow through Redis Streams: raw-docs → extracted → classified → stored
- Store worker persists to PostgreSQL (pgvector) + Azure Blob Storage
