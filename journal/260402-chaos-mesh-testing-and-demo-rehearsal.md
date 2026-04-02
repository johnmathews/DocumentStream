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

## Files changed

- `k8s/chaos/pod-kill.yaml` — changed mode from `fixed`/`value: "2"` to `one`
- `infra/helm-install.sh` — added containerd runtime settings for Chaos Mesh
- `docs/chaos-experiments.md` — added containerd prerequisite note and verified results
- `docs/demo-guide.md` — updated rolling update section to use gateway instead of workers
- `CLAUDE.md` — removed chaos mesh and demo rehearsal from "Not yet done"
