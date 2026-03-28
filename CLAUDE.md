# DocumentStream — K8s Document Processing Pipeline

## Project Overview
Portfolio project for RaboBank Data Engineer interview demonstrating Kubernetes, CI/CD,
and data engineering on Azure. A document processing pipeline for commercial real estate
loan documents.

## Stack
- **Language:** Python 3.13
- **API:** FastAPI
- **Queue:** Redis (Streams)
- **Database:** PostgreSQL with pgvector
- **PDF generation:** fpdf2 + Faker (nl_NL locale)
- **Text extraction:** PyMuPDF (fitz)
- **Rule-based classification:** Weighted keyword scoring (privacy level)
- **Semantic classification:** sentence-transformers + anchor embeddings (environmental impact, industries)
- **Vector DB:** PostgreSQL + pgvector (384-dim embeddings)
- **Testing:** pytest + coverage
- **Linting:** ruff
- **Deps:** uv

## Project Structure
- `src/gateway/` — FastAPI API + web UI
- `src/worker/` — Pipeline workers (extract, classify, semantic, store)
- `src/generator/` — PDF document generator (5 templates)
- `tests/` — All tests
- `k8s/` — Kubernetes manifests
- `infra/` — Azure setup/teardown scripts
- `locust/` — Load testing
- `grafana/` — Dashboard JSON
- `docs/` — Documentation
- `journal/` — Development journal

## Commands
- `make test` — Run tests with pytest
- `make lint` — Run ruff linter
- `make generate` — Generate sample documents
- `make dev` — Start local dev environment (docker-compose)

## Key Patterns
- Each pipeline stage is a separate K8s Deployment scaled by KEDA
- Documents flow through Redis queues: raw-docs → extracted → classified → stored
- All documents in a loan scenario share the same loan_id, client, and property data
- 5 document types: loan_application, valuation_report, kyc_report, contract, invoice
- Two classifiers run on every document:
  - Rule-based: privacy level (Public/Confidential/Secret) via keyword scoring
  - Semantic: environmental impact (None/Low/Medium/High) + industry sectors via embeddings
- Document embeddings stored in pgvector for semantic search
- Anchor texts are descriptive paragraphs, not keyword lists
