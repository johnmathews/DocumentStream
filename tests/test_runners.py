"""Tests for the worker runners (extract, classify, store).

Tests the process_message functions directly with mocked Redis connections.
This verifies the business logic of each pipeline stage without requiring
running infrastructure.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from worker.queue import StreamMessage, encode_pdf


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis connection."""
    r = MagicMock()
    r.xadd.return_value = "1234-0"
    return r


@pytest.fixture
def sample_pdf_b64(scenario) -> str:
    """Generate a real PDF and return as base64."""
    from generator.templates import DOCUMENT_TYPES

    pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)
    return encode_pdf(pdf_bytes)


class TestExtractRunner:
    def test_process_message(self, mock_redis: MagicMock, sample_pdf_b64: str) -> None:
        from worker.extract_runner import process_message

        msg = StreamMessage(
            message_id="1000-0",
            data={
                "doc_id": "test-doc-1",
                "filename": "invoice.pdf",
                "pdf_b64": sample_pdf_b64,
            },
        )

        process_message(mock_redis, msg)

        # Should publish to extracted stream
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args[0]
        assert call_args[0] == "extracted"
        published_data = call_args[1]
        assert published_data["doc_id"] == "test-doc-1"
        assert published_data["filename"] == "invoice.pdf"
        assert "text" in published_data
        assert int(published_data["word_count"]) > 0

        # Should ack the original message
        mock_redis.xack.assert_called_once()

        # Should set status to extracting
        status_calls = mock_redis.hset.call_args_list
        assert any(call[1]["mapping"]["status"] == "extracting" for call in status_calls)


class TestClassifyRunner:
    def test_process_message(self, mock_redis: MagicMock, sample_pdf_b64: str) -> None:
        from worker.classify_runner import process_message
        from worker.extract import extract_text
        from worker.queue import decode_pdf

        # Pre-extract text (normally the extract runner does this)
        pdf_bytes = decode_pdf(sample_pdf_b64)
        extraction = extract_text(pdf_bytes)

        msg = StreamMessage(
            message_id="2000-0",
            data={
                "doc_id": "test-doc-2",
                "filename": "invoice.pdf",
                "text": extraction.text,
                "page_count": str(extraction.page_count),
                "word_count": str(extraction.word_count),
                "pdf_b64": sample_pdf_b64,
            },
        )

        process_message(mock_redis, msg)

        # Should publish to classified stream
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args[0]
        assert call_args[0] == "classified"
        published_data = call_args[1]
        assert published_data["doc_id"] == "test-doc-2"
        assert published_data["classification"] in ("Public", "Confidential", "Secret")
        assert "embedding" in published_data
        assert "industries" in published_data

        # Should ack the original message
        mock_redis.xack.assert_called_once()


class TestStoreRunner:
    @patch("worker.store_runner.psycopg")
    def test_process_message(
        self, mock_psycopg: MagicMock, mock_redis: MagicMock, sample_pdf_b64: str
    ) -> None:
        from worker.store_runner import process_message

        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        msg = StreamMessage(
            message_id="3000-0",
            data={
                "doc_id": "test-doc-3",
                "filename": "invoice.pdf",
                "text": "sample document text",
                "page_count": "2",
                "word_count": "100",
                "classification": "Public",
                "confidence": "0.85",
                "matched_keywords": json.dumps({"Public": ["invoice"]}),
                "scores": json.dumps({"Public": 3.0, "Confidential": 1.0, "Secret": 0.0}),
                "semantic_privacy": "Public",
                "semantic_privacy_confidence": "0.75",
                "environmental_impact": "None",
                "environmental_confidence": "0.6",
                "industries": json.dumps(["Financial Services"]),
                "embedding": json.dumps([0.1] * 384),
                "pdf_b64": sample_pdf_b64,
            },
        )

        process_message(mock_redis, msg, mock_conn)

        # Should execute INSERT
        mock_conn.cursor.return_value.__enter__.return_value.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

        # Should ack the original message
        mock_redis.xack.assert_called_once()

        # Should set status to completed
        status_calls = mock_redis.hset.call_args_list
        assert any(call[1]["mapping"]["status"] == "completed" for call in status_calls)
