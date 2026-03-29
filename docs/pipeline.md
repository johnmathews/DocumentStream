# DocumentStream — Redis Streams Pipeline

## Overview

The document processing pipeline uses Redis Streams as a message broker
between three processing stages. Each stage is an independent worker process
that reads from one stream and writes to the next.

```
raw-docs  →  Extract Worker  →  extracted  →  Classify Worker  →  classified  →  Store Worker  →  PostgreSQL
```

## Streams

| Stream | Consumer Group | Message Fields | Purpose |
|--------|---------------|----------------|---------|
| `raw-docs` | `extract-group` | `doc_id`, `filename`, `pdf_b64` | Uploaded PDFs waiting for text extraction |
| `extracted` | `classify-group` | `doc_id`, `filename`, `text`, `page_count`, `word_count`, `pdf_b64` | Extracted text waiting for classification |
| `classified` | `store-group` | All classification fields + `embedding`, `pdf_b64` | Classified documents waiting for storage |

## Dual-Mode Gateway

The gateway (`src/gateway/app.py`) operates in two modes:

**Sync mode** (default, no `REDIS_URL`):
- Processes documents inline: extract → classify → return results
- Used for local development and testing
- All 51 original tests run in this mode

**Async mode** (`REDIS_URL` is set):
- Publishes to `raw-docs` stream, returns `status: queued` immediately
- Client polls `GET /api/documents/{id}` to track progress
- Status updates come from Redis hashes (`doc:{doc_id}`)

## Workers

### Extract Worker (`src/worker/extract_runner.py`)

- Reads PDF bytes from `raw-docs`
- Extracts text using PyMuPDF
- Publishes extracted text to `extracted`
- Lightweight — fast startup, low memory

### Classify Worker (`src/worker/classify_runner.py`)

- Reads extracted text from `extracted`
- Runs rule-based classifier (privacy level)
- Runs semantic classifier (environmental impact, industries)
- Publishes all results to `classified`
- Heavy — loads sentence-transformers model (~80MB, ~300-400MB total RAM)

### Store Worker (`src/worker/store_runner.py`)

- Reads classified data from `classified`
- Inserts into PostgreSQL (metadata + pgvector embedding)
- Optionally uploads original PDF to Azure Blob Storage
- Updates document status to `completed`

## Status Tracking

Document progress is tracked in Redis hashes at key `doc:{doc_id}`:

| Status | Set by |
|--------|--------|
| `queued` | Gateway (on upload) |
| `extracting` | Extract worker |
| `classifying` | Classify worker |
| `storing` | Store worker |
| `completed` | Store worker (with classification results) |
| `failed` | Any worker (on unrecoverable error) |

## Reliability

- **At-least-once delivery**: Messages are only acknowledged (`XACK`) after
  successful processing. If a worker crashes, Redis re-delivers the message
  to another consumer in the group.
- **Graceful shutdown**: Workers catch `SIGTERM` (sent by K8s before pod
  termination) and finish processing the current message before exiting.
- **Idempotent storage**: The PostgreSQL INSERT uses `ON CONFLICT DO NOTHING`
  on `doc_id`, so re-processing a message doesn't create duplicates.

## Running Locally

```bash
# Start the full pipeline with docker-compose
docker compose up --build

# Upload a PDF
curl -F "file=@demo_samples/CRE-*/invoice.pdf" http://localhost:8000/api/documents

# Generate test documents (processed through the pipeline)
curl -X POST http://localhost:8000/api/generate -H "Content-Type: application/json" -d '{"count": 5}'

# Check document status
curl http://localhost:8000/api/documents/{document_id}
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Used by |
|----------|---------|---------|
| `REDIS_URL` | (empty = sync mode) | Gateway, all workers |
| `DATABASE_URL` | `postgresql://documentstream:...@localhost:5432/documentstream` | Store worker |
| `BLOB_CONNECTION_STRING` | (empty = skip blob upload) | Store worker |
| `BLOB_CONTAINER` | `documents` | Store worker |
| `STREAM_RAW` | `raw-docs` | Gateway, extract worker |
| `STREAM_EXTRACTED` | `extracted` | Extract worker, classify worker |
| `STREAM_CLASSIFIED` | `classified` | Classify worker, store worker |
| `READ_BLOCK_MS` | `2000` | All workers (XREADGROUP block timeout) |

## Database Schema

The `documents` table (`src/worker/schema.sql`) includes:
- Document metadata (filename, text, page/word counts)
- Rule-based classification (level, confidence, matched keywords, scores)
- Semantic classification (privacy, environmental impact, industries)
- pgvector embedding (`vector(384)`) with HNSW index for approximate nearest neighbor search
- Indexes on `classification` and `environmental_impact` for filtering
