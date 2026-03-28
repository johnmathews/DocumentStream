"""Tests for the semantic classifier."""

import numpy as np

from generator.scenario import LoanScenario
from generator.templates import DOCUMENT_TYPES
from worker.extract import extract_text
from worker.semantic import (
    EMBEDDING_DIM,
    SemanticClassification,
    classify_semantic,
    embed_text,
)


class TestEmbedding:
    def test_embed_text_returns_correct_shape(self) -> None:
        vec = embed_text("This is a test document.")
        assert vec.shape == (EMBEDDING_DIM,)
        assert vec.dtype == np.float32

    def test_embeddings_are_normalized(self) -> None:
        vec = embed_text("Commercial real estate loan agreement.")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01

    def test_similar_texts_have_high_similarity(self) -> None:
        vec1 = embed_text("The property has soil contamination from industrial use.")
        vec2 = embed_text("Ground pollution was found due to factory operations.")
        similarity = float(vec1 @ vec2)
        assert similarity > 0.5

    def test_dissimilar_texts_have_low_similarity(self) -> None:
        vec1 = embed_text("The property has soil contamination from industrial use.")
        vec2 = embed_text("The interest rate is 4.5% per annum.")
        similarity = float(vec1 @ vec2)
        assert similarity < 0.4


class TestSemanticClassification:
    def test_returns_classification_result(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["valuation_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_semantic(text)

        assert isinstance(result, SemanticClassification)
        assert result.privacy_level in {"Public", "Confidential", "Secret"}
        assert result.environmental_impact in {"None", "Low", "Medium", "High"}
        assert isinstance(result.industries, list)
        assert len(result.embedding) == EMBEDDING_DIM

    def test_invoice_is_not_secret(self, scenario: LoanScenario) -> None:
        """Invoices should not be classified as Secret."""
        pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_semantic(text)
        assert result.privacy_level != "Secret"

    def test_contract_detects_legal_industry(self, scenario: LoanScenario) -> None:
        """Contracts should include Legal and Compliance in industries."""
        pdf_bytes = DOCUMENT_TYPES["contract"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_semantic(text)
        has_legal = "Legal and Compliance" in result.industries
        has_finance = "Financial Services" in result.industries
        assert has_legal or has_finance

    def test_valuation_detects_real_estate(self, scenario: LoanScenario) -> None:
        """Valuation reports should include Real Estate in industries."""
        pdf_bytes = DOCUMENT_TYPES["valuation_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_semantic(text)
        assert "Real Estate" in result.industries

    def test_environmental_text_scores_higher(self) -> None:
        """Text with environmental content should score higher on env impact."""
        clean_text = (
            "This is a standard office building in a modern business park. "
            "The property is well maintained with no known issues. "
            "The loan terms are straightforward with standard covenants."
        )
        dirty_text = (
            "The property is located on a former chemical plant site. "
            "Soil sampling revealed heavy metal contamination in the "
            "topsoil. Groundwater monitoring shows elevated levels of "
            "benzene. Asbestos was found in the building insulation. "
            "The site is in a flood-prone polder below sea level."
        )

        clean_result = classify_semantic(clean_text)
        dirty_result = classify_semantic(dirty_text)

        # The contaminated site should have higher environmental scores
        assert dirty_result.environmental_scores["High"] > clean_result.environmental_scores["High"]

    def test_embedding_stored_for_vector_search(self, scenario: LoanScenario) -> None:
        """The embedding should be stored for later pgvector queries."""
        pdf_bytes = DOCUMENT_TYPES["valuation_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_semantic(text)

        assert len(result.embedding) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in result.embedding)

    def test_all_document_types_classifiable(self, scenario: LoanScenario) -> None:
        """All document types should produce valid semantic classifications."""
        for doc_type, config in DOCUMENT_TYPES.items():
            pdf_bytes = config["generator"](scenario)
            text = extract_text(pdf_bytes).text
            result = classify_semantic(text)

            assert result.privacy_level in {"Public", "Confidential", "Secret"}, (
                f"{doc_type}: invalid privacy level {result.privacy_level}"
            )
            assert result.environmental_impact in {"None", "Low", "Medium", "High"}, (
                f"{doc_type}: invalid env impact {result.environmental_impact}"
            )
            assert len(result.industries) > 0, f"{doc_type}: no industries detected"
