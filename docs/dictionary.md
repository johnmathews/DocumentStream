# DocumentStream Dictionary

Terms and concepts used in this project, explained for someone coming from Docker Compose and web app backgrounds.

---

## Kubernetes (K8s) Core Concepts

### Pod
The smallest thing K8s runs. Like a Docker container, but it can hold 1+ containers that share
networking and storage. In practice, most pods have exactly one container. Think of it as:
**Docker Compose service instance = K8s pod**.

### Deployment
Tells K8s "I want N copies of this pod running at all times." If a pod dies, the Deployment
creates a replacement. Like `deploy.replicas` in Docker Compose, but with self-healing built in.

### Service
A stable network address that routes traffic to pods. Pods come and go (scaling, crashes, updates),
but the Service address stays the same. Like Docker Compose service names (e.g., `redis:6379`),
but more explicit.

### Namespace
A way to group related resources. Like folders for your K8s objects. We use:
- `documentstream` — our application
- `monitoring` — Prometheus + Grafana
- `chaos-mesh` — chaos engineering tools
- `keda` — autoscaler

### Ingress
An HTTP router that sits in front of your services. Maps external URLs to internal services.
Like an nginx reverse proxy, but managed by K8s. Example: `/api/*` → gateway service,
`/grafana/*` → Grafana service.

### ConfigMap
Key-value config that gets injected into pods as environment variables or files. Like an `.env`
file, but managed by K8s and versioned.

### Secret
Same as ConfigMap but for sensitive data (passwords, API keys). Base64-encoded at rest.
Like Docker secrets. Referenced via `secretRef` in a Deployment's `envFrom` — if listed
after a ConfigMap, Secret values override ConfigMap values with the same key.

**Important:** Never commit Secrets to git. Create them via `kubectl create secret` or
apply a gitignored YAML file. GitHub Push Protection will block pushes containing keys.

### ServiceMonitor
A Custom Resource (CRD) used by the **kube-prometheus-stack** to tell Prometheus which
services to scrape. Pod annotations like `prometheus.io/scrape: "true"` do **not** work
with kube-prometheus-stack — you must create a ServiceMonitor instead.

Key gotcha: the ServiceMonitor needs a `release: prometheus` label (or whatever label
selector your Prometheus instance uses). Without it, Prometheus silently ignores it.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  labels:
    release: prometheus  # required!
spec:
  selector:
    matchLabels:
      app: gateway
  endpoints:
    - port: http         # must match a named port on the Service
      path: /metrics
```

---

## Kubernetes Operational Concepts

### Liveness Probe
A health check that K8s runs on your container. If it fails, K8s kills and restarts the pod.
Example: `GET /health` returns 200 → alive. Returns 500 → kill it, start a new one.

### Readiness Probe
Similar to liveness, but controls whether traffic is routed to the pod. A pod can be alive
but not ready (e.g., still loading data). K8s won't send it requests until it's ready.

### Rolling Update
How K8s deploys a new version: start new pods, wait until they're ready, then kill old pods.
At no point are zero pods running. This gives you **zero-downtime deployments**. If the new
pods fail their readiness probes, K8s stops the rollout automatically.

### `kubectl rollout restart`
Triggers a rolling restart of all pods in a deployment without changing any YAML. Needed
when a ConfigMap or Secret changes — K8s does **not** automatically restart pods when their
ConfigMap values change. You have to tell it to.

```bash
kubectl rollout restart deployment/gateway deployment/store-worker
kubectl rollout status deployment/gateway   # watch progress
kubectl rollout history deployment/gateway  # see past revisions
```

### Rollback
Undo a deployment: `kubectl rollout undo deployment/my-app`. K8s keeps the previous pod
spec and can revert to it instantly.

### Resource Requests and Limits
- **Request:** "This container needs at least 256MB RAM and 0.25 CPU to run."
  K8s uses this to decide which node to place the pod on.
- **Limit:** "This container must never use more than 512MB RAM."
  If it exceeds the memory limit, K8s kills it (OOMKilled).

### Pod READY Column
When you run `kubectl get pods`, the READY column shows `1/1` or `2/2`. This is
`READY_CONTAINERS/TOTAL_CONTAINERS` in that pod. A pod with an app + sidecar container
would show `2/2` when both are ready, or `1/2` if one is still starting.

### `kubectl get all` Limitations
Despite the name, `kubectl get all` only returns a hardcoded subset: Pods, Services,
Deployments, ReplicaSets, StatefulSets, DaemonSets, Jobs, CronJobs. It does **not**
include HPAs, ConfigMaps, Secrets, Ingresses, PVCs, ServiceMonitors, ScaledObjects, etc.

To see everything in a namespace, be explicit:
```bash
kubectl get deploy,svc,hpa,ingress,configmap,scaledobject -n documentstream
```

### Default Namespace
Set a default namespace to avoid typing `-n documentstream` on every command:
```bash
kubectl config set-context --current --namespace=documentstream
kubectl config view --minify | grep namespace  # verify
```

### Horizontal Pod Autoscaler (HPA)
Watches a metric (CPU, memory, custom) and adjusts the number of pod replicas. Example:
"If average CPU > 70%, add more pods. If < 30%, remove pods." Like auto-scaling in cloud
VMs, but for containers and much faster (seconds, not minutes).

---

## Tools & Platforms

### KEDA (Kubernetes Event-Driven Autoscaling)
An extension to K8s that adds smarter autoscaling beyond just CPU/memory. While the built-in
HPA can only scale on CPU and memory, KEDA can scale based on **any event source**:

- **Redis queue depth** — "There are 50 documents waiting in the queue, scale up to 10 workers"
- **Kafka consumer lag** — "Messages are piling up, add more consumers"
- **Cron schedules** — "Scale to 5 pods every weekday at 9am"
- **HTTP request rate** — "Traffic is spiking, add more API pods"

**Why we use it:** Our pipeline uses Redis queues between stages. When documents pile up in
a queue, KEDA automatically adds more worker pods to process them faster. When the queue
empties, it scales back down to 1 (or even 0) pods. This is the core demo — you can *see*
pods appear and disappear in response to workload.

**How it works:**
1. You install KEDA in your cluster (one Helm chart)
2. You create a `ScaledObject` YAML that says: "Watch this Redis list. If it has more than
   5 items per worker, add more workers. Maximum 10 workers."
3. KEDA checks the queue every 30 seconds and adjusts the pod count

**Docker Compose equivalent:** There isn't one. Docker Compose has no autoscaling. This is
one of the key reasons to use K8s over Compose in production.

### Chaos Mesh
A tool that intentionally breaks things in your K8s cluster so you can prove the system
recovers. You define "experiments" like:

- "Kill 2 random pods from the classify-worker deployment"
- "Add 500ms network latency to the database connection"
- "Consume 90% of CPU on one node"

It has a web dashboard where you can start/stop experiments during a live demo.
The point is to show that K8s **self-heals** — when pods die, they come back automatically.

### Helm
A package manager for K8s. Like `apt install` or `brew install`, but for K8s applications.
Instead of writing 15 YAML files to install Prometheus + Grafana, you run:
`helm install monitoring prometheus-community/kube-prometheus-stack`
Helm charts are configurable via a `values.yaml` file.

### Kustomize
A tool for managing K8s YAML without templates. You write a "base" set of manifests, then
create "overlays" that patch specific values for different environments (dev, staging, prod).
Built into kubectl: `kubectl apply -k ./k8s/base/`.

### Prometheus
A monitoring system that scrapes metrics from your applications and stores them as time series.
Your FastAPI app exposes metrics at `/metrics` (request count, latency, error rate). Prometheus
collects them every 15 seconds. Grafana reads from Prometheus to draw dashboards.

### Grafana
A dashboarding tool. Connects to Prometheus (and other data sources) and draws real-time
graphs. We use it to show: pod count, CPU/memory, request rate, queue depth, error rate.
The live updating graphs are the centerpiece of the demo.

### Locust
A Python load testing tool with a web UI. You write test scenarios in Python (e.g., "upload
a random document every 0.5 seconds"), then control the number of simulated users via
sliders in the browser. We use it to generate traffic and show KEDA scaling in action.

---

## Azure Services

### AKS (Azure Kubernetes Service)
Managed K8s on Azure. Azure handles the control plane (the K8s "brain"). You just pay for
the worker nodes (VMs that run your pods). Free tier available for the control plane.

### ACR (Azure Container Registry)
Where your Docker images live. Like Docker Hub, but private and integrated with AKS.
When you push a new image, AKS can pull it automatically.

### Azure Database for PostgreSQL — Flexible Server
Managed PostgreSQL. Azure handles backups, patching, high availability. Can be stopped when
not in use (you only pay for disk storage while stopped).

### Azure Blob Storage
Object storage for files (like S3). We store the original PDF files here. Extremely cheap.
PDFs are organized as `{doc_id}/{loan_id}/{doc_type}.pdf` in a container called `documents`.

### Azurite
Microsoft's local emulator for Azure Storage. Runs as a Docker container and provides the
same API as real Azure Blob Storage. Used in `docker-compose.yml` for local dev so you don't
need a real Azure account to test blob uploads.

### Building and Pushing Images to ACR
`docker build` only creates the image **locally**. To deploy to AKS, you must also push:

```bash
# Option 1: Build locally + push (need --platform for ARM Mac → AMD64 cluster)
docker build --platform linux/amd64 -t acrdocumentstream.azurecr.io/gateway:latest -f src/gateway/Dockerfile .
az acr login --name acrdocumentstream
docker push acrdocumentstream.azurecr.io/gateway:latest

# Option 2: Build remotely on ACR (no platform flag needed, builds on Linux)
az acr build --registry acrdocumentstream --image gateway:latest --file src/gateway/Dockerfile .
```

After pushing, `kubectl rollout restart deployment/gateway` tells K8s to pull the new image.

---

## Pipeline Concepts

### Queue-Based Processing
Instead of processing documents synchronously (upload → wait → response), we put them on a
queue and return immediately. Worker pods pick items off the queue and process them
independently. Benefits:
- **Resilience:** If a worker crashes, the message stays in the queue and another worker picks it up
- **Scaling:** Add more workers when the queue is long, remove them when it's short
- **Decoupling:** Each stage can be updated/scaled/failed independently

### Redis as a Queue
Redis is best known as a key-value store, but it has several built-in data structures.
Two of them can work as message queues:

**Redis Lists (simple queue):** `LPUSH` adds to one end, `RPOP` takes from the other.
Problem: once you pop a message, it's gone. If your worker crashes mid-processing,
the message is lost forever.

**Redis Streams (what we use):** An append-only log where each message has an ID and
key-value fields. The critical feature is **consumer groups** — multiple workers read
from the same stream, Redis tracks which messages each worker received, and workers
must explicitly acknowledge (`XACK`) a message when done. If a worker crashes before
acknowledging, the message stays unacknowledged and another worker can claim it.

| | Queue (List) | Stream |
|---|---|---|
| Message persistence | Gone after pop | Stays in the log |
| Crash recovery | Message lost | Unacked message re-delivered |
| Multiple consumers | One message → one consumer | Consumer groups divide work |
| History | None | Can replay old messages |

**Why this matters for the demo:** When Chaos Mesh kills a classify worker pod mid-processing,
the message stays unacknowledged in Redis. K8s restarts the pod, it picks up the unfinished
message, and the document gets processed. Zero data loss. That's a key interview talking point.

### Streams vs Pub/Sub
Redis also has Pub/Sub — a broadcast system where publishers send messages to channels and
all current subscribers receive them. The critical difference:

- **Pub/Sub:** Fire and forget. If nobody is subscribed, the message is gone forever. No
  storage, no history, no acknowledgment. Like a radio broadcast — miss it and it's gone.
- **Streams:** Durable log. Messages persist whether or not anyone is reading. Consumers
  track their position, acknowledge processed messages, and can replay from any point.
  Like an email inbox — messages wait for you.

For a processing pipeline, Pub/Sub would lose documents whenever a worker pod restarts.
Streams guarantee every document gets processed.

---

## Azure CLI Commands

### Check What's Running
```bash
# List all resource groups
az group list -o table

# List all resources in a resource group
az resource list -g DocumentStream -o table

# List resources in the AKS-managed resource group (VMs, disks, load balancers)
az resource list -g MC_DocumentStream_DocumentStreamManagedCluster_westeurope -o table
```

### AKS Cluster (Start / Stop)
The AKS node VMs are the biggest cost. Stopping the cluster deallocates the VMs and stops
compute billing. Storage (disks, IPs) still costs a small amount while stopped.

```bash
# Check if the cluster is running
az aks show -g DocumentStream -n DocumentStreamManagedCluster --query "powerState" -o tsv

# Stop the cluster (saves ~$5/day in compute)
az aks stop -g DocumentStream -n DocumentStreamManagedCluster

# Start the cluster (takes 3-5 minutes)
az aks start -g DocumentStream -n DocumentStreamManagedCluster

# Get kubectl credentials after starting
az aks get-credentials -g DocumentStream -n DocumentStreamManagedCluster --overwrite-existing
```

### PostgreSQL Flexible Server (Start / Stop)
```bash
# List servers
az postgres flexible-server list -o table

# Check status
az postgres flexible-server show -g DocumentStream -n <server-name> --query "state" -o tsv

# Stop (only pays for storage while stopped)
az postgres flexible-server stop -g DocumentStream -n <server-name>

# Start
az postgres flexible-server start -g DocumentStream -n <server-name>
```

### Check Costs (az rest)
The `az costmanagement query` CLI command was removed by Microsoft in 2023. Use `az rest`
to call the Cost Management API directly:

```bash
# Cost breakdown by service, per day, this month
SUB_ID=$(az account show --query id -o tsv) && az rest --method post \
  --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/DocumentStream/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
  --body '{
    "type": "Usage",
    "dataset": {
      "aggregation": {
        "totalCost": { "name": "PreTaxCost", "function": "Sum" }
      },
      "granularity": "Daily",
      "grouping": [{ "name": "ServiceName", "type": "Dimension" }]
    },
    "timeframe": "MonthToDate"
  }'
```

Other useful groupings (replace `ServiceName` above):
- `ResourceType` — group by resource type (VMs, disks, LB, etc.)
- `ResourceId` — group by individual resource
- `MeterCategory` — group by billing meter category

Valid timeframes: `MonthToDate`, `WeekToDate`, `TheLastMonth`, `BillingMonthToDate`.

**Note:** The Cost Management API and `az consumption usage list` both return empty results
for free credit / sponsorship subscriptions. For these subscription types, check costs in the
Azure Portal: **Cost Management + Billing** > **Azure credits** or **Subscriptions** >
your subscription > **Cost analysis**.

### Cost Awareness

Our setup: 2x Standard_B2s_v2 nodes, Free tier AKS control plane, Standard Load Balancer.

| Resource | $/hour | $/day (running) | $/day (stopped) |
|---|---|---|---|
| 2x Standard_B2s_v2 (2 vCPU, 8 GiB each) | $0.192 | $4.61 | $0 |
| 2x OS Disk (128 GiB Standard SSD) | — | $0.64 | $0.64 |
| Standard Load Balancer (first 5 rules) | $0.025 | $0.60 | $0.60 |
| Public IP | $0.004 | $0.10 | $0.10 |
| ACR (Basic tier) | — | $0.17 | $0.17 |
| Blob Storage | — | Pennies | Pennies |
| **Total** | | **~$6.12** | **~$1.51** |

If PostgreSQL Flexible Server is also running (Burstable B1ms): add ~$1.20/day.

**Rule of thumb:** Stop AKS and PostgreSQL when not actively working. Start them 5-10 minutes
before you need them. The cluster takes 3-5 minutes to start.

---

## Semantic Classification Concepts

### Vector Embedding
A way to convert text into a list of numbers (a vector) that captures its meaning. Two pieces
of text about similar topics will have similar vectors, even if they use completely different
words. For example, "the site was a textile dyeing factory" and "ground contamination from
industrial chemical processing" would have similar embeddings because they're about the same
concept — industrial pollution.

We use the `all-MiniLM-L6-v2` model (sentence-transformers) which produces 384-dimensional
vectors. "384-dimensional" means each text becomes a list of 384 numbers.

### Cosine Similarity
A way to measure how similar two vectors are. Returns a value between -1 and 1:
- 1.0 = identical meaning
- 0.5+ = related topics
- ~0 = unrelated
- Negative = opposite meaning

We compare each document's embedding to pre-computed "anchor" embeddings that describe each
classification category. The category with the highest similarity wins.

### Zero-Shot Classification
Classifying text into categories without training on labeled examples. Instead of showing the
model 1,000 labeled documents and training a classifier, we:
1. Write a descriptive paragraph for each category (the "anchor")
2. Embed both the anchor and the document
3. Compare similarity

This works immediately with no training data — hence "zero-shot." The trade-off: less accurate
than a trained classifier, but deployable in minutes instead of days.

### pgvector
A PostgreSQL extension that adds a `vector` column type and similarity search operations.
You store embeddings alongside regular data (loan_id, classification, dates) in the same
database. Then you can run queries like:

```sql
SELECT * FROM documents
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

The `<=>` operator computes cosine distance. This finds the 10 documents most semantically
similar to your query — even if they share no keywords.

### Azure AI Search (interview talking point)
Microsoft's managed search service with built-in vector search. In production at a bank,
you'd likely use this instead of pgvector because it adds:
- Hybrid search (vector + keyword in one query)
- Integrated embedding via Azure OpenAI
- Semantic re-ranking with a cross-encoder model
- Enterprise compliance (SOC 2, GDPR, data residency)

The interview answer: "I used pgvector to demonstrate the fundamentals. In production, I'd
recommend Azure AI Search because it meets regulatory requirements and integrates with
Azure OpenAI for embedding generation."

---

*This dictionary will be updated as new concepts are introduced during development.*
