# Start Here

This is a portfolio project for a RaboBank Data Engineer interview. It demonstrates
Kubernetes, CI/CD, and data engineering on Azure by building a document processing
pipeline for commercial real estate (CRE) loan documents.

The project is being built over 3 days (March 28-30, 2026), with a live demo at the
interview after Day 3.

## What to read first

| Document | What it covers |
|----------|---------------|
| [README.md](README.md) | Project overview, quick start, API docs, design decisions |
| [project-brief.md](project-brief.md) | Original interview brief and brainstorming notes |

## The plan

There are two plan documents:

| Document | Purpose |
|----------|---------|
| [docs/implementation-plan.md](docs/implementation-plan.md) | **Active execution tracker** — 11 stages with checkboxes, progress dashboard, time estimates, priority tiers. This is the day-to-day checklist. |
| [.engineering-team/architecture-plan.md](.engineering-team/architecture-plan.md) | Original architectural vision — technology choices, cost analysis, demo script, interview positioning. Higher-level context and rationale. |

**Use `docs/implementation-plan.md` as the primary plan.** It has a progress dashboard at
the top showing what's done and what's next.

## Technical documentation

| Document | What it covers |
|----------|---------------|
| [docs/architecture.md](docs/architecture.md) | System design, pipeline flow, deployment architecture, Azure cost breakdown |
| [docs/classification.md](docs/classification.md) | How the two classifiers work (rule-based privacy + semantic environmental/industry) |
| [docs/pipeline.md](docs/pipeline.md) | Redis Streams message flow, stream schemas, dual-mode gateway |
| [docs/demo-guide.md](docs/demo-guide.md) | 8-minute live demo script with timing cues and talking points |
| [docs/dictionary.md](docs/dictionary.md) | Glossary of K8s, Azure, and data engineering concepts (learning reference) |

## Development journal

The [journal/](journal/) directory tracks decisions, progress, and context:

- `260328-project-kickoff.md` — Day 1: architectural decisions, technology choices
- `260329-add-readme.md` — Day 2 morning: README, plan audit
- `260329-redis-pipeline-and-k8s-manifests.md` — Day 2 afternoon: Redis pipeline, K8s manifests, Azure setup

## Key commands

```
make test       # Run 83 tests
make lint       # Run ruff linter
make generate   # Generate 10 loan scenarios (50 PDFs)
make dev        # Start local dev environment (docker-compose)
```

## Project structure

```
src/gateway/     — FastAPI API + web UI (sync or async mode)
src/worker/      — Pipeline workers (extract, classify, semantic, store)
src/generator/   — PDF document generator (5 CRE loan templates)
tests/           — All tests (83)
k8s/             — Kubernetes manifests
infra/           — Azure setup/teardown scripts
docs/            — Documentation (6 files, see table above)
journal/         — Development journal
demo_samples/    — Sample PDFs (one complete loan scenario)
```
