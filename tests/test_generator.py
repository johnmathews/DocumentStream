"""Tests for the document generator."""

from datetime import date

from generator.scenario import Client, LoanScenario, Property
from generator.templates import DOCUMENT_TYPES


class TestProperty:
    def test_generate_returns_property(self) -> None:
        prop = Property.generate()
        assert isinstance(prop, Property)
        assert prop.address
        assert prop.city
        assert prop.floor_area_sqm > 0
        assert prop.year_built >= 1960

    def test_generate_produces_varied_output(self) -> None:
        properties = [Property.generate() for _ in range(10)]
        addresses = {p.address for p in properties}
        assert len(addresses) > 1


class TestClient:
    def test_generate_returns_client(self) -> None:
        client = Client.generate()
        assert isinstance(client, Client)
        assert client.company_name
        assert client.registration_number.startswith("KVK-")
        assert "@" in client.email
        assert client.years_in_business > 0

    def test_email_uses_company_domain(self) -> None:
        client = Client.generate()
        domain = client.email.split("@")[1]
        assert domain.endswith(".nl")


class TestLoanScenario:
    def test_generate_returns_scenario(self, scenario: LoanScenario) -> None:
        assert isinstance(scenario, LoanScenario)
        assert scenario.loan_id.startswith("CRE-")
        assert len(scenario.loan_id) == 10  # CRE- + 6 digits

    def test_dates_are_chronological(self, scenario: LoanScenario) -> None:
        assert scenario.application_date <= scenario.valuation_date
        assert scenario.application_date <= scenario.kyc_date
        assert scenario.kyc_date <= scenario.contract_date
        assert scenario.contract_date <= scenario.invoice_date

    def test_loan_amount_is_reasonable(self, scenario: LoanScenario) -> None:
        assert 1_000_000 <= scenario.loan_amount_eur <= 20_000_000

    def test_ltv_ratio_is_reasonable(self, scenario: LoanScenario) -> None:
        assert 50 < scenario.ltv_ratio_pct < 100

    def test_has_invoice_items(self, scenario: LoanScenario) -> None:
        assert 3 <= len(scenario.invoice_items) <= 6
        for desc, amount in scenario.invoice_items:
            assert isinstance(desc, str)
            assert amount > 0

    def test_base_date_is_respected(self) -> None:
        base = date(2025, 6, 1)
        scenario = LoanScenario.generate(base_date=base)
        assert scenario.application_date == base

    def test_linked_data_is_consistent(self, scenario: LoanScenario) -> None:
        """All documents share the same client and property."""
        assert scenario.client.company_name
        assert scenario.property.address
        assert scenario.loan_id


class TestTemplates:
    def test_all_templates_generate_pdf_bytes(self, scenario: LoanScenario) -> None:
        for doc_type, config in DOCUMENT_TYPES.items():
            pdf_bytes = config["generator"](scenario)
            assert isinstance(pdf_bytes, (bytes, bytearray)), f"{doc_type} did not return bytes"
            assert bytes(pdf_bytes[:4]) == b"%PDF", f"{doc_type} is not a valid PDF"
            assert len(pdf_bytes) > 500, f"{doc_type} PDF is suspiciously small"

    def test_document_types_registry(self) -> None:
        expected = {
            "loan_application",
            "valuation_report",
            "kyc_report",
            "contract",
            "invoice",
        }
        assert set(DOCUMENT_TYPES.keys()) == expected

    def test_classifications_are_correct(self) -> None:
        expected_classifications = {
            "loan_application": "Confidential",
            "valuation_report": "Confidential",
            "kyc_report": "Secret",
            "contract": "Secret",
            "invoice": "Public",
        }
        for doc_type, config in DOCUMENT_TYPES.items():
            assert config["classification"] == expected_classifications[doc_type]

    def test_batch_generation_is_fast(self) -> None:
        """Generating 10 full scenarios (50 PDFs) should take < 10 seconds."""
        import time

        start = time.time()
        for _ in range(10):
            s = LoanScenario.generate()
            for config in DOCUMENT_TYPES.values():
                config["generator"](s)
        elapsed = time.time() - start
        assert elapsed < 10, f"Batch generation took {elapsed:.1f}s (expected < 10s)"
