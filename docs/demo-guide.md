# DocumentStream — Demo & Presentation Guide

A step-by-step guide for the live demo and interview presentation. Includes exact
commands, timing, talking points, and things to name-drop with context on **why**.

---

## Pre-Demo Checklist

Before the interview:

- [ ] AKS cluster is running (`az aks start -n DocumentStreamManagedCluster -g documentstream`)
- [ ] PostgreSQL is running (`az postgres flexible-server start -n documentstream-pg -g documentstream`)
- [ ] All pods are healthy (`kubectl get pods -n documentstream`)
- [ ] Grafana is accessible and dashboard is loaded
- [ ] Chaos Mesh dashboard is accessible
- [ ] Locust is ready (either in-cluster or local)
- [ ] Browser tabs pre-opened: Web UI, Grafana, Chaos Mesh, Locust
- [ ] Printed materials ready: architecture diagram, K8s manifest highlights, cost breakdown
- [ ] Terminal open with `kubectl` configured

---

## Demo Flow (8-10 minutes)

### Minute 0-1: "Here's the system"

**Show:** Web UI at `/` — the DocumentStream dashboard

**Say:**
> "This is DocumentStream — a document processing pipeline for commercial real estate loan
> documents. It processes five types of documents that a bank generates during a loan
> lifecycle: loan applications, property valuations, KYC reports, contracts, and
> contractor invoices."

**Show:** Click "Generate" with 5 scenarios

> "Each loan scenario generates 5 linked documents. They share the same loan ID, client,
> and property — just like a real bank's document management system. Each PDF is uploaded
> to Azure Blob Storage automatically — you can see the count and total size per document
> type on the Grafana dashboard."

**Point out the two classifier columns:**
> "Every document goes through two classifiers. The rule-based classifier handles privacy
> levels — Public, Confidential, Secret — using weighted keyword matching. It's fast and
> deterministic. The semantic classifier uses sentence-transformer embeddings to assess
> environmental impact and industry sectors. That's something rules can't do."

---

### Minute 1-2: "Why two classifiers?"

**This is the key technical talking point. Take your time here.**

> "Rule-based classification works well for privacy levels because the indicators are
> explicit — a document either mentions 'KYC' and 'due diligence' or it doesn't.
> But environmental risk is different."

**Point to a valuation report with "High" environmental impact:**
> "This valuation report describes a property 'situated on land that previously housed
> a textile dyeing facility' and is 'located in a designated polder area, 1.8 metres
> below NAP.' A keyword classifier would miss this completely — there's no word
> 'contamination' or 'flood' in the text. But the embedding model understands that
> 'textile dyeing facility' is semantically close to 'industrial contamination,' and
> 'polder below NAP' is semantically close to 'flood risk.'"

> "That's why we use vector embeddings. We define descriptive anchor texts for each
> environmental impact level — not keyword lists, but paragraphs describing what
> 'High environmental impact' means in natural language. Then we compute cosine
> similarity between the document embedding and each anchor. The category with the
> highest similarity wins."

**If asked "why not just add more keywords?":**
> "You can't enumerate every way someone might describe environmental risk. 'Former
> industrial site,' 'legacy building materials from the 1970s,' 'water management zone' —
> these all imply risk without using the word 'risk.' The embedding model captures
> meaning, not syntax."

---

### Minute 2-4: "Watch it scale"

**Show:** Open Locust, set to 50 concurrent users

**Show:** Switch to Grafana dashboard — watch metrics update

> "I'm generating 50 concurrent document uploads. Watch the Redis queue depth climb.
> KEDA — Kubernetes Event-Driven Autoscaler — monitors the queue. When documents pile
> up, it adds worker pods automatically."

**Point at Grafana panels:**
> "There — extract workers scaled from 1 to 4. Classify workers are at 3.
> KEDA checks queue depth every 30 seconds and calculates how many workers are needed.
> When the queue drains, it scales back down. This is event-driven scaling — not
> CPU-based. It scales on actual demand."

**If asked "why KEDA instead of regular HPA?":**
> "The built-in Horizontal Pod Autoscaler can only scale on CPU and memory metrics.
> For a queue-based pipeline, that's not useful — a worker at 10% CPU with 500 messages
> waiting still needs more replicas. KEDA adds custom scalers for Redis, Kafka, Azure
> Service Bus, and dozens of other event sources."

---

### Minute 4-6: "Watch it heal"

**Run:** `kubectl apply -f k8s/chaos/pod-kill.yaml`

> "I'm going to kill a classify worker. This simulates a node failure or a process crash."

**Show:** `kubectl get pods -n documentstream -l app=classify-worker` — pod dies and restarts
in ~8 seconds

> "Kubernetes detected the failed pod within seconds and created a replacement. The
> document that worker was processing? It stayed unacknowledged in the Redis
> stream. When the new worker started, it picked up the unfinished message.
> Zero data loss."

**Explain the Redis Streams guarantee:**
> "We use Redis Streams, not Redis Pub/Sub or simple Lists. With Streams, workers must
> explicitly acknowledge each message after processing. If a worker dies before
> acknowledging, the message gets re-delivered to another worker. This is at-least-once
> delivery — the same guarantee you get from Kafka or Azure Service Bus, but with a
> much simpler operational footprint."

---

### Minute 6-8: "Watch it handle a bad deployment"

**Run:** `kubectl set image deployment/gateway gateway=acrdocumentstream.azurecr.io/gateway:buggy -n documentstream`

> "I just deployed a 'buggy' version of the gateway — pointing to an image tag that
> doesn't exist. Watch the rolling update."

**Show:** `kubectl get pods -n documentstream -l app=gateway` — new pod is Pending/ImagePullBackOff,
old pods still Running

> "K8s starts the new pod, but it can't pull the image. The rolling update strategy
> keeps the old pods running — the system is still serving traffic. No downtime."

**Verify:** `curl http://51.138.91.82/health` — still returns 200

**Run:** `kubectl rollout undo deployment/gateway -n documentstream`

> "One command to rollback. The previous version is restored in seconds."

**Note:** The gateway has readiness probes configured, so K8s knows not to route
traffic to unhealthy pods. The workers don't have HTTP endpoints (they're Redis
consumers), so the gateway is the best target for this demo.

---

### Minute 8-10: "Architecture & cost"

**Show:** Paper printout of architecture diagram

> "The full pipeline: FastAPI gateway receives uploads, puts them on a Redis stream.
> Extract workers pull text with PyMuPDF. Classify workers run both rule-based and
> semantic classification. Store workers save metadata and embeddings to PostgreSQL
> with pgvector, and original PDFs to Azure Blob Storage. The gateway exposes Prometheus
> metrics — blob upload counts and sizes by document type — which Prometheus scrapes
> via a ServiceMonitor and Grafana displays in real time."

**Show:** Cost breakdown

> "The entire cluster costs about 28 cents per hour. Three B2ms nodes on AKS Free
> tier, a B1ms PostgreSQL Flexible Server, Basic ACR, and Blob Storage. When I'm
> not demoing, I stop the cluster and database — costs drop to near zero."

**Show:** CI/CD diagram or GitHub Actions tab

> "Every push to main triggers a GitHub Actions workflow that builds the container
> images, pushes them to Azure Container Registry, and deploys to AKS using kubectl."

---

## Name-Drops & Why They Matter

These are things to mention naturally during the demo or in follow-up questions.
Don't force them — use them when the conversation goes there.

### Azure AI Search
**When to mention:** When asked about the vector database choice or production scaling.

**What to say:**
> "I used pgvector to demonstrate the core concepts — embedding storage, cosine
> similarity search. For production at enterprise scale, I'd recommend Azure AI
> Search. It adds hybrid search — combining vector similarity and keyword matching
> in a single query with reciprocal rank fusion. It also has integrated vectorization
> with Azure OpenAI, semantic re-ranking with a cross-encoder model, and built-in
> quantization to reduce storage costs. And it meets the compliance requirements
> a bank needs — SOC 2, GDPR, data residency in the Netherlands region."

**Why this matters:** Shows you understand the difference between a demo tool and a
production-grade solution, and that you know Microsoft's recommended architecture
for RAG workloads on Azure.

### KEDA vs HPA
**When to mention:** When discussing autoscaling.

**What to say:**
> "Standard HPA scales on CPU and memory. KEDA extends that to any event source —
> in our case, Redis queue depth. In a bank context, you'd use KEDA with Azure
> Service Bus or Event Hubs scalers."

### Redis Streams vs Kafka
**When to mention:** When asked about the message broker choice.

**What to say:**
> "Redis Streams gives us the durability guarantees we need — consumer groups with
> message acknowledgment. For a demo, it's lighter to operate than Kafka. In
> production, if throughput requirements grew beyond what a single Redis instance
> handles, I'd consider Azure Event Hubs, which is Kafka-compatible and fully managed."

### Sentence-Transformers + ONNX Runtime vs Azure OpenAI
**When to mention:** When asked about the embedding model or container optimization.

**What to say:**
> "I used sentence-transformers locally — specifically all-MiniLM-L6-v2 — with ONNX
> Runtime as the inference backend instead of PyTorch. ONNX Runtime is about 50MB
> versus 5GB for full PyTorch, which makes a big difference in a K8s environment —
> faster image pulls, faster pod startup when KEDA scales up, and lower memory per
> worker. For production, I'd use Azure OpenAI's text-embedding-3-small model. The
> embeddings are higher quality, and the data stays within Azure's boundary —
> important for a bank's compliance requirements."

### Chaos Engineering
**When to mention:** When they seem impressed by the self-healing demo.

**What to say:**
> "This is called chaos engineering — intentionally injecting failures to verify the
> system recovers. Netflix pioneered this with Chaos Monkey. We use Chaos Mesh,
> which is a CNCF incubating project designed for Kubernetes. In production, you'd
> run chaos experiments in a staging environment as part of your release qualification
> process."

---

## Anticipated Questions & Answers

### "How would this handle 10x the volume?"
> "The architecture scales horizontally. KEDA would add more worker pods. If we hit
> the node limit, AKS Cluster Autoscaler adds more nodes. For the database, we'd
> either scale up the PostgreSQL Flexible Server or switch to Azure Cosmos DB for
> PostgreSQL (Citus), which distributes across multiple nodes. For the queue, Redis
> Cluster or Azure Event Hubs."

### "What about data security? These are bank documents."
> "In production: all Azure services behind Private Endpoints in a VNet, no public
> internet exposure. Customer-managed encryption keys for data at rest. Azure AD
> authentication instead of passwords. RBAC at the K8s namespace level — the classify
> workers can't access the database directly, only the store workers can. And the
> classification labels themselves drive access control — Secret documents are only
> accessible to authorized roles."

### "Why Kubernetes and not just Azure Functions?"
> "Functions would work for simple event processing. But K8s gives us control over
> the execution environment, the ability to run the same stack locally with
> docker-compose, fine-grained resource management, and more deployment strategies
> (rolling updates, canary, blue-green). For a team managing multiple interconnected
> services — which is what a data engineering team at a bank does — K8s provides a
> consistent platform."

### "What would you do differently with more time?"
> "Three things: First, replace the rule-based privacy classifier with a fine-tuned
> model trained on real bank documents. Second, add a RAG layer — let users ask
> natural language questions about the loan portfolio and retrieve relevant documents
> using the vector embeddings. Third, set up a proper GitOps workflow with Flux or
> ArgoCD for declarative deployments instead of kubectl."

---

## Paper Printout Checklist

Materials to print and bring to the interview:

- [ ] **Architecture diagram** — the full system diagram with pipeline flow
- [ ] **K8s manifest excerpt** — one Deployment + one ScaledObject YAML (annotated)
- [ ] **Classification comparison table** — rules vs semantic results on the same documents
- [ ] **Cost breakdown** — per-service costs with totals
- [ ] **GitHub Actions workflow** — the CI/CD pipeline YAML (annotated)
- [ ] **Anchor text example** — showing how descriptive anchors enable semantic classification
  (the "textile dyeing facility" → "industrial contamination" example)
