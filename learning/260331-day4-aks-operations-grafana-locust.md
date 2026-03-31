# Learning Journal: AKS Operations, Grafana, and Locust Load Testing

**Date:** 2026-03-31 (Day 4, morning session)
**Goal:** Run KEDA autoscaling + Grafana monitoring + Locust load test on the live cluster, fix production issues as they arise

---

## What We Accomplished

1. Started AKS cluster from stopped state, reconnected kubectl
2. Explored Azure Portal -- resource groups, node pools, cluster properties
3. Applied KEDA ScaledObjects (`kubectl apply -f k8s/scaling/`)
4. Imported Grafana dashboard via port-forward
5. Ran Locust load test (5 users) against the live cluster
6. Observed KEDA scaling classify-workers from 1 to 8 pods
7. Fixed gateway OOM by bumping memory 256Mi to 768Mi
8. Made PostgreSQL persistent (emptyDir to PVC with subPath)
9. Created reset-demo.sh script
10. Fixed various deployment issues along the way

---

## Commands Reference (new ones learned today)

### Applying Manifests from a Directory

```bash
# Apply all YAML files in a directory at once
kubectl apply -f k8s/scaling/
```

This finds every `.yaml` and `.json` file in the directory and applies each one. The
trailing slash is important -- it tells kubectl you mean a directory, not a single file.
`apply` is **declarative and idempotent**: creates resources if they don't exist, updates
them if they do. Compare with `kubectl create` which fails if the resource already exists.

### Inspecting Cluster State

```bash
# Get everything in a namespace (pods, services, deployments, replicasets)
kubectl get all -n documentstream

# Check KEDA autoscaling state
kubectl get scaledobjects -n documentstream
kubectl get hpa -n documentstream

# Show labels on resources (labels are how K8s matches things together)
kubectl get pods -n documentstream --show-labels

# Filter resources by label
kubectl get pods -n documentstream -l app=postgres
```

The `-l` flag is a **label selector**. Labels are key-value pairs on every K8s resource.
Services use them to find their Pods, Deployments use them to find their ReplicaSets, and
you can use them to filter `kubectl get` results. Think of them as tags.

### Accessing In-Cluster Services

```bash
# Port-forward: tunnel from your laptop through the API server to a pod
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
```

Format is `local-port:remote-port`. After running this, `http://localhost:3000` on your
laptop hits port 80 on the Grafana Service inside the cluster. The tunnel stays open until
you Ctrl+C.

This is necessary because Grafana has a **ClusterIP** service -- only reachable from inside
the cluster. We intentionally don't expose monitoring services to the public internet. Port-
forwarding gives you secure access without creating an Ingress.

```bash
# Get Grafana admin password (stored as a K8s Secret, base64-encoded)
kubectl get secret --namespace monitoring prometheus-grafana \
    -o jsonpath="{.data.admin-password}" | base64 -d; echo
```

K8s Secrets store values as base64. The `jsonpath` flag extracts a specific field, and
`base64 -d` decodes it. The `; echo` just adds a newline so your terminal prompt isn't
jammed against the password.

### Working Inside Pods

```bash
# Copy a local file into a running pod
kubectl cp src/worker/schema.sql documentstream/<pod-name>:/tmp/schema.sql

# Run a command inside a running pod
kubectl exec -n documentstream deployment/postgres -- \
    psql -U documentstream -d documentstream -f /tmp/schema.sql
```

`kubectl cp` is like `scp` but for pods. Note the format: `namespace/pod-name:path`.

`kubectl exec` runs a command inside an existing pod. The `--` separates kubectl flags from
the command to run inside the container. When you target a `deployment/` instead of a
specific pod name, kubectl picks one of the deployment's pods automatically.

### Manual Scaling and Cleanup

```bash
# Scale a deployment to zero (kills all its pods)
kubectl scale deployment/postgres -n documentstream --replicas=0

# Delete pods matching a label (new pods will be recreated by the Deployment)
kubectl delete pod -n documentstream -l app=postgres
```

Scaling to 0 is useful when you need to release resources (like a PVC that only allows one
attachment). Deleting pods by label is a quick way to force restarts -- the Deployment
controller notices "I should have N pods but I have 0" and creates fresh ones.

### Running the Load Test

```bash
# Start Locust against the live cluster
uv run locust -f locust/locustfile.py --host http://51.138.91.82
```

This starts a web UI on http://localhost:8089 where you configure the number of simulated
users and ramp-up rate. Locust is a Python load-testing tool -- the locustfile defines
tasks (upload PDF, generate scenario, list docs, health check) with weights that control
how often each runs.

---

## Questions & Answers

### Azure Portal

**Q: What are the 4 resource groups I see (DocumentStream, MC_..., NetworkWatcherRG, defaultresourcegroup-weu)?**

A: Only **DocumentStream** is yours. The rest are auto-created by Azure:

| Resource Group | Purpose |
|---|---|
| `DocumentStream` | Your resource group -- contains AKS cluster, ACR, and anything you created |
| `MC_DocumentStream_...` | Auto-created by AKS. Contains the underlying VMs, disks, load balancers, and NICs that back your cluster. When you delete DocumentStream, this cleans up automatically |
| `NetworkWatcherRG` | Azure networking diagnostics (auto-created when any VNet is created) |
| `defaultresourcegroup-weu` | Azure Monitor defaults for West Europe region |

You should never manually edit resources in `MC_*` -- AKS manages those. If you delete the
AKS cluster's resource group, the `MC_*` group is automatically garbage-collected.

**Q: What are MSCI and MSProm prefixed resources?**

A: Auto-created by Azure Monitor when you enable monitoring on the cluster:

- **MSCI** = Microsoft Standardized Container Insights -- a data collection rule that defines
  what metrics and logs to scrape from your containers.
- **MSProm** = Microsoft managed Prometheus -- a data collection endpoint that receives
  Prometheus-format metrics.

These are Azure's managed monitoring layer, completely separate from the Prometheus + Grafana
you installed via Helm inside the cluster. Azure's version feeds the Azure Portal monitoring
UI; yours feeds your custom Grafana dashboard. Both coexist independently.

**Q: How do I see how many nodes are in a node pool?**

A: Two ways:
- **Azure Portal:** Kubernetes service, then Node pools, then click the pool. Shows target
  count and ready count.
- **CLI:** `kubectl get nodes` -- lists all nodes with their status, roles, and age.

---

### K8s Architecture

**Q: What is the hierarchy of Node, Pod, and Container?**

A:
```
Node (a VM)
  └── Pod (scheduling unit -- one or more tightly coupled containers)
        └── Container (a single running Docker image)
```

- A **Node** is a virtual machine in your cluster. You have 2 Standard_B2s_v2 nodes.
- A **Pod** is the smallest deployable unit. Containers in the same Pod share the same
  network (they can reach each other on localhost) and storage volumes. Most Pods have
  exactly one container.
- A **Container** is a single running instance of a Docker image.

You almost never create Pods directly. You create **Deployments**, which manage
**ReplicaSets**, which manage **Pods**. This chain gives you rolling updates, rollback
history, and replica management.

**Q: What does a Deployment do vs a ReplicaSet?**

A: They have different jobs:

- **Deployment** -- manages the rollout lifecycle. When you change the container image, it
  creates a *new* ReplicaSet with the new spec and gradually scales it up while scaling the
  old one down (rolling update). It also keeps rollout history so you can `kubectl rollout
  undo`.

- **ReplicaSet** -- simpler. Its only job is counting: "I'm supposed to have N pods. Do I?
  If not, create or delete pods to match." That's it.

You interact with Deployments. ReplicaSets are an implementation detail -- you'll see them
in `kubectl get all` but you almost never touch them directly.

**Q: What is the Pod spec and where is it defined?**

A: The Pod spec lives inside the Deployment YAML, under `spec.template.spec`. A Deployment
YAML actually bundles two separate things:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
spec:
  replicas: 2                    # <-- Deployment-level config
  strategy:
    type: RollingUpdate          # <-- Deployment-level config
  template:                      # <-- Everything below here is the Pod spec
    metadata:
      labels:
        app: gateway
    spec:
      containers:
        - name: gateway
          image: acrdocumentstream.azurecr.io/gateway:latest
          resources:
            requests:
              memory: "512Mi"
            limits:
              memory: "768Mi"
          env:
            - name: REDIS_URL
              value: "redis://redis-master:6379"
```

The Pod spec contains: container image, command, resource requests/limits, volume mounts,
environment variables, and restart policy. The Deployment wraps it with replica count,
rollout strategy, and selector labels.

**Q: Is a Deployment YAML file the same as a Deployment process?**

A: No. Important distinction:

- The **YAML file** is a *declaration* -- it says "this is the desired state I want."
- The **Deployment controller** is a process running inside K8s (in the control plane) that
  *reads* that declaration and makes it happen. It continuously watches: "does reality match
  the declaration? If not, fix it."

When you run `kubectl apply -f deployment.yaml`, kubectl sends the YAML to the API server
as an HTTP request. The API server stores it in etcd. The Deployment controller (which is
always watching etcd for changes) notices and reconciles the actual cluster state with the
declared state.

**Q: Who handles what in K8s?**

A:

| Concern | Who handles it |
|---|---|
| How many pods should exist | Deployment (replicas field) + KEDA/HPA (autoscaling) |
| Restarting crashed containers | kubelet (per-node agent) |
| Rolling updates / rollbacks | Deployment controller |
| CPU, memory, volumes | Pod spec |
| Stable network endpoint | Service |
| External HTTP routing | Ingress (+ ingress-nginx controller) |
| Node-level container management | kubelet + containerd |
| Scheduling pods to nodes | kube-scheduler |

**Q: What is a control plane?**

A: The "brain" of the cluster -- a collection of services that work together:

| Component | Role |
|---|---|
| **API server** | Front door for all commands (kubectl, controllers, everything talks to this) |
| **etcd** | Database storing all cluster state (every YAML you've ever applied lives here) |
| **Scheduler** | Watches for unscheduled pods, assigns them to nodes based on resource availability |
| **Controller manager** | Runs all built-in controllers (Deployment controller, ReplicaSet controller, Node controller, etc.) |

On AKS, Azure manages the control plane on hidden VMs you don't pay for. Your 2 nodes only
run kubelet + your workloads. This is why AKS is called a "managed" Kubernetes service --
you manage the workloads, Azure manages the control plane.

**Q: What is a kubelet?**

A: The agent running on **every** worker node. It's the bridge between the control plane and
the actual containers.

When the scheduler says "put this Pod on Node 2," the kubelet on Node 2:
1. Tells containerd (the container runtime) to pull the Docker image
2. Creates and starts the container
3. Runs liveness/readiness probes to check health
4. Restarts crashed containers (per the restartPolicy)
5. Mounts volumes
6. Reports node status back to the control plane

If a container crashes, the kubelet restarts it with exponential backoff (immediately, then
10s, 20s, 40s, ... up to 5 minutes). You see this in `kubectl describe pod` as the restart
count and "Back-off restarting failed container" events.

**Q: What is a CRD?**

A: **Custom Resource Definition** -- a way to extend K8s with new resource types that don't
exist out of the box.

Built-in types: Pod, Deployment, Service, ConfigMap, etc.
Custom types added by operators:
- KEDA registers `ScaledObject` and `TriggerAuthentication`
- Chaos Mesh registers `PodChaos`, `NetworkChaos`, `StressChaos`
- Prometheus registers `ServiceMonitor`, `PrometheusRule`

The pattern is:
1. Install the operator via Helm (which registers the CRDs)
2. Create instances of those CRDs (`kubectl apply -f my-scaledobject.yaml`)
3. The operator watches for its CRDs and acts on them

Without the operator installed, `kubectl apply` would reject the YAML with
`error: unable to recognize: no matches for kind "ScaledObject"`.

---

### kubectl Internals

**Q: What does `kubectl apply -f <directory>/` do?**

A: Finds all `.yaml` and `.json` files in the directory and applies each one. This is how
we applied all three ScaledObjects at once with `kubectl apply -f k8s/scaling/`.

`apply` is declarative and idempotent:
- Resource doesn't exist? Create it.
- Resource exists but spec changed? Update it.
- Resource exists and spec is identical? No-op.

Compare with `kubectl create` which errors if the resource already exists. In practice,
always use `apply`.

**Q: Does kubectl copy files to the cluster?**

A: No. This is a common misconception. Here's what actually happens:

1. kubectl reads the YAML file on your laptop
2. Sends it as an HTTP POST/PUT request to the API server (over HTTPS)
3. API server validates the YAML against the resource schema
4. API server stores the resource definition in etcd
5. The relevant controller (watching etcd) notices the new/changed resource and acts

Nothing is "copied" as a file. The API server is a REST API, and kubectl is an HTTP client.
You could do the same thing with `curl` if you wanted to (but you wouldn't want to -- the
auth headers are painful).

**Q: What does the -l flag do?**

A: Label selector. Filters resources by their labels.

```bash
# Show only pods with the label app=postgres
kubectl get pods -n documentstream -l app=postgres

# Show only pods with TWO matching labels (AND logic)
kubectl get pods -l app=worker,stage=classify

# Show labels on all pods
kubectl get pods --show-labels
```

Labels are the glue of K8s. Services find their backend Pods via label selectors. KEDA
ScaledObjects target Deployments by name but Deployments find their Pods by label. When
something isn't connecting, check that labels match.

---

### Grafana and Port-Forwarding

**Q: Why is port-forwarding necessary for Grafana?**

A: Grafana has a **ClusterIP** service, meaning it's only accessible from inside the
cluster. There are three K8s Service types:

| Service Type | Accessible From | Use Case |
|---|---|---|
| ClusterIP | Inside cluster only | Internal services (databases, monitoring) |
| NodePort | Cluster + specific port on every node | Testing, rarely used in production |
| LoadBalancer | Public internet via cloud load balancer | Public-facing services (your gateway) |

Grafana is ClusterIP on purpose -- you don't expose monitoring dashboards to the internet.
`kubectl port-forward` creates a temporary encrypted tunnel:

```
Your laptop:3000 --> kubectl --> K8s API server --> Grafana pod:80
```

The tunnel runs through the API server (which you're already authenticated to), so it's
secure without any extra configuration. It stays open until you Ctrl+C.

---

### Locust

**Q: How does Locust work?**

A: Locust is a Python load-testing tool that runs on **your laptop** (not in the cluster).

1. You start it: `uv run locust -f locust/locustfile.py --host http://51.138.91.82`
2. It opens a web UI at http://localhost:8089
3. You configure: number of simulated users (e.g., 5) and ramp-up rate (users per second)
4. Each simulated user runs tasks from the locustfile in a loop with random waits
5. Tasks have **weights** determining frequency (weight 5 = runs 5x as often as weight 1)

For our test, the locustfile defines 4 tasks:
- `list_documents` (weight 5) -- most common, lightweight GET
- `upload_pdf` (weight 3) -- uploads a PDF, triggers the pipeline
- `health_check` (weight 2) -- quick liveness check
- `generate_scenario` (weight 1) -- heaviest endpoint, generates 5 documents

With 5 users running these tasks, we generated enough Redis queue pressure for KEDA to
scale classify-workers from 1 to 8 replicas within a few minutes.

---

### Storage and Persistence

**Q: Does generating documents cost storage money?**

A: Negligible at demo scale. Here's where data lives:

| Data | Where Stored | Cost |
|---|---|---|
| PostgreSQL database | PersistentVolumeClaim (Azure managed disk) | Included in VM disk cost |
| Redis streams | Node-local memory | Included in VM memory |
| Azure Blob Storage | Not configured (no BLOB_CONNECTION_STRING) | Zero |
| Generated PDFs | In-memory during processing, metadata in PostgreSQL | Minimal |

100 documents is roughly 500KB of metadata. The only real cost is the running VMs
(~$6/day for 2x B2s_v2 nodes).

**Q: Why make storage persistent?**

A: `emptyDir` volumes are tied to the **pod's lifecycle**. When a pod restarts (OOM, node
failure, deployment rollout), the emptyDir is deleted. All data gone.

A **PersistentVolumeClaim** (PVC) survives pod restarts. The data lives on an Azure managed
disk that persists independently of any pod. When a new pod starts, it mounts the same disk
and finds its data intact.

For databases, this is critical:
- Without PVC: every pod restart = empty database, need to re-run schema.sql, all demo
  data lost
- With PVC: pod restarts and reconnects to existing data seamlessly

---

## Problems Encountered and How They Were Fixed

### 1. Gateway 502 on /api/generate

**Symptom:** `curl -X POST http://51.138.91.82/api/generate` returned 502 Bad Gateway.

**Investigation:** Checked gateway logs with `kubectl logs deployment/gateway -n documentstream`.
Found OOMKilled events. The `/api/generate` endpoint loads the sentence-transformers model
synchronously into memory, which needs roughly 400MB.

**Root cause:** Gateway memory limit was set to 256Mi. The endpoint needs ~400MB just for
the model, plus overhead for the Python runtime and request processing.

**Fix:** Bumped gateway resources to requests 512Mi / limits 768Mi in the deployment YAML.

**Lesson:** Resource limits must account for peak usage, not just idle state. The gateway
idles at ~100MB but spikes to ~500MB when the model loads. Setting limits too low doesn't
save resources -- it just causes OOMKill restarts that waste more resources than generous
limits would.

### 2. KEDA Scaled to 8 but Most Pods Pending

**Symptom:** KEDA scaled classify-worker to 8 replicas, but `kubectl get pods` showed 6 of
them stuck in `Pending` state.

**Investigation:** `kubectl describe pod <pending-pod>` showed the event:
`0/2 nodes are available: insufficient memory`.

**Root cause:** Two-node cluster (2x B2s_v2, each with 2GB RAM) doesn't have enough
resources for 8 classify-workers (each requesting ~500Mi). The scheduler can't place them
anywhere.

**Key insight -- two-level scaling:**
- **KEDA** scales **pods** (horizontal pod autoscaler based on queue depth)
- **Cluster Autoscaler** scales **nodes** (adds VMs when pods are Pending)

We have KEDA but not Cluster Autoscaler. So KEDA correctly decided "we need 8 workers" but
there were only enough resources for 2. In production, you'd enable Cluster Autoscaler,
which watches for Pending pods and automatically adds nodes to the node pool.

**Lesson:** KEDA and Cluster Autoscaler work together: KEDA creates demand (more pods),
Cluster Autoscaler supplies capacity (more nodes). Without both, you hit a ceiling.

### 3. PostgreSQL PVC initdb Error

**Symptom:** PostgreSQL pod crash-looped with:
```
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
```

**Root cause:** When you mount a PVC at a path, the underlying Azure managed disk has a
filesystem with a `lost+found` directory. PostgreSQL's `initdb` refuses to initialize into
a non-empty directory as a safety measure.

**Fix:** Added `subPath: pgdata` to the volumeMount:

```yaml
volumeMounts:
  - name: postgres-data
    mountPath: /var/lib/postgresql/data
    subPath: pgdata
```

`subPath` tells K8s to use a **subdirectory** inside the PVC instead of the PVC root. So
the mount effectively becomes `<pvc-root>/pgdata/` which starts empty. The `lost+found`
directory is at the PVC root level and doesn't interfere.

**Lesson:** This is such a common gotcha with PostgreSQL on K8s that most Helm charts
include `subPath` by default. When deploying PostgreSQL manually, always use subPath.

### 4. Old ReplicaSet Blocking New Postgres Pod

**Symptom:** After fixing the subPath issue and redeploying, the new postgres pod was stuck
at `ContainerCreating` while the old pod from the previous ReplicaSet was still crash-
looping.

**Root cause:** The PVC was created with `ReadWriteOnce` access mode, meaning it can only
be attached to **one node** at a time. The old ReplicaSet still had a pod trying to claim
the volume, blocking the new pod from mounting it.

**Fix:** Scaled the deployment to 0, then back to 1:

```bash
kubectl scale deployment/postgres -n documentstream --replicas=0
# Wait for all pods to terminate
kubectl scale deployment/postgres -n documentstream --replicas=1
```

Scaling to 0 kills all pods from all ReplicaSets, releasing the PVC. Then scaling to 1
lets the new ReplicaSet create a fresh pod that can mount the volume.

**Lesson:** `ReadWriteOnce` means one-node-at-a-time, which effectively means one-pod-at-
a-time for most deployments. When doing a rolling update on a StatefulSet or single-replica
Deployment with a PVC, you may need to go through a 0-replica step. In production, you'd
use `strategy: Recreate` instead of `RollingUpdate` for Deployments with ReadWriteOnce PVCs.

### 5. Redis FLUSHDB Not Available

**Symptom:** Running `FLUSHDB` via redis-cli returned:
```
ERR unknown command 'FLUSHDB'
```

**Root cause:** Redis 8.6 may have restricted or renamed the flush commands, or the
deployment was configured with command renaming for safety.

**Fix:** Used targeted deletion instead of a blanket flush:

```bash
# Delete specific streams
redis-cli DEL raw-docs extracted classified

# Delete status hashes by pattern
redis-cli KEYS "doc:*" | xargs redis-cli DEL
```

Updated `reset-demo.sh` to use this approach. More surgical than FLUSHDB anyway -- it only
removes DocumentStream data and leaves any other Redis data untouched.

### 6. kubectl exec stdin pipe not working for schema.sql

**Symptom:** Piping schema.sql via stdin didn't work:
```bash
kubectl exec -n documentstream deployment/postgres -- psql -U documentstream -d documentstream -f /dev/stdin < src/worker/schema.sql
```
The command produced no output and the tables were not created.

**Fix:** Two-step approach -- copy the file in, then execute it:

```bash
# Step 1: Copy the file into the pod
kubectl cp src/worker/schema.sql documentstream/<pod-name>:/tmp/schema.sql

# Step 2: Execute it inside the pod
kubectl exec -n documentstream deployment/postgres -- \
    psql -U documentstream -d documentstream -f /tmp/schema.sql
```

**Lesson:** Stdin piping with `kubectl exec` can be unreliable, especially with complex
commands. `kubectl cp` + `kubectl exec` is more predictable. The two-step pattern is
common for database migrations on K8s.

---

## Key Concepts Solidified Today

### The Apply Loop (K8s Reconciliation)

Everything in K8s follows the same pattern:

1. You **declare** desired state (YAML)
2. You **submit** it (`kubectl apply`)
3. A **controller** continuously compares desired state vs actual state
4. If they differ, the controller takes action to converge

This is why K8s is called "declarative" -- you don't say "start 3 pods," you say "there
should be 3 pods." If one crashes, the controller notices the drift and creates a
replacement. This is also why `kubectl apply` is idempotent -- applying the same YAML
twice is fine because the controller says "desired = actual, nothing to do."

### Labels Are the Glue

Almost every relationship in K8s is based on label selectors, not names:

- **Service** finds its Pods via `selector: {app: gateway}`
- **Deployment** manages Pods via `matchLabels: {app: gateway}`
- **KEDA ScaledObject** targets a Deployment by name, but the Deployment finds its Pods by label
- **kubectl -l** filters resources by label

When something isn't connecting (Service can't find Pod, HPA not targeting the right
Deployment), check that labels match between the selector and the resource.

### Resource Requests vs Limits

```yaml
resources:
  requests:
    memory: "512Mi"    # Scheduler uses this to find a node with enough room
    cpu: "100m"
  limits:
    memory: "768Mi"    # Hard ceiling -- container is OOMKilled if it exceeds this
    cpu: "500m"
```

- **Requests** = what the scheduler guarantees. "This pod needs at least 512Mi to start."
  The scheduler won't place it on a node that can't provide this.
- **Limits** = hard ceiling. If the container uses more than 768Mi, it's killed (OOMKill).
  CPU limits are softer -- the container is throttled, not killed.

Setting requests too high wastes capacity (pods can't be scheduled). Setting limits too
low causes OOMKills. The gap between requests and limits is "burst headroom."

---

## Current State

```
Cluster: DocumentStreamManagedCluster (2x Standard_B2s_v2, West Europe)
External IP: 51.138.91.82
Health check: curl http://51.138.91.82/health  ->  {"mode":"async"}
Grafana: kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
         (admin / prom-operator)

All Helm charts installed:
  - redis (documentstream namespace)
  - ingress-nginx (ingress-nginx namespace)
  - keda (keda namespace)
  - prometheus + grafana (monitoring namespace)
  - chaos-mesh (chaos-mesh namespace)

KEDA ScaledObjects applied for all 3 workers (extract, classify, store)
Grafana DocumentStream dashboard imported
PostgreSQL now using PersistentVolumeClaim with subPath

Still TODO:
  - Apply Chaos Mesh experiments
  - Demo rehearsal
  - Fix "No data" on Redis Queue Depth and KEDA Metrics dashboard panels
```

---

## Interview Talking Points from Today

If asked about autoscaling in the interview:

> "We used KEDA to watch Redis stream lag count. When documents queue up, KEDA scales
> classify-workers from 1 to 8. On a 2-node cluster we hit the resource ceiling -- 6 pods
> were Pending. In production, Cluster Autoscaler would add nodes to match the pod demand.
> That's the two-level scaling story: KEDA handles pods, Cluster Autoscaler handles nodes."

If asked about persistence:

> "We started with emptyDir for PostgreSQL, which works until a pod restarts and you lose
> everything. Switching to a PersistentVolumeClaim with subPath gave us data that survives
> pod restarts. The subPath is needed because Azure managed disks have a lost+found directory
> that PostgreSQL's initdb rejects."

If asked about monitoring:

> "Prometheus scrapes metrics from all pods, Grafana visualizes them. We built a custom
> dashboard with pod counts, resource usage, queue depth, and KEDA scaling metrics. Access
> is via kubectl port-forward since we don't expose monitoring publicly."
