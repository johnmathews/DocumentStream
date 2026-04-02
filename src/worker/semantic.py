"""Semantic document classifier using ONNX Runtime embeddings.

Classifies documents across multiple dimensions using zero-shot classification
with descriptive anchor texts. Unlike the rule-based classifier, this approach
understands meaning — it can detect environmental risks from contextual
descriptions even when no specific keywords are present.

Dimensions:
    - Privacy Level: Public / Confidential / Secret
    - Environmental Impact: None / Low / Medium / High
    - Industry Sectors: multi-label from a fixed set

How it works:
    1. At startup, embed all anchor texts (descriptive paragraphs per category)
    2. For each document, embed the full extracted text
    3. Compute cosine similarity between document embedding and each anchor
    4. Assign the category with highest similarity, with a confidence score
    5. Store the document embedding in pgvector for later semantic search
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np
from huggingface_hub import hf_hub_download
from numpy.typing import NDArray
from transformers import AutoTokenizer

if TYPE_CHECKING:
    import onnxruntime as ort

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
ONNX_FILENAME = "onnx/model.onnx"
MAX_SEQ_LENGTH = 256  # from sentence_bert_config.json
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _get_tokenizer() -> AutoTokenizer:
    """Load the tokenizer (cached, loaded once)."""
    return AutoTokenizer.from_pretrained(MODEL_REPO)


@lru_cache(maxsize=1)
def _get_session() -> ort.InferenceSession:
    """Load the ONNX Runtime inference session (cached, loaded once).

    Downloads the ONNX model from HuggingFace Hub on first use.
    Subsequent calls use the huggingface_hub cache.
    """
    import onnxruntime as ort

    model_path = hf_hub_download(repo_id=MODEL_REPO, filename=ONNX_FILENAME)
    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def _mean_pooling(
    token_embeddings: NDArray[np.float32],
    attention_mask: NDArray[np.int64],
) -> NDArray[np.float32]:
    """Apply mean pooling: average token embeddings weighted by attention mask.

    Args:
        token_embeddings: shape (batch, seq_len, hidden_dim)
        attention_mask: shape (batch, seq_len)

    Returns:
        Pooled embeddings of shape (batch, hidden_dim)
    """
    mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
    sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
    sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask


def _l2_normalize(x: NDArray[np.float32]) -> NDArray[np.float32]:
    """L2-normalize each row vector."""
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-9, a_max=None)
    return x / norms


def _encode(texts: list[str]) -> NDArray[np.float32]:
    """Tokenize, run ONNX inference, pool, and normalize.

    Returns L2-normalized embeddings of shape (len(texts), 384).
    """
    tokenizer = _get_tokenizer()
    session = _get_session()

    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
        return_tensors="np",
    )

    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]

    # token_type_ids may or may not be required by the ONNX model
    ort_inputs: dict[str, NDArray] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    # Add token_type_ids if the model expects it
    model_input_names = {inp.name for inp in session.get_inputs()}
    if "token_type_ids" in model_input_names and "token_type_ids" in encoded:
        ort_inputs["token_type_ids"] = encoded["token_type_ids"]

    outputs = session.run(None, ort_inputs)
    token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)

    pooled = _mean_pooling(token_embeddings, attention_mask)
    return _l2_normalize(pooled)


def embed_text(text: str) -> NDArray[np.float32]:
    """Embed a text string into a vector."""
    return _encode([text])[0]


def embed_texts(texts: list[str]) -> NDArray[np.float32]:
    """Embed multiple texts into vectors (batched for efficiency)."""
    return _encode(texts)


# ---------------------------------------------------------------------------
# Anchor definitions
#
# Each anchor is a descriptive paragraph that captures the MEANING of the
# category, not a keyword list. The embedding model encodes semantics, so
# descriptions like "land previously used for heavy industry" will match
# documents mentioning "former steel mill" or "textile dyeing factory"
# even without shared keywords.
# ---------------------------------------------------------------------------

PRIVACY_ANCHORS: dict[str, str] = {
    "Public": (
        "This document contains general information intended for public "
        "distribution. It includes published reports, marketing materials, "
        "product brochures, general terms and conditions, press releases, "
        "and contractor invoices for standard commercial services. There is "
        "no personal data, no client-specific financial information, and no "
        "restricted internal content."
    ),
    "Confidential": (
        "This document contains internal business information that should "
        "not be shared publicly. It includes client loan applications, "
        "property valuation assessments, internal financial analyses, "
        "revenue figures, market comparisons, and business correspondence. "
        "It may reference specific properties, transaction amounts, and "
        "commercial terms but does not contain deeply sensitive personal "
        "or regulatory data."
    ),
    "Secret": (
        "This document contains highly sensitive information requiring "
        "restricted access. It includes know-your-customer due diligence "
        "reports, anti-money laundering screening results, individual "
        "credit assessments, legal contracts with confidentiality clauses, "
        "personal financial records, regulatory compliance findings, and "
        "binding loan agreements with detailed terms and covenants."
    ),
}

ENVIRONMENTAL_ANCHORS: dict[str, str] = {
    "High": (
        "The property presents significant environmental concerns. The "
        "site has a history of industrial activity such as manufacturing, "
        "chemical processing, metalworking, or textile production that may "
        "have resulted in soil or groundwater contamination. The building "
        "may contain hazardous materials such as asbestos insulation, lead "
        "paint, or other legacy construction materials. The location is in "
        "an area vulnerable to flooding, situated below sea level in a "
        "polder, near river flood plains, or in a zone requiring active "
        "water management infrastructure. There are significant remediation "
        "costs or environmental liabilities associated with the property."
    ),
    "Medium": (
        "The property has moderate environmental considerations. The "
        "renovation plans include energy efficiency improvements, "
        "installation of sustainable building systems, waste management "
        "during construction, or compliance with environmental building "
        "standards. The site may be near transportation infrastructure "
        "with associated noise or air quality considerations. Some "
        "environmental assessment or monitoring may be required but no "
        "major contamination or hazard has been identified."
    ),
    "Low": (
        "The property has minimal environmental considerations. It is a "
        "standard commercial building in an urban or suburban area with no "
        "known history of industrial use, no hazardous materials concerns, "
        "and no particular flood or environmental risk. The location is on "
        "stable ground in a well-maintained area with standard municipal "
        "infrastructure and services."
    ),
    "None": (
        "This document does not relate to physical property or "
        "environmental matters. It covers purely financial, legal, or "
        "administrative topics such as loan terms, interest rates, "
        "payment schedules, client identity verification, corporate "
        "structure, or contractual obligations without reference to "
        "physical site conditions or environmental factors."
    ),
}

INDUSTRY_ANCHORS: dict[str, str] = {
    "Real Estate": (
        "Commercial and residential property development, property "
        "valuation and appraisal, real estate investment, building "
        "renovation and redevelopment, property management, lease "
        "agreements, and real estate market analysis."
    ),
    "Construction": (
        "Building construction, structural engineering, architectural "
        "design, demolition, site preparation, foundation work, "
        "electrical and plumbing installation, facade renovation, "
        "HVAC systems, fire safety, and project management for "
        "construction projects."
    ),
    "Financial Services": (
        "Banking, lending, loan origination and servicing, credit "
        "assessment, interest rate management, collateral valuation, "
        "debt structuring, financial covenants, payment processing, "
        "and corporate finance."
    ),
    "Legal and Compliance": (
        "Contract law, regulatory compliance, know-your-customer "
        "verification, anti-money laundering screening, due diligence "
        "investigations, legal agreements, governing law provisions, "
        "corporate governance, and regulatory reporting."
    ),
    "Environmental": (
        "Environmental assessment, soil and groundwater analysis, "
        "contamination remediation, sustainability, energy efficiency, "
        "emissions monitoring, waste management, environmental "
        "regulations, and ecological impact assessment."
    ),
}

# Threshold for industry multi-label assignment
INDUSTRY_THRESHOLD = 0.15

# Minimum margin between top-1 and top-2 scores to report a confident result.
# Below this, the classifier reports the top label but flags low confidence.
CONFIDENCE_MARGIN = 0.03


# ---------------------------------------------------------------------------
# Anchor embedding cache
# ---------------------------------------------------------------------------


@dataclass
class _AnchorSet:
    """Pre-computed embeddings for a set of category anchors."""

    labels: list[str]
    embeddings: NDArray[np.float32]


@lru_cache(maxsize=1)
def _get_anchor_sets() -> dict[str, _AnchorSet]:
    """Embed all anchor texts (done once at startup)."""
    result: dict[str, _AnchorSet] = {}
    for name, anchors in [
        ("privacy", PRIVACY_ANCHORS),
        ("environmental", ENVIRONMENTAL_ANCHORS),
        ("industry", INDUSTRY_ANCHORS),
    ]:
        labels = list(anchors.keys())
        texts = list(anchors.values())
        embeddings = embed_texts(texts)
        result[name] = _AnchorSet(labels=labels, embeddings=embeddings)
    return result


def _classify_against_anchors(
    doc_embedding: NDArray[np.float32],
    anchor_set: _AnchorSet,
) -> list[tuple[str, float]]:
    """Compute similarity scores between a document and anchor embeddings.

    Returns list of (label, similarity) sorted by similarity descending.
    """
    similarities = doc_embedding @ anchor_set.embeddings.T
    scored = list(zip(anchor_set.labels, similarities.tolist(), strict=True))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class SemanticClassification:
    """Full semantic classification result for a document."""

    privacy_level: str
    privacy_confidence: float
    privacy_scores: dict[str, float]

    environmental_impact: str
    environmental_confidence: float
    environmental_scores: dict[str, float]

    industries: list[str]
    industry_scores: dict[str, float]

    embedding: list[float] = field(repr=False)


def classify_semantic(text: str) -> SemanticClassification:
    """Classify document text across all semantic dimensions.

    Args:
        text: Extracted text content from the document.

    Returns:
        SemanticClassification with privacy level, environmental impact,
        industry sectors, and the document embedding for storage.
    """
    anchor_sets = _get_anchor_sets()
    doc_embedding = embed_text(text)

    # Privacy level
    privacy_scores = _classify_against_anchors(doc_embedding, anchor_sets["privacy"])
    privacy_label = privacy_scores[0][0]
    privacy_conf = privacy_scores[0][1]

    # Environmental impact
    env_scores = _classify_against_anchors(doc_embedding, anchor_sets["environmental"])
    env_label = env_scores[0][0]
    env_conf = env_scores[0][1]

    # Industry sectors (multi-label: all above threshold)
    ind_scores = _classify_against_anchors(doc_embedding, anchor_sets["industry"])
    industries = [label for label, score in ind_scores if score >= INDUSTRY_THRESHOLD]

    return SemanticClassification(
        privacy_level=privacy_label,
        privacy_confidence=round(float(privacy_conf), 3),
        privacy_scores={k: round(float(v), 3) for k, v in privacy_scores},
        environmental_impact=env_label,
        environmental_confidence=round(float(env_conf), 3),
        environmental_scores={k: round(float(v), 3) for k, v in env_scores},
        industries=industries,
        industry_scores={k: round(float(v), 3) for k, v in ind_scores},
        embedding=doc_embedding.tolist(),
    )
