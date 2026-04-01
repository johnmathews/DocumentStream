# Day 4 (evening): Azure Blob Storage Integration and Prometheus Metrics

**Date:** 2026-04-01

## What Was Done

Integrated Azure Blob Storage for PDF persistence and added custom Prometheus metrics
to the Grafana dashboard, completing the storage layer of the pipeline.

### Azure Blob Storage

- Created Azure Storage Account (`documentstream`) in `rg-documentstream`
- Added `azure-storage-blob` dependency to `pyproject.toml`
- Added Azurite emulator service to `docker-compose.yml` for local dev
- Store worker uploads PDFs to blob storage on every processed document
- Gateway's `/api/generate` endpoint also uploads PDFs directly to blob storage
- Container auto-created on first upload (no manual setup needed)
- Blob path structure: `{doc_id}/{loan_id}/{doc_type}.pdf`

### Database Schema Changes

- Added `doc_type` column to `documents` table (loan_application, valuation_report, kyc_report, contract, invoice)
- Added `blob_url` column to track blob storage path per document
- Added index on `doc_type` for filtering
- Ran `ALTER TABLE` migration on live cluster via `kubectl exec`

### Custom Prometheus Metrics

- Added `prometheus_client` dependency
- Two new counters exposed by the gateway (`/metrics` endpoint):
  - `documentstream_blob_uploads_total` — count of uploads by `doc_type`
  - `documentstream_blob_bytes_total` — bytes uploaded by `doc_type`
- Store worker also exposes same metrics on port 9102
- Created `k8s/base/servicemonitor.yaml` (ServiceMonitor CRD) so kube-prometheus-stack
  scrapes the gateway — the `release: prometheus` label was required

### Grafana Dashboard

- Added 2 new panels (total now 9):
  - "Blob Storage — PDF Count by Type" (bar gauge)
  - "Blob Storage — Total Size by Type" (bar gauge, bytes unit)
- Both query the new `documentstream_blob_*` counters, labeled by `doc_type`

### Doc Type Inference

- `infer_doc_type()` extracts doc type from filename pattern `{loan_id}/{doc_type}.pdf`
- Matches against known types; defaults to "unknown" for arbitrary uploads

## Bugs Fixed During Deployment

- **`bytearray` upload error:** fpdf2 generator returns `bytearray`, but Azure SDK's
  `upload_blob()` failed with `TypeError: can't concat int to bytes`. Fixed by wrapping
  in `bytes()` before upload.
- **ServiceMonitor discovery:** Prometheus pod annotations (`prometheus.io/scrape`) don't
  work with kube-prometheus-stack — it uses ServiceMonitor CRDs with a `release: prometheus`
  label selector. Created the ServiceMonitor and named the Service port.

## K8s Concepts Learned

- `kubectl rollout restart` — triggers rolling restart without YAML changes (needed when
  ConfigMap values change, since K8s doesn't auto-restart pods for ConfigMap updates)
- `kubectl get all` doesn't return all resources — HPAs, ConfigMaps, Secrets, Ingresses
  are excluded. It's a hardcoded subset, not a discovery command.
- `kubectl config set-context --current --namespace=X` — sets default namespace
- Deployment vs Service: Deployment manages pods (what to run), Service provides stable
  networking (how to reach them)
- Pod READY column `1/1` means ready containers / total containers in the pod
- `docker build` only builds locally — must `docker push` to ACR, or use `az acr build`
- ServiceMonitor CRD is how kube-prometheus-stack discovers scrape targets (not pod annotations)

## Files Changed

- `pyproject.toml` — added azure-storage-blob, prometheus_client
- `docker-compose.yml` — added Azurite service, blob env vars on store-worker
- `src/worker/schema.sql` — added doc_type, blob_url columns + index
- `src/worker/store.py` — doc_type/blob_url in record + SQL, infer_doc_type(), Prometheus counters
- `src/worker/store_runner.py` — infers doc_type, records blob_url, starts metrics server
- `src/gateway/app.py` — generate endpoint uploads to blob, /metrics endpoint added
- `k8s/base/configmap.yaml` — added BLOB_CONNECTION_STRING, BLOB_CONTAINER
- `k8s/base/store-deployment.yaml` — metrics port + Prometheus annotations
- `k8s/base/gateway-deployment.yaml` — Prometheus annotations
- `k8s/base/gateway-service.yaml` — named port for ServiceMonitor
- `k8s/base/servicemonitor.yaml` — new file, Prometheus scrape config
- `grafana/documentstream-dashboard.json` — 2 new blob storage panels
- `tests/test_store.py` — 9 new tests (doc_type inference, blob upload, record fields)

### Switch to ONNX Runtime

- Changed `SentenceTransformer(MODEL_NAME)` to `SentenceTransformer(MODEL_NAME, backend="onnx")`
  in `src/worker/semantic.py`
- Replaced `sentence-transformers` dependency with `sentence-transformers[onnx]` in `pyproject.toml`
  (pulls in `onnxruntime` and `optimum`)
- ONNX Runtime is ~50MB vs ~5GB for full PyTorch — faster image pulls, faster KEDA scale-up,
  lower memory per classify-worker pod

### Wrap-up Fixes (code review)

- Added `servicemonitor.yaml` to `k8s/base/kustomization.yaml` — it was missing, so
  `kubectl apply -k k8s/base/` would silently skip it
- Increased store-worker memory limits from 64Mi/128Mi to 128Mi/256Mi — Python with
  psycopg, azure-storage-blob, and prometheus_client exceeds 64Mi
- Added comment on Azurite dev key in docker-compose.yml to prevent false positives
  from secret scanners

## Test Status

- 92 tests passing (up from 83), 88% coverage, lint clean
