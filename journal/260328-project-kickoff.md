# Project Kickoff — DocumentStream

**Date:** 2026-03-28

## What happened

Started the DocumentStream project from scratch — a K8s-native document processing pipeline
for commercial real estate loan documents, built as a portfolio demo for a RaboBank
Data Engineer interview.

## Key decisions

- **Scenario:** Commercial real estate loan lifecycle. A developer applies for a loan to
  renovate an office building. The lifecycle generates 5 linked document types (loan
  application, property valuation report, KYC/due diligence report, loan agreement,
  contractor invoice). All documents in a loan share the same loan_id, client, and property.

- **Classification levels:** Public, Confidential, Secret. Dropped Top Secret (fraud/SARs)
  — it uses the same classification logic, and faking a fraud scenario for a formal interview
  felt forced. Better to mention it as a production extension.

- **5 templates, not 10+.** Originally planned the full loan lifecycle with ~10 document types.
  Trimmed to 5 to stay within the 3-day timeline. The K8s infrastructure is what matters for
  the interview, not the document variety.

- **Rule-based classifier over ML.** Weighted keyword scoring is deterministic, explainable,
  and built in an hour. Can add a scikit-learn TF-IDF layer later if time allows.

- **pgvector for semantic search.** Three document types (valuation reports, KYC reports,
  contracts) have enough text (500-1100+ words) to warrant vector embeddings. Using
  PostgreSQL with pgvector keeps the architecture simple — one database for metadata and
  vectors.

- **Local-first development.** Building with docker-compose first, deploying to Azure AKS
  on Day 2. This avoids blocking on Azure account setup.

- **fpdf2 over reportlab.** Lighter, simpler API, MIT licensed. Generates 72 docs/sec which
  is more than enough for stress testing.

- **Faker with nl_NL locale.** Dutch names, addresses, IBANs for realism. KVK registration
  numbers for companies.

## What was built

| Component | Files | Status |
|---|---|---|
| Document generator | `src/generator/scenario.py`, `templates.py`, `generate.py` | Complete |
| Text extractor | `src/worker/extract.py` | Complete |
| Classifier | `src/worker/classify.py` | Complete |
| FastAPI gateway | `src/gateway/app.py`, `templates/index.html` | Complete |
| Semantic classifier | `src/worker/semantic.py` | Complete |
| Tests | `tests/test_*.py` (51 tests) | All passing |
| Docker Compose | `docker-compose.yml` + Dockerfile | Config validated |
| Documentation | `docs/` (dictionary, architecture, classification, demo guide) | Complete |
| Architecture plan | `.engineering-team/architecture-plan.md` | Complete |

## Performance numbers

- PDF generation: 72 docs/sec (1,000 docs in ~14 seconds)
- Rule-based classification accuracy: 100% on generated documents
- Semantic classification: differentiates environmental risk levels correctly
- Test suite: 51 tests in 7.6 seconds

## Azure cost estimate

~€0.28/hour running (AKS Free tier + 3x B2ms nodes + PostgreSQL B1ms + Blob Storage).
Near-zero when stopped via `az aks stop`.

## What's next (Day 2)

1. Redis queue integration — wire the pipeline stages through Redis Streams
2. KEDA ScaledObjects — queue-depth autoscaling for each worker
3. Grafana + Prometheus dashboard — the centerpiece of the live demo
4. Chaos Mesh experiments — pod kills, network delay, CPU stress
5. Azure setup — AKS cluster, ACR, PostgreSQL Flexible Server
6. Vector embeddings with sentence-transformers + pgvector

## Semantic classifier decision

Added a dual-classifier approach: rule-based for privacy levels, semantic
(sentence-transformers + anchor embeddings) for environmental impact and
industry sectors. Key design choice: anchor texts are descriptive paragraphs,
not keyword lists. This enables the embedding model to catch contextual
environmental risks ("former textile dyeing facility" → industrial contamination)
that keyword matching would miss.

Chose pgvector over Azure AI Search for the demo — keeps architecture simple.
Will name-drop Azure AI Search in the interview as the production recommendation.

## Open questions

- Locust for load testing — deploy inside the cluster or run locally?
- How much time to spend on the web UI vs the K8s infrastructure?
