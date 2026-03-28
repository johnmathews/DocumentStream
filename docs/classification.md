# Document Classification — Technical Deep Dive

How DocumentStream classifies documents using two complementary approaches:
rule-based keyword scoring and semantic embedding classification.

---

## Why Two Classifiers?

Different classification dimensions need different tools:

| Dimension | Best Approach | Why |
|---|---|---|
| **Privacy level** (Public/Confidential/Secret) | Rule-based | Indicators are explicit keywords ("KYC", "loan agreement", "invoice"). Deterministic, auditable, fast. |
| **Environmental impact** (None/Low/Medium/High) | Semantic | Risk is expressed contextually, not with fixed keywords. "Former textile dyeing facility" implies contamination without saying "contamination." |
| **Industry sectors** (multi-label) | Semantic | Documents touch multiple sectors simultaneously. A loan contract is Financial Services + Legal + Real Estate. |

Running both on every document lets us compare results and demonstrate when each
approach is appropriate — a key interview talking point.

---

## Rule-Based Classifier (`src/worker/classify.py`)

### How it works

1. Define keyword dictionaries for each classification level, with weights:
   ```
   "Secret" keywords:
     "know your customer"  → weight 4.0
     "anti-money laundering" → weight 3.5
     "source of funds"     → weight 3.0
     ...
   ```

2. For each document, scan the text for all keywords across all levels.

3. Sum the weights per level. The level with the highest total score wins.

4. Confidence = (winning score) / (sum of all scores).

### Strengths
- **Deterministic:** Same document always gets the same classification.
- **Explainable:** "This document was classified as Secret because it contains
  'know your customer' (weight 4.0) and 'source of funds' (weight 3.0)."
- **Fast:** Microseconds per document. No model loading.
- **Auditable:** A compliance team can review and approve the keyword list.

### Limitations
- **Brittle:** If a document describes KYC procedures without using the phrase
  "know your customer," it gets missed.
- **Single-dimensional:** Can only classify on one axis (privacy level).
- **Can't handle subtlety:** "The property was built in the 1970s with original
  insulation materials" implies asbestos risk, but no keyword would catch it.

---

## Semantic Classifier (`src/worker/semantic.py`)

### How it works

**Zero-shot classification using anchor embeddings:**

1. **Define anchor texts** — descriptive paragraphs (not keyword lists) for each
   category. For example, the "High environmental impact" anchor:

   > "The property presents significant environmental concerns. The site has a
   > history of industrial activity such as manufacturing, chemical processing,
   > metalworking, or textile production that may have resulted in soil or
   > groundwater contamination. The building may contain hazardous materials
   > such as asbestos insulation, lead paint, or other legacy construction
   > materials. The location is in an area vulnerable to flooding, situated
   > below sea level in a polder, near river flood plains, or in a zone
   > requiring active water management infrastructure."

2. **Embed the anchors** at startup using sentence-transformers (all-MiniLM-L6-v2,
   384 dimensions). Each anchor becomes a 384-number vector that captures its meaning.

3. **Embed each document** — the full extracted text becomes a vector.

4. **Compute cosine similarity** between the document vector and each anchor vector.

5. **Assign the category** with the highest similarity score.

### Why descriptive anchors, not keyword lists

This is the critical design decision. Compare:

**Bad anchor (keyword list):**
> "contamination, asbestos, flood, pollution, hazardous, toxic"

This is just keyword matching with extra steps. The embedding model would match
documents containing these exact words — no better than the rule-based classifier.

**Good anchor (descriptive paragraph):**
> "The site has a history of industrial activity such as manufacturing or
> textile production that may have resulted in soil contamination..."

The embedding model encodes the **meaning** of this paragraph. A document about
"a property on land that previously housed a dye works operating from 1962 to
1997" has no words in common with the anchor, but the meaning is similar:
- "dye works" ≈ "textile production" (same industry)
- "previously housed" ≈ "history of industrial activity" (past tense, industrial)

The cosine similarity between these embeddings is high because the concepts match,
even though the vocabulary doesn't.

### Real example: detecting flood risk without the word "flood"

**Anchor text (High environmental impact) includes:**
> "...location in an area vulnerable to flooding, situated below sea level
> in a polder, near river flood plains, or in a zone requiring active water
> management infrastructure."

**Generated valuation report text:**
> "The property is situated in a designated polder area, approximately 1.8
> metres below Normaal Amsterdams Peil (NAP). The local water board
> (waterschap) maintains active pumping infrastructure to manage groundwater
> levels in this zone."

The embedding model understands:
- "polder area, 1.8m below NAP" ≈ "below sea level in a polder"
- "water board maintains active pumping" ≈ "active water management infrastructure"
- Therefore: this document is about flood risk

A keyword classifier would need to enumerate every possible way to describe
flood risk. The semantic classifier handles variations it has never seen,
because it understands meaning.

### Classification dimensions

**Privacy Level** (single-label):
- Public / Confidential / Secret
- Compared with the rule-based result in the UI

**Environmental Impact** (single-label):
- None / Low / Medium / High
- Only the semantic classifier can assess this

**Industry Sectors** (multi-label, threshold: 0.15):
- Real Estate, Construction, Financial Services, Legal and Compliance, Environmental
- A document can belong to multiple sectors

### The embedding as stored data

Beyond classification, the document embedding is stored in PostgreSQL via pgvector.
This enables **semantic search** — finding documents by meaning rather than keywords:

```sql
-- "Find documents about environmental contamination risk"
SELECT filename, classification, environmental_impact
FROM documents
ORDER BY embedding <=> embed('environmental contamination risk')
LIMIT 10;
```

This query would find the valuation report about the former textile facility,
even though neither text contains the other's words.

---

## Production Considerations

### pgvector vs Azure AI Search

We use pgvector (PostgreSQL extension) for the demo. For production at a bank,
**Azure AI Search** would be the recommended choice:

| Feature | pgvector | Azure AI Search |
|---|---|---|
| Hybrid search (vector + keyword) | Manual implementation | Native, single query |
| Integrated embedding generation | No — client-side | Yes — calls Azure OpenAI automatically |
| Semantic re-ranking | No | Yes — cross-encoder L2 re-ranking |
| Quantization (storage reduction) | No | Built-in scalar/binary |
| Compliance | Via Azure PostgreSQL | SOC 2, GDPR, data residency |
| Cost | Included in PostgreSQL | Separate service (~€65+/month) |

**The interview answer:**
> "I used pgvector to demonstrate the fundamentals — embedding storage, cosine
> distance, similarity search. In production at scale, I'd recommend Azure AI
> Search. It adds hybrid search, semantic re-ranking, and integrated
> vectorization with Azure OpenAI. And it meets the compliance requirements
> for data residency in the Netherlands region."

### Embedding model

We use `all-MiniLM-L6-v2` (sentence-transformers, 384 dimensions) — free,
runs locally, no API dependency. For production:

**Azure OpenAI `text-embedding-3-small`** would be preferred:
- Higher quality embeddings (1536 dimensions)
- Data stays within Azure's boundary
- Consistent with Microsoft's recommended RAG architecture
- Billed per token (~$0.02 per 1M tokens — negligible for our volume)

---

## Accuracy & Trade-offs

### Rule-based classifier accuracy
- **100% on generated documents.** By design — the templates embed the keywords
  that trigger the correct classification. On real bank documents, accuracy would
  depend on how well the keyword list covers the vocabulary used.

### Semantic classifier behaviour
- **Privacy level:** Less precise than rule-based (compressed similarity scores).
  This is expected — privacy indicators are better handled by rules.
- **Environmental impact:** Effectively differentiates between documents with and
  without environmental content. Scores are subtle (0.38-0.48 range) because
  environmental text is one section in a multi-page document — the rest of the
  content dilutes the signal.
- **Industry sectors:** Accurate multi-label assignment. Correctly identifies
  that a loan contract is both Financial Services and Legal.

### When to use which
- **Compliance-critical classifications** (privacy, access control): Use rule-based.
  Deterministic, auditable, no model dependencies.
- **Risk assessment and discovery** (environmental, industry): Use semantic.
  Catches contextual signals that rules miss.
- **Both:** Run both on every document, store both results, let humans decide
  which to act on. This is the approach a bank's risk team would want.
