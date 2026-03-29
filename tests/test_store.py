"""Tests for the store module.

Tests document storage logic with mocked PostgreSQL connection.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from worker.store import DocumentRecord, store_document


@pytest.fixture
def sample_record() -> DocumentRecord:
    """Create a sample document record for testing."""
    return DocumentRecord(
        doc_id="store-test-1",
        filename="test.pdf",
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
        assert params["classification"] == "Confidential"
        assert params["embedding"] == str([0.1] * 384)
        assert params["industries"] == json.dumps(["Real Estate", "Financial Services"])

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


class TestUploadBlob:
    def test_no_blob_connection_string(self) -> None:
        from worker.store import upload_blob

        result = upload_blob("doc-1", "test.pdf", b"content")
        assert result is None
