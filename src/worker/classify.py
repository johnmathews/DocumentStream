"""Document classification by sensitivity level.

Classifies extracted text into: Public, Confidential, or Secret.
Uses a weighted keyword scoring approach — each classification level has
a set of indicator keywords with associated weights. The document is
assigned the classification with the highest cumulative score.

This approach is:
- Deterministic and explainable (you can show exactly which keywords triggered)
- Fast (no model loading, runs in microseconds)
- Appropriate for a demo where generated documents contain known keywords
"""

from dataclasses import dataclass

# Keywords and their weights for each classification level.
# Higher weight = stronger indicator of that classification.
CLASSIFICATION_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "Public": [
        ("invoice", 3.0),
        ("contractor", 2.0),
        ("subtotal", 2.0),
        ("vat", 2.0),
        ("payment due", 1.5),
        ("purchase order", 1.5),
        ("delivery", 1.0),
        ("installation", 1.0),
        ("works", 1.0),
        ("project management", 1.0),
    ],
    "Confidential": [
        ("loan application", 3.0),
        ("property valuation", 3.0),
        ("valuation report", 3.0),
        ("market value", 2.5),
        ("floor area", 2.0),
        ("year built", 2.0),
        ("location analysis", 2.0),
        ("condition assessment", 2.0),
        ("loan amount", 1.5),
        ("interest rate", 1.5),
        ("loan-to-value", 1.5),
        ("property description", 1.5),
        ("risk factors", 1.5),
        ("annual revenue", 1.0),
        ("borrower", 1.0),
    ],
    "Secret": [
        ("know your customer", 4.0),
        ("kyc", 4.0),
        ("due diligence", 3.5),
        ("anti-money laundering", 3.5),
        ("aml screening", 3.5),
        ("source of funds", 3.0),
        ("beneficial owner", 3.0),
        ("ownership structure", 3.0),
        ("loan agreement", 3.0),
        ("events of default", 3.0),
        ("covenants", 2.5),
        ("governing law", 2.5),
        ("collateral", 2.5),
        ("risk assessment", 2.0),
        ("politically exposed", 2.0),
        ("sanction", 2.0),
        ("compliance", 1.5),
        ("confidential", 1.0),
    ],
}


@dataclass
class ClassificationResult:
    """Result of classifying a document."""

    classification: str
    confidence: float
    scores: dict[str, float]
    matched_keywords: dict[str, list[str]]


def classify_text(text: str) -> ClassificationResult:
    """Classify document text by sensitivity level.

    Args:
        text: Extracted text content from the document.

    Returns:
        ClassificationResult with the assigned classification, confidence
        score, per-level scores, and which keywords matched.
    """
    text_lower = text.lower()

    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for level, keywords in CLASSIFICATION_KEYWORDS.items():
        level_score = 0.0
        level_matches: list[str] = []
        for keyword, weight in keywords:
            if keyword in text_lower:
                level_score += weight
                level_matches.append(keyword)
        scores[level] = level_score
        matched[level] = level_matches

    # Assign the classification with the highest score.
    # If all scores are 0, default to Confidential (safe middle ground).
    total = sum(scores.values())
    if total == 0:
        return ClassificationResult(
            classification="Confidential",
            confidence=0.0,
            scores=scores,
            matched_keywords=matched,
        )

    best_level = max(scores, key=scores.get)  # type: ignore[arg-type]
    confidence = scores[best_level] / total

    return ClassificationResult(
        classification=best_level,
        confidence=round(confidence, 3),
        scores={k: round(v, 2) for k, v in scores.items()},
        matched_keywords=matched,
    )
