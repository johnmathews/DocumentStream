"""Tests for text extraction."""

from generator.scenario import LoanScenario
from generator.templates import DOCUMENT_TYPES
from worker.extract import ExtractionResult, extract_text


class TestExtractText:
    def test_extracts_text_from_pdf(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["loan_application"]["generator"](scenario)
        result = extract_text(pdf_bytes)

        assert isinstance(result, ExtractionResult)
        assert result.page_count >= 1
        assert result.word_count > 0
        assert result.char_count > 0
        assert len(result.text) > 0

    def test_extracted_text_contains_scenario_data(self, scenario: LoanScenario) -> None:
        """Extracted text should contain data from the scenario."""
        pdf_bytes = DOCUMENT_TYPES["loan_application"]["generator"](scenario)
        result = extract_text(pdf_bytes)

        assert scenario.loan_id in result.text
        assert scenario.client.company_name in result.text

    def test_valuation_report_has_substantial_text(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["valuation_report"]["generator"](scenario)
        result = extract_text(pdf_bytes)
        assert result.word_count > 300

    def test_contract_has_substantial_text(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["contract"]["generator"](scenario)
        result = extract_text(pdf_bytes)
        assert result.word_count > 500

    def test_kyc_report_has_substantial_text(self, scenario: LoanScenario) -> None:
        pdf_bytes = DOCUMENT_TYPES["kyc_report"]["generator"](scenario)
        result = extract_text(pdf_bytes)
        assert result.word_count > 200

    def test_all_document_types_extractable(self, scenario: LoanScenario) -> None:
        for doc_type, config in DOCUMENT_TYPES.items():
            pdf_bytes = config["generator"](scenario)
            result = extract_text(pdf_bytes)
            assert result.word_count > 0, f"{doc_type} produced no text"
