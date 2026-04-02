# Chaos Engineering Experiments

Chaos Mesh experiments for demonstrating Kubernetes resilience and self-healing. All experiment YAMLs are in
`k8s/chaos/`.

## Prerequisites

- Chaos Mesh installed with containerd runtime support (AKS uses containerd, not Docker):
  ```bash
  helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
    --namespace chaos-mesh \
    --set chaosDaemon.runtime=containerd \
    --set chaosDaemon.socketPath=/run/containerd/containerd.sock
  ```
  Without the containerd settings, StressChaos and NetworkChaos fail with
  `expected docker:// but got container` errors. The `infra/helm-install.sh` script
  already includes these settings.
- Pipeline running with documents flowing through Redis Streams
- Grafana dashboard open to observe the effects

## Experiment 1: Pod Kill (Self-Healing)

Kills classify-worker pods. K8s restarts them within seconds. Redis re-delivers unacknowledged messages — zero data loss,
zero manual intervention.

```bash
# Watch pods (run in a separate terminal)
kubectl get pods -w

# Apply the experiment
kubectl apply -f k8s/chaos/pod-kill.yaml

# Check experiment status
kubectl get podchaos

# Clean up
kubectl delete podchaos pod-kill-classify-worker
```

**What to watch for:**

- Classify-worker pod disappears and a new one starts within seconds
- Pod restarts counter increments (visible in Grafana "Pod Restarts" panel)
- Pipeline continues processing after the new pod is ready

**Verified result (2026-04-02):** Pod killed and replacement Running+Ready in ~8 seconds.
Pipeline processed documents immediately after recovery. Zero data loss confirmed.

## Experiment 2: Network Delay (Resilience)

Injects 500ms latency (with 100ms jitter) on store-worker pods for 2 minutes. Simulates degraded connectivity to
PostgreSQL or Azure Blob Storage.

```bash
# Apply the experiment
kubectl apply -f k8s/chaos/network-delay.yaml

# Check experiment status
kubectl get networkchaos

# Clean up (or wait 2 minutes for auto-expiry)
kubectl delete networkchaos network-delay-store-worker
```

**What to watch for:**

- Pipeline slows but does not break
- Redis queue depth increases (store-worker processing is slower)
- Grafana network I/O panel shows the latency effect
- After expiry, throughput returns to normal

**Verified result (2026-04-02):** Pipeline slowed but continued processing. Store-worker
lag reached 8 messages (normally 0) during the experiment. All messages processed after
delay cleared.

## Experiment 3: CPU Stress (KEDA Autoscaling)

Burns 80% CPU on classify-worker pods for 2 minutes. This is the most impressive experiment — it triggers KEDA
autoscaling.

```bash
# Apply the experiment
kubectl apply -f k8s/chaos/cpu-stress.yaml

# Generate load so messages pile up in the queue
# (use the dashboard "Generate" button, or repeat this curl)
curl -X POST http://51.138.91.82/api/generate -H 'Content-Type: application/json' -d '{"count": 10}'

# Watch KEDA scale up workers
kubectl get pods -w

# Check experiment status
kubectl get stresschaos

# Clean up (or wait 2 minutes for auto-expiry)
kubectl delete stresschaos cpu-stress-classify-worker
```

**What to watch for:**

- Classify-workers slow down, Redis queue depth rises
- KEDA detects the lag and scales up additional classify-worker pods
- New pods process the backlog, queue depth drops
- After stress ends + 60s cooldown, KEDA scales back down to 1

**Verified result (2026-04-02):** CPU stress injected successfully (required containerd
runtime fix — see Prerequisites). With 80 concurrent PDF uploads, classify lag reached 18
messages. KEDA scaled classify-workers from 1 to 4 pods within 15 seconds. Additional pods
were Pending due to node capacity (2 nodes) — in production, AKS Cluster Autoscaler would
add nodes.

**Note:** The `/api/generate` endpoint processes documents synchronously (bypasses Redis).
To test KEDA scaling, use the `/api/documents` upload endpoint which queues through Redis,
or use Locust.

## Recommended Demo Order

1. **Pod Kill** — quick (30s), shows self-healing
2. **CPU Stress** — most visual (2min), shows KEDA autoscaling, generate load while it runs
3. **Network Delay** — optional, shows resilience under degraded conditions

## Cleaning Up All Experiments

```bash
kubectl delete podchaos,networkchaos,stresschaos --all
```
