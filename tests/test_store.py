"""Tests for the store module.

Tests document storage logic with mocked PostgreSQL connection.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from worker.store import DocumentRecord, infer_doc_type, store_document


@pytest.fixture
def sample_record() -> DocumentRecord:
    """Create a sample document record for testing."""
    return DocumentRecord(
        doc_id="store-test-1",
        filename="LOAN-2025-001/loan_application.pdf",
        text="sample document text for testing",
        page_count=2,
        word_count=6,
        classification="Confidential",
        confidence=0.85,
        matched_keywords={"Confidential": ["loan application"]},
        scores={"Public": 1.0, "Confidential": 5.0, "Secret": 0.0},
        semantic_privacy="Confidential",
        semantic_privacy_confidence=0.72,
        environmental_impact="Low",
        environmental_confidence=0.55,
        industries=["Real Estate", "Financial Services"],
        embedding=[0.1] * 384,
        doc_type="loan_application",
    )


class TestStoreDocument:
    def test_store_with_provided_connection(self, sample_record: DocumentRecord) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store_document(sample_record, mock_conn)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT INTO documents" in sql
        assert "ON CONFLICT (doc_id) DO NOTHING" in sql
        assert params["doc_id"] == "store-test-1"
        assert params["doc_type"] == "loan_application"
        assert params["classification"] == "Confidential"
        assert params["embedding"] == str([0.1] * 384)
        assert params["industries"] == json.dumps(["Real Estate", "Financial Services"])
        assert params["blob_url"] is None

        mock_conn.commit.assert_called_once()
        # Should NOT close the connection we provided
        mock_conn.close.assert_not_called()

    @patch("worker.store.psycopg")
    def test_store_creates_connection_if_none(
        self, mock_psycopg: MagicMock, sample_record: DocumentRecord
    ) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store_document(sample_record)

        mock_psycopg.connect.assert_called_once()
        mock_conn.commit.assert_called_once()
        # Should close the connection it created
        mock_conn.close.assert_called_once()


class TestDocumentRecord:
    def test_fields(self, sample_record: DocumentRecord) -> None:
        assert sample_record.doc_id == "store-test-1"
        assert sample_record.page_count == 2
        assert len(sample_record.embedding) == 384
        assert sample_record.pdf_bytes is None
        assert sample_record.doc_type == "loan_application"
        assert sample_record.blob_url is None

    def test_with_pdf_bytes(self) -> None:
        record = DocumentRecord(
            doc_id="test",
            filename="test.pdf",
            text="text",
            page_count=1,
            word_count=1,
            classification="Public",
            confidence=1.0,
            matched_keywords={},
            scores={},
            semantic_privacy="Public",
            semantic_privacy_confidence=1.0,
            environmental_impact="None",
            environmental_confidence=1.0,
            industries=[],
            embedding=[],
            pdf_bytes=b"fake pdf",
        )
        assert record.pdf_bytes == b"fake pdf"

    def test_with_blob_url(self) -> None:
        record = DocumentRecord(
            doc_id="test",
            filename="test.pdf",
            text="text",
            page_count=1,
            word_count=1,
            classification="Public",
            confidence=1.0,
            matched_keywords={},
            scores={},
            semantic_privacy="Public",
            semantic_privacy_confidence=1.0,
            environmental_impact="None",
            environmental_confidence=1.0,
            industries=[],
            embedding=[],
            doc_type="invoice",
            blob_url="test/test.pdf",
        )
        assert record.doc_type == "invoice"
        assert record.blob_url == "test/test.pdf"


class TestInferDocType:
    def test_loan_application(self) -> None:
        assert infer_doc_type("LOAN-2025-001/loan_application.pdf") == "loan_application"

    def test_valuation_report(self) -> None:
        assert infer_doc_type("LOAN-2025-001/valuation_report.pdf") == "valuation_report"

    def test_kyc_report(self) -> None:
        assert infer_doc_type("LOAN-2025-001/kyc_report.pdf") == "kyc_report"

    def test_contract(self) -> None:
        assert infer_doc_type("LOAN-2025-001/contract.pdf") == "contract"

    def test_invoice(self) -> None:
        assert infer_doc_type("LOAN-2025-001/invoice.pdf") == "invoice"

    def test_unknown_type(self) -> None:
        assert infer_doc_type("random-file.pdf") == "unknown"

    def test_bare_filename(self) -> None:
        assert infer_doc_type("contract.pdf") == "contract"


class TestUploadBlob:
    def test_no_blob_connection_string(self) -> None:
        from worker.store import upload_blob

        result = upload_blob("doc-1", "test.pdf", b"content")
        assert result is None

    @patch("worker.store.BLOB_CONNECTION_STRING", "UseDevelopmentStorage=true")
    @patch("azure.storage.blob.BlobServiceClient")
    def test_successful_upload(self, mock_blob_class: MagicMock) -> None:
        from worker.store import upload_blob

        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob_class.from_connection_string.return_value = mock_service
        mock_service.get_container_client.return_value = mock_container

        result = upload_blob("doc-1", "test.pdf", b"pdf-content", doc_type="invoice")

        assert result == "test.pdf"
        mock_container.upload_blob.assert_called_once_with(
            "test.pdf", b"pdf-content", overwrite=True
        )
