"""Tests for document classification."""

from generator.scenario import LoanScenario
from generator.templates import DOCUMENT_TYPES
from worker.classify import ClassificationResult, classify_text
from worker.extract import extract_text


class TestClassifyText:
    def test_returns_classification_result(self) -> None:
        result = classify_text("This is a simple test document.")
        assert isinstance(result, ClassificationResult)
        assert result.classification in {"Public", "Confidential", "Secret"}
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_text_defaults_to_confidential(self) -> None:
        result = classify_text("")
        assert result.classification == "Confidential"
        assert result.confidence == 0.0

    def test_invoice_classified_as_public(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert result.classification == "Public"
        assert result.confidence > 0.5

    def test_loan_application_classified_as_confidential(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["loan_application"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert result.classification == "Confidential"

    def test_valuation_report_classified_as_confidential(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["valuation_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert result.classification == "Confidential"

    def test_kyc_report_classified_as_secret(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["kyc_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert result.classification == "Secret"
        assert result.confidence > 0.5

    def test_contract_classified_as_secret(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["contract"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert result.classification == "Secret"

    def test_matched_keywords_are_populated(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["kyc_report"]["generator"](scenario)
        text = extract_text(pdf_bytes).text
        result = classify_text(text)
        assert len(result.matched_keywords["Secret"]) > 0
        assert "kyc" in result.matched_keywords["Secret"]

    def test_all_document_types_classify_correctly(self, scenario: LoanScenario) -> None:
        """Each generated document should classify to its expected level."""
        expected = {
            "loan_application": "Confidential",
            "valuation_report": "Confidential",
            "kyc_report": "Secret",
            "contract": "Secret",
            "invoice": "Public",
        }
        for doc_type, config in DOCUMENT_TYPES.items():
            pdf_bytes = config["generator"](scenario)
            text = extract_text(pdf_bytes).text
            result = classify_text(text)
            assert result.classification == expected[doc_type], (
                f"{doc_type}: expected {expected[doc_type]}, "
                f"got {result.classification} "
                f"(scores: {result.scores})"
            )
