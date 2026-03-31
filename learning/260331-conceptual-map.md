# Conceptual Map: DocumentStream on K8s

**Date:** 2026-03-31

This document maps out all the moving parts, what they do, and how they connect.
Use it as a mental model reference before the interview.

---

## The Big Picture

You have **three layers**:

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 3: Your Application                              │
│  Gateway, Extract/Classify/Store workers, Redis, Postgres│
│  Managed by: kubectl apply -k k8s/base/                 │
├─────────────────────────────────────────────────────────┤
│  LAYER 2: Platform Services (Helm charts)               │
│  KEDA, Prometheus+Grafana, Chaos Mesh, Ingress-nginx    │
│  Managed by: helm upgrade --install                     │
├─────────────────────────────────────────────────────────┤
│  LAYER 1: Infrastructure (Azure)                        │
│  AKS cluster, ACR registry, Nodes (VMs)                 │
│  Managed by: az aks / az acr / Azure Portal             │
└─────────────────────────────────────────────────────────┘
```

Each layer builds on the one below. You can change Layer 3 without touching Layer 2.
You can change Layer 2 without touching Layer 1.

---

## Components and What They Do

### Layer 1: Infrastructure

| Component | What it is | What it does | How you interact |
|---|---|---|---|
| **AKS cluster** | Managed Kubernetes on Azure | Runs the control plane + your nodes | `az aks start/stop/get-credentials` |
| **Nodes** (2x B2s_v2) | Virtual machines | Run your containers. Each has a kubelet agent | `kubectl get nodes` |
| **ACR** | Container image registry | Stores your Docker images | `docker push`, `az acr build` |
| **Control plane** | API server + etcd + scheduler + controllers | Brain of the cluster. You never see these VMs | `kubectl` talks to API server |

### Layer 2: Platform Services

| Component | Installed via | What it does | Namespace |
|---|---|---|---|
| **Redis** | `helm install redis bitnami/redis` | Message broker (Streams) between pipeline stages | documentstream |
| **Ingress-nginx** | `helm install ingress-nginx` | Routes external HTTP traffic into the cluster | ingress-nginx |
| **KEDA** | `helm install keda kedacore/keda` | Autoscales pods based on Redis queue depth | keda |
| **Prometheus + Grafana** | `helm install prometheus` | Collects metrics, displays dashboards | monitoring |
| **Chaos Mesh** | `helm install chaos-mesh` | Injects failures for testing resilience | chaos-mesh |

### Layer 3: Your Application

| Component | K8s resource type | Replicas | What it does |
|---|---|---|---|
| **Gateway** | Deployment + Service + Ingress | 2 | FastAPI app. Receives uploads, publishes to Redis |
| **Extract worker** | Deployment (+ KEDA ScaledObject) | 1-8 | Reads from `raw-docs` stream, extracts text with PyMuPDF |
| **Classify worker** | Deployment (+ KEDA ScaledObject) | 1-8 | Reads from `extracted` stream, runs rule-based + semantic classifiers |
| **Store worker** | Deployment (+ KEDA ScaledObject) | 1-8 | Reads from `classified` stream, writes to PostgreSQL |
| **PostgreSQL** | Deployment + Service + PVC | 1 | Stores document metadata, classifications, vector embeddings |

---

## The Levers You Pull

### 1. Deploying / Updating Your App

**Command:** `kubectl apply -k k8s/base/`

**What it does:** Sends all your YAML manifests to the API server. K8s compares
desired state (your YAML) with actual state (what's running) and reconciles.

**When to use:** After changing any YAML in `k8s/base/` — resource limits, replica
counts, env vars, image tags.

**Pattern:** Edit YAML → `kubectl apply` → K8s rolls out changes.

### 2. Scaling

**Automatic (KEDA):**
- `kubectl apply -f k8s/scaling/` — tells KEDA to watch Redis queue depth
- KEDA checks every 15 seconds. If lag > 5 messages, scales up. If lag = 0 for
  60 seconds, scales down. Min 1, max 8 replicas.
- `kubectl get hpa -n documentstream` — see current scaling state

**Manual override:**
- `kubectl scale deployment/classify-worker -n documentstream --replicas=3`
- KEDA will take back control when it next evaluates (within 15 seconds)

**Node-level scaling:** Not configured. Would use Cluster Autoscaler to add nodes
when pods are Pending. Currently fixed at 2 nodes.

### 3. Installing Platform Services

**Command:** `helm upgrade --install <name> <chart> --namespace <ns> --set key=value`

**What it does:** Downloads a chart (bundled templated YAML), renders it with your
`--set` values, and applies the resulting manifests.

**When to use:** Setting up infrastructure inside the cluster. One-time setup, then
rarely touched.

**Key flags:**
- `--create-namespace` — create namespace if it doesn't exist
- `--set key=value` — override chart defaults
- `--wait` — block until pods are running
- `--timeout` — give up after this duration

**See what's installed:** `helm list --all-namespaces`

### 4. Injecting Failures (Chaos Mesh)

**Command:** `kubectl apply -f k8s/chaos/pod-kill.yaml`

**What it does:** Creates a CRD instance. Chaos Mesh operator watches for it and
executes the failure injection.

**Three experiments:**
| File | What it does | Duration |
|---|---|---|
| `pod-kill.yaml` | Kills 2 classify-worker pods | 30s |
| `network-delay.yaml` | Adds 500ms latency to store-worker | 2min |
| `cpu-stress.yaml` | Burns 80% CPU on classify-worker | 2min |

**Clean up:** Experiments auto-expire after their duration. Or:
`kubectl delete podchaos pod-kill-classify-worker -n documentstream`

### 5. Monitoring

**Grafana dashboard:** Port-forward then open in browser.
```bash
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
# http://localhost:3000 (admin / <password from secret>)
```

**Quick CLI checks:**
```bash
kubectl get all -n documentstream          # Everything in your namespace
kubectl get hpa -n documentstream          # KEDA scaling state
kubectl get pods -n documentstream -w      # Watch pods in real-time
kubectl logs deployment/<name> -n documentstream --tail=30  # Check logs
kubectl describe pod <name> -n documentstream              # Detailed events
```

### 6. Load Testing

**Command:** `uv run locust -f locust/locustfile.py --host http://51.138.91.82`

**What it does:** Runs simulated users from your laptop hitting the cluster.
Web UI at http://localhost:8089.

**The upload task** (weight 3) drives the Redis pipeline — this is what triggers
KEDA scaling. The generate task (weight 1) runs synchronously in the gateway.

### 7. Resetting Demo Data

**Command:** `./infra/reset-demo.sh`

**What it does:** Truncates PostgreSQL, deletes Redis streams and status hashes,
restarts gateway to clear in-memory store.

### 8. Building and Deploying New Images

```bash
# Build for AMD64 (required — AKS is x86, Mac is ARM)
docker build --platform linux/amd64 -t acrdocumentstream.azurecr.io/gateway:latest -f src/gateway/Dockerfile .
docker push acrdocumentstream.azurecr.io/gateway:latest

# Tell K8s to pull the new image
kubectl rollout restart deployment/gateway -n documentstream
```

### 9. Cluster Lifecycle

```bash
# Start cluster (3-8 min, then re-fetch credentials)
az aks start -g DocumentStream -n DocumentStreamManagedCluster
az aks get-credentials -n DocumentStreamManagedCluster -g DocumentStream --overwrite-existing

# Stop cluster (saves money — only disk costs remain)
az aks stop -g DocumentStream -n DocumentStreamManagedCluster

# Flush DNS if needed after restart
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

---

## Data Flow

```
User/Locust
    │
    ▼
Ingress-nginx (51.138.91.82:80)
    │
    ▼
Gateway (FastAPI, 2 replicas)
    │
    ├── POST /api/documents → Redis stream "raw-docs" → return 202
    ├── POST /api/generate  → sync processing in gateway → return results
    ├── GET /api/documents  → read in-memory store → return list
    └── GET /health         → return {"status":"healthy","mode":"async"}

    Redis stream: raw-docs
    │
    ▼
Extract Worker (KEDA-scaled 1-8)
    │  PyMuPDF: extract text from PDF
    │
    ▼
    Redis stream: extracted
    │
    ▼
Classify Worker (KEDA-scaled 1-8)
    │  Rule-based: privacy level (Public/Confidential/Secret)
    │  Semantic: environmental impact + industries (sentence-transformers)
    │
    ▼
    Redis stream: classified
    │
    ▼
Store Worker (KEDA-scaled 1-8)
    │
    ▼
PostgreSQL (metadata + embeddings + classifications)
```

---

## K8s Resource Types You're Using

| Resource | Your files | Purpose |
|---|---|---|
| **Namespace** | `namespace.yaml` | Logical boundary: `documentstream` |
| **ConfigMap** | `configmap.yaml` | Env vars: REDIS_URL, DATABASE_URL, stream names |
| **Deployment** | `gateway-deployment.yaml`, `*-deployment.yaml` | Manages pod replicas and rollouts |
| **Service** | `gateway-service.yaml`, `postgres-deployment.yaml` (contains Service) | Stable DNS name + load balancing to pods |
| **Ingress** | `ingress.yaml` | Routes external HTTP → gateway Service |
| **PersistentVolumeClaim** | `postgres-deployment.yaml` (contains PVC) | 1Gi disk for PostgreSQL data |
| **Kustomization** | `kustomization.yaml` | Lists all resources for `kubectl apply -k` |
| **ScaledObject** (CRD) | `k8s/scaling/*.yaml` | KEDA autoscaling rules per worker |
| **PodChaos** (CRD) | `k8s/chaos/pod-kill.yaml` | Chaos Mesh pod kill experiment |
| **NetworkChaos** (CRD) | `k8s/chaos/network-delay.yaml` | Chaos Mesh network delay experiment |
| **StressChaos** (CRD) | `k8s/chaos/cpu-stress.yaml` | Chaos Mesh CPU stress experiment |

---

## Common Patterns

### "I changed a YAML file, how do I apply it?"
```bash
kubectl apply -k k8s/base/       # for base manifests
kubectl apply -f k8s/scaling/    # for scaling rules
kubectl apply -f k8s/chaos/      # for chaos experiments
```

### "Something is broken, how do I debug?"
```bash
kubectl get pods -n documentstream                    # What's the status?
kubectl logs deployment/<name> -n documentstream      # What's the error?
kubectl describe pod <name> -n documentstream         # Events (scheduling, pulling, OOM)
kubectl get events -n documentstream --sort-by=.metadata.creationTimestamp  # Recent events
```

### "I want to restart something cleanly"
```bash
kubectl rollout restart deployment/<name> -n documentstream
```

### "I want to see what K8s thinks the desired state is"
```bash
kubectl get deployment <name> -n documentstream -o yaml    # Full YAML from etcd
kubectl get deployment <name> -n documentstream -o jsonpath='{.spec.template.spec.containers[0].resources}'  # Specific field
```

### "I want to temporarily force a specific number of replicas"
```bash
kubectl scale deployment/<name> -n documentstream --replicas=3
```

### "I want to see what Helm installed"
```bash
helm list --all-namespaces
helm get values redis -n documentstream    # See config values for a release
```
