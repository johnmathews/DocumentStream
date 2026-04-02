# Chaos Mesh Testing & Demo Rehearsal

**Date:** 2026-04-02

## What happened

Ran all three Chaos Mesh experiments on the live AKS cluster and did a full demo rehearsal.

## Chaos Mesh containerd fix

The CPU stress and network delay experiments were failing with:
```
rpc error: code = Unknown desc = expected docker:// but got container
```

Root cause: AKS uses containerd as the container runtime, but Chaos Mesh defaults to Docker.
Fixed by adding Helm values to `infra/helm-install.sh`:
```
--set chaosDaemon.runtime=containerd
--set chaosDaemon.socketPath=/run/containerd/containerd.sock
```

Applied via `helm upgrade --install`. Chaos daemons restarted and all experiments work.

## Experiment results

### Pod Kill
- Pod killed and replacement Running+Ready in ~8 seconds
- Pipeline processed documents immediately after recovery
- Zero data loss confirmed
- Changed `mode: fixed` / `value: "2"` to `mode: one` — KEDA keeps replicas at 1 when
  queue is empty, so requesting to kill 2 pods fails

### CPU Stress
- Successfully injected 80% CPU burn on classify-worker
- With 80 concurrent uploads, classify lag reached 18 messages
- KEDA scaled classify-workers from 1 to 4 pods within 15 seconds
- 3 new pods were Pending due to node capacity (2 nodes instead of 3)
- In production, AKS Cluster Autoscaler would add nodes

### Network Delay
- 500ms delay injected on store-worker
- Pipeline slowed but continued processing
- Store lag reached 8 messages during the experiment
- All messages processed after delay cleared

## Demo rehearsal findings

1. **Web UI** loads in ~36ms, generate endpoint works reliably
2. **Rolling update demo** should target the gateway (has readiness probes),
   not the workers (no HTTP endpoints). Updated demo guide accordingly.
3. **KEDA + Chaos Mesh interaction:** The `/api/generate` endpoint processes
   synchronously (bypasses Redis), so it doesn't trigger KEDA scaling. Must use
   `/api/documents` upload endpoint or Locust for queue-based load.
4. **Node capacity:** Only 2 of 3 configured nodes are running. Some KEDA-scaled
   pods couldn't schedule. Not a blocker for the demo narrative but worth noting.

## Additional fixes

- **Blob storage paths:** Removed unnecessary UUID prefix from blob names. Documents
  are now stored as `CRE-123456/contract.pdf` instead of `{uuid}/CRE-123456/contract.pdf`.
  The loan ID grouping in the filename is sufficient.
- **Locust load test:** Reweighted tasks so 80% of requests use the async `/api/documents`
  endpoint (which goes through Redis and triggers KEDA). Removed the sync `/api/generate`
  task which bypassed Redis entirely. Reduced wait time from 1-3s to 0.5-1.5s.
- **Chaos Mesh dashboard RBAC:** Created a `chaos-admin` service account with cluster-admin
  binding to fix the dashboard permission error. Generated a long-lived token for demo use.
- **Demo checklist:** Removed the PostgreSQL Flexible Server start step — Postgres runs
  in-cluster as a pod, starts automatically with AKS.
- **Documentation audit:** Fixed test count in README (51 → 92), corrected Azure resource
  names across all docs, updated implementation plan progress.
- **CI fix:** `src/worker/store.py` had a ruff format issue (function args on one line).

## Files changed

- `k8s/chaos/pod-kill.yaml` — changed mode from `fixed`/`value: "2"` to `one`
- `infra/helm-install.sh` — added containerd runtime settings for Chaos Mesh
- `infra/setup.sh` — corrected storage account name
- `docs/chaos-experiments.md` — added containerd prerequisite note and verified results
- `docs/demo-guide.md` — updated rolling update section, removed stale Postgres checklist item
- `docs/implementation-plan.md` — marked chaos, rolling update, demo rehearsal as DONE
- `locust/locustfile.py` — reweighted for async pipeline, removed sync generate task
- `src/worker/store.py` — simplified blob path (filename only, no UUID prefix)
- `tests/test_store.py` — updated blob path assertions
- `README.md` — corrected test count (51 → 92)
- `CLAUDE.md` — removed chaos mesh and demo rehearsal from "Not yet done"
- `.engineering-team/architecture-plan.md` — updated demo script and Azure resource names
- `.github/workflows/deploy.yml` — corrected AKS cluster name and resource group
