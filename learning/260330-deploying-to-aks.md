# Learning Journal: Deploying to AKS

**Date:** 2026-03-30 (Day 3)
**Goal:** Deploy DocumentStream to a live AKS cluster

---

## What We Accomplished

- Started AKS cluster and connected kubectl
- Built Docker images locally and pushed to ACR
- Installed 5 Helm charts (Redis, ingress-nginx, KEDA, Prometheus+Grafana, Chaos Mesh)
- Deployed all app components (gateway, extract-worker, classify-worker, store-worker)
- Deployed PostgreSQL with pgvector in-cluster
- Initialized the database schema
- Got the pipeline running end-to-end: `curl http://51.138.91.82/health` returns `{"mode":"async"}`

---

## Commands Reference

### AKS Cluster Management

```bash
# Start a stopped cluster (takes 3-8 minutes)
az aks start -g DocumentStream -n DocumentStreamManagedCluster

# Check cluster power state
az aks show -g DocumentStream -n DocumentStreamManagedCluster --query "powerState.code" -o tsv

# Get kubectl credentials (re-run after every cluster restart!)
az aks get-credentials -n DocumentStreamManagedCluster -g DocumentStream --overwrite-existing

# Verify cluster connectivity
kubectl get nodes

# Attach ACR to AKS (so cluster can pull images without extra auth)
az aks update -n DocumentStreamManagedCluster -g DocumentStream --attach-acr acrdocumentstream
```

### Building and Pushing Docker Images

```bash
# Log in to ACR (requires Docker Desktop running)
az acr login -n acrdocumentstream

# Build for AMD64 (required — AKS runs x86_64, Mac is ARM64)
docker build --platform linux/amd64 -t acrdocumentstream.azurecr.io/gateway:latest -f src/gateway/Dockerfile .
docker build --platform linux/amd64 -t acrdocumentstream.azurecr.io/worker:latest -f src/worker/Dockerfile .

# Push to ACR
docker push acrdocumentstream.azurecr.io/gateway:latest
docker push acrdocumentstream.azurecr.io/worker:latest
```

### Helm Charts

```bash
# Add chart repositories (like adding package sources in apt/brew)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add kedacore https://kedacore.github.io/charts
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update

# Install Redis (message broker)
helm upgrade --install redis bitnami/redis \
    --namespace documentstream \
    --create-namespace \
    --set architecture=standalone \
    --set auth.enabled=false \
    --set master.resources.requests.cpu=50m \
    --set master.resources.requests.memory=64Mi \
    --set master.resources.limits.cpu=200m \
    --set master.resources.limits.memory=128Mi \
    --wait --timeout 120s

# Install ingress-nginx (HTTP traffic entry point)
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.replicaCount=1 \
    --set controller.resources.requests.cpu=50m \
    --set controller.resources.requests.memory=128Mi \
    --set controller.resources.limits.cpu=200m \
    --set controller.resources.limits.memory=256Mi \
    --wait --timeout 120s

# Install KEDA (autoscaler that watches Redis queue depth)
helm upgrade --install keda kedacore/keda \
    --namespace keda \
    --create-namespace \
    --set resources.operator.requests.cpu=50m \
    --set resources.operator.requests.memory=64Mi \
    --set resources.metricServer.requests.cpu=50m \
    --set resources.metricServer.requests.memory=64Mi \
    --wait --timeout 120s

# Install Prometheus + Grafana (monitoring)
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set prometheus.prometheusSpec.resources.requests.cpu=100m \
    --set prometheus.prometheusSpec.resources.requests.memory=256Mi \
    --set prometheus.prometheusSpec.retention=12h \
    --set grafana.resources.requests.cpu=50m \
    --set grafana.resources.requests.memory=128Mi \
    --set alertmanager.enabled=false \
    --set nodeExporter.enabled=false \
    --wait --timeout 180s

# Install Chaos Mesh (failure injection)
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
    --namespace chaos-mesh \
    --create-namespace \
    --set controllerManager.resources.requests.cpu=25m \
    --set controllerManager.resources.requests.memory=64Mi \
    --set dashboard.resources.requests.cpu=25m \
    --set dashboard.resources.requests.memory=64Mi \
    --wait --timeout 120s

# Check all installed releases
helm list --all-namespaces
```

### Deploying the App

```bash
# Apply all K8s manifests via Kustomize
kubectl apply -k k8s/base/

# Apply KEDA autoscaling rules
kubectl apply -f k8s/scaling/

# Initialize PostgreSQL schema
kubectl exec -n documentstream deployment/postgres -- psql -U documentstream -d documentstream -f /dev/stdin < src/worker/schema.sql
```

### Debugging Commands

```bash
# Watch pods in real-time
kubectl get pods -n documentstream -w

# Check logs for a crashing pod
kubectl logs deployment/gateway -n documentstream --tail=30
kubectl logs deployment/store-worker -n documentstream --tail=30

# Detailed pod info including events (useful for scheduling/pull errors)
kubectl describe pod -n documentstream -l app=store-worker

# Restart a deployment (forces new pods)
kubectl rollout restart deployment/store-worker -n documentstream

# Get everything in a namespace
kubectl get all -n documentstream

# Check external IP for ingress
kubectl get svc -n ingress-nginx
```

### DNS Debugging (macOS)

```bash
# Flush macOS DNS cache
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder

# Test DNS resolution against a specific DNS server
nslookup <hostname> 8.8.8.8

# Flush Unbound cache (if running Unbound as DNS resolver)
# SSH into the Unbound host first, then:
sudo unbound-control flush_zone azmk8s.io
# Or brute force: sudo systemctl restart unbound
```

---

## Questions & Answers

### Docker & Container Images

**Q: The Dockerfiles don't mention PyTorch, so where does the 5GB layer come from?**
A: Transitive dependencies. `pyproject.toml` requires `sentence-transformers`, which requires
`torch`, which pulls in ~5GB of CUDA/CPU libraries. The chain is resolved by `uv` and locked
in `uv.lock`. When the Dockerfile runs `uv sync --no-dev --frozen`, it installs everything in
the lock file, including transitive deps.

**Q: Do we need PyTorch for inference? Can we use ONNX instead?**
A: No, we don't need full PyTorch for inference-only. `sentence-transformers` supports an ONNX
backend (~50MB vs 5GB). One-line code change: `SentenceTransformer("all-MiniLM-L6-v2", backend="onnx")`.
Alternatively, installing PyTorch CPU-only cuts it to ~200MB. Good optimization for later.

**Q: What does each line of the gateway Dockerfile do?**
A:
- `FROM python:3.13-slim` — Base image. Slim = stripped-down Debian (~150MB vs ~1GB full).
- `WORKDIR /app` — Sets working directory. Creates it if it doesn't exist.
- `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv` — Multi-stage copy trick.
  Pulls the uv image, copies just the binary. Two parts after `--from`: source path in the
  external image, destination path in our image.
- `COPY pyproject.toml uv.lock ./` — Copies dependency files first (layer caching optimization).
  Everything except the last argument is a source; the last is the destination.
- `RUN uv sync --no-dev --frozen` — Install production deps. `--no-dev` skips test/dev deps.
  `--frozen` means use exact versions from lock file, fail if they don't match (reproducibility).
- `COPY src/ src/` — Copy source code AFTER deps (so code changes don't invalidate dep cache).
- `ENV PYTHONPATH=/app/src` — So Python can find modules.
- `EXPOSE 8000` — Documentation only. Doesn't actually open the port.
- `CMD [...]` — Default start command. `0.0.0.0` binds to all interfaces (required in containers).

**Q: What does `docker build -t` mean?**
A: `-t` is **tag** (the name for the image), not target. The format is `registry/image:version`.
`-f` specifies the Dockerfile path.

**Q: Can I use the terminal instead of Docker Desktop?**
A: `docker` is a CLI tool that runs in the terminal. Docker Desktop is the background daemon +
a GUI wrapper. The daemon must be running (start Docker Desktop app), then you use `docker`
commands in the terminal.

**Q: What does `size: 2209` mean in Docker push output?**
A: That's the size of the image **manifest** (2.2KB) — a JSON document listing all layers and
their digests. The actual image is the sum of all those layers (much bigger).

### Azure & ACR

**Q: For `az acr build`, don't we need `-g` for resource group and `-n` for name?**
A: No. ACR registry names are globally unique across all of Azure, so `-r acrdocumentstream`
is enough. Most other `az` commands need `-g` + `-n` because resource names are only unique
within a resource group, but ACR is different.

**Q: How does `az acr build` work? Where does the compute come from?**
A: `az acr build` uploads your local files to Azure, spins up a temporary compute instance
("ACR Task"), runs `docker build` in the Azure datacenter, stores the image, and destroys
the compute. You don't manage the compute — it's included in the ACR SKU. Much faster than
building locally and pushing, because the build happens near the registry with fast network
for pulling base images. (Note: ACR Tasks may be disabled on some subscription types — ours
was, so we built locally instead.)

### Helm

**Q: What is Helm?**
A: A package manager for Kubernetes — like `brew` for Mac or `apt` for Ubuntu, but for K8s.
A Helm **chart** bundles all the K8s manifests needed for a service (Deployment, Service,
ConfigMap, etc.) into a single package with configurable options via `--set` flags. Without
Helm, deploying Redis would mean writing 10+ YAML files yourself.

**Q: Is there a Helm registry? Does Helm download config or code?**
A: Yes, chart repositories (added via `helm repo add`). There's also a central search hub at
artifacthub.io. Helm downloads **config files** — specifically templated YAML with Go template
placeholders (e.g., `{{ .Values.auth.enabled }}`). Helm renders the templates with your `--set`
overrides, producing plain K8s manifests, then applies them. No code runs — purely YAML
templating and packaging.

**Q: What does `helm upgrade --install` do?**
A: Install if it doesn't exist, upgrade if it does. Idempotent — safe to run multiple times.
Key flags:
- `--namespace` / `--create-namespace` — target namespace, create if needed
- `--set key=value` — override chart defaults
- `--wait` — block until pods are actually running
- `--timeout` — give up after this duration

### Kubernetes Concepts

**Q: What are the main K8s resource types?**
A:

| Resource | What it does | Analogy |
|---|---|---|
| Pod | Smallest unit — one or more containers | A single process |
| Deployment | Manages Pod replicas, rolling updates | systemd service manager |
| Service | Stable network endpoint for Pods | A load balancer / DNS entry |
| ConfigMap | Key-value config as env vars or files | `.env` file |
| Secret | Like ConfigMap but for sensitive data | `.env` for passwords |
| Ingress | HTTP routing from outside the cluster | Nginx reverse proxy config |
| Namespace | Logical isolation of resources | A folder / project boundary |
| StatefulSet | Like Deployment but for stateful apps | Used for databases |
| PersistentVolumeClaim | Requests disk storage | Mounting a drive |
| ScaledObject | KEDA CRD — autoscaling rules | Custom (not built-in K8s) |

**Q: What is a CRD (Custom Resource Definition)?**
A: CRDs extend K8s with new resource types that don't exist out of the box. When you install
KEDA, it registers `ScaledObject` as a CRD. When you install Chaos Mesh, it registers
`PodChaos`, `NetworkChaos`, `StressChaos`. Without the operator installed, K8s would reject
these YAML files as unknown types. The pattern is: Helm chart installs operator + CRDs →
you create instances of those CRDs → the operator watches for them and acts.

**Q: What does `kubectl run` do? And what's a Redis client vs server?**
A: `kubectl run` creates a **new** Pod from scratch — it's not starting something that already
exists. You always specify an image because you're creating a new container.

Redis is a server (listens on port 6379). A Redis client is anything that connects to it —
your Python workers are clients, `redis-cli` is a command-line client for debugging.

**Q: Why are there two Services for Redis (redis-master and redis-headless)?**
A:
- `redis-master` (ClusterIP 10.0.54.69) — Normal Service with a virtual IP. Your app connects
  to this. K8s DNS resolves the name to the virtual IP, then routes to the Redis Pod.
- `redis-headless` (ClusterIP None) — No virtual IP. DNS resolves directly to the Pod's actual
  IP. StatefulSets need this for stable per-Pod DNS names. Used internally by Redis, not by
  your app.

Both can use port 6379 because they have different ClusterIPs — like two different domain names
both hosting websites on port 443.

---

## Problems We Hit & How We Fixed Them

### 1. DNS Resolution Failure After AKS Restart

**Symptom:** `kubectl get nodes` returned `no such host` after restarting the cluster.

**Root cause:** Three layers of DNS caching conspired against us:
- Tailscale VPN was running with its own DNS resolver (100.100.100.100)
- AdGuard Home on the local network (192.168.2.111) was the DNS server
- Unbound (behind AdGuard) had cached an NXDOMAIN response from when the cluster was stopped

**Debug steps:**
1. Re-fetched kubectl credentials — didn't help
2. Tested DNS with `nslookup <hostname> 8.8.8.8` — resolved fine via Google DNS
3. Identified local DNS server (100.100.100.100 = Tailscale) was the problem
4. Disconnected Tailscale — still failed because AdGuard/Unbound also cached NXDOMAIN
5. Flushed Unbound cache: `sudo unbound-control flush_zone azmk8s.io`
6. Flushed macOS cache: `sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`

**Lesson:** When AKS stops, the API server DNS record may go stale. After restart, every DNS
cache in the chain needs flushing: Unbound/upstream resolver → AdGuard → macOS.

### 2. ACR Tasks Not Permitted

**Symptom:** `az acr build` returned `TasksOperationsNotAllowed`.

**Root cause:** ACR Tasks (remote builds) are disabled on some Azure subscription types.

**Fix:** Build locally with `docker build` and push with `docker push` instead. Same result,
just uses your machine for the build.

### 3. exec format error (Architecture Mismatch)

**Symptom:** All pods crashed with `exec /usr/local/bin/uv: exec format error`.

**Root cause:** `docker build` on an Apple Silicon Mac builds ARM64 images by default. AKS
nodes run AMD64 (x86_64). The `uv` binary (copied from the uv image) was ARM64 and couldn't
execute on the x86_64 node.

**Fix:** Rebuild with `--platform linux/amd64`:
```bash
docker build --platform linux/amd64 -t acrdocumentstream.azurecr.io/gateway:latest -f src/gateway/Dockerfile .
```
The build runs under emulation (slower) but produces images that work on AKS.

**Lesson:** Always specify `--platform linux/amd64` when building for cloud deployment on
an Apple Silicon Mac. The `COPY --from=ghcr.io/astral-sh/uv:latest` line is architecture-
sensitive — Docker picks the platform variant matching your build target.

### 4. extract-worker OOMKilled

**Symptom:** extract-worker kept restarting with `OOMKilled` status.

**Root cause:** Memory limit was 128Mi. PyMuPDF under AMD64 emulation (or just normal operation)
needed more than that.

**Fix:** Bumped memory limit from 128Mi to 256Mi in `k8s/base/extract-deployment.yaml`.

### 5. store-worker Can't Find PostgreSQL

**Symptom:** `psycopg.OperationalError: failed to resolve host 'postgres.documentstream.svc.cluster.local'`

**Root cause:** The ConfigMap referenced a PostgreSQL hostname, but we hadn't deployed
PostgreSQL to the cluster yet. The implementation plan assumed Azure PostgreSQL Flexible
Server, but we're deploying in-cluster for simplicity.

**Fix:** Deployed PostgreSQL with pgvector in the cluster (see problem 6 & 7 below), updated
ConfigMap to point to `postgres-postgresql.documentstream.svc.cluster.local`.

### 6. Bitnami PostgreSQL Chart Rejected pgvector Image

**Symptom:** Helm refused to install with a non-Bitnami container image.

**Root cause:** Bitnami charts include a security check that blocks unrecognized images.

**Fix:** Added `--set global.security.allowInsecureImages=true`. But this led to problem 7...

### 7. pgvector Image Incompatible with Bitnami Chart

**Symptom:** PostgreSQL pod crashed with `could not create lock file "/var/run/postgresql/.s.PGSQL.5432.lock": Read-only file system`

**Root cause:** Bitnami's chart mounts `/var/run/postgresql` as read-only, but the vanilla
`pgvector/pgvector:pg16` image expects to write there. Bitnami charts are designed for
Bitnami images with a specific filesystem layout.

**Fix:** Abandoned the Bitnami PostgreSQL chart entirely. Created a simple Deployment + Service
manifest (`k8s/base/postgres-deployment.yaml`) using the `pgvector/pgvector:pg16` image
directly. This works because we don't need Bitnami's advanced features (replication, backup,
etc.) for a demo.

**Lesson:** Helm charts are opinionated about their container images. If you need a specific
image (like pgvector), sometimes a simple hand-written Deployment is easier than fighting
the chart's assumptions.

---

## Current State

```
Cluster: DocumentStreamManagedCluster (2x Standard_B2s_v2, West Europe)
External IP: 51.138.91.82
Health check: curl http://51.138.91.82/health → {"mode":"async"}

Pods running:
  - gateway (2 replicas)
  - extract-worker (1 replica)
  - classify-worker (1 replica)
  - store-worker (1 replica)
  - redis-master (1 replica)
  - postgres (1 replica)

Helm releases:
  - redis (documentstream namespace)
  - ingress-nginx (ingress-nginx namespace)
  - keda (keda namespace)
  - prometheus + grafana (monitoring namespace)
  - chaos-mesh (chaos-mesh namespace)

Still TODO:
  - Apply KEDA ScaledObjects (kubectl apply -f k8s/scaling/)
  - Import Grafana dashboard
  - Apply Chaos Mesh experiments
  - Run Locust load test
  - Demo rehearsal
```
