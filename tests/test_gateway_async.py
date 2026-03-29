"""Tests for the gateway in async (Redis) mode.

Tests the dual-mode behavior: when REDIS_URL is set, the gateway should
publish to Redis Streams instead of processing synchronously.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def async_client() -> TestClient:
    """Create a test client with REDIS_URL set (async mode)."""
    import gateway.app as app_module

    # Save original state
    orig_redis_url = app_module._REDIS_URL
    orig_redis_conn = app_module._redis_conn
    orig_documents = app_module._documents.copy()

    # Enable async mode
    app_module._REDIS_URL = "redis://fake:6379"
    mock_redis = MagicMock()
    mock_redis.xadd.return_value = "1234-0"
    app_module._redis_conn = mock_redis
    app_module._documents.clear()

    client = TestClient(app_module.app)

    yield client

    # Restore original state
    app_module._REDIS_URL = orig_redis_url
    app_module._redis_conn = orig_redis_conn
    app_module._documents.clear()
    app_module._documents.update(orig_documents)


@pytest.fixture
def mock_redis_conn() -> MagicMock:
    """Get the mock Redis connection from the async client."""
    import gateway.app as app_module

    return app_module._redis_conn


class TestAsyncMode:
    def test_is_async_mode(self, async_client: TestClient) -> None:
        import gateway.app as app_module

        assert app_module.is_async_mode() is True

    def test_health_reports_async(self, async_client: TestClient) -> None:
        response = async_client.get("/health")
        assert response.status_code == 200
        assert response.json()["mode"] == "async"

    def test_upload_returns_queued(self, async_client: TestClient) -> None:
        from generator.scenario import LoanScenario
        from generator.templates import DOCUMENT_TYPES

        scenario = LoanScenario.generate()
        pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)

        response = async_client.post(
            "/api/documents",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["filename"] == "test.pdf"
        assert data["classification"] is None  # not yet classified

    def test_upload_publishes_to_redis(
        self, async_client: TestClient, mock_redis_conn: MagicMock
    ) -> None:
        from generator.scenario import LoanScenario
        from generator.templates import DOCUMENT_TYPES

        scenario = LoanScenario.generate()
        pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)

        async_client.post(
            "/api/documents",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        # Should publish to raw-docs stream
        mock_redis_conn.xadd.assert_called()
        call_args = mock_redis_conn.xadd.call_args[0]
        assert call_args[0] == "raw-docs"
        assert "doc_id" in call_args[1]
        assert "pdf_b64" in call_args[1]

    def test_get_document_checks_redis_status(self, async_client: TestClient) -> None:
        import gateway.app as app_module

        # Simulate a queued document
        app_module._documents["test-doc-1"] = {
            "document_id": "test-doc-1",
            "filename": "test.pdf",
            "status": "queued",
            "submitted_at": "2026-01-01T00:00:00",
        }

        # Mock Redis returning updated status
        app_module._redis_conn.hgetall.return_value = {
            "status": "classifying",
            "filename": "test.pdf",
            "submitted_at": "2026-01-01T00:00:00",
        }

        response = async_client.get("/api/documents/test-doc-1")
        assert response.status_code == 200
        assert response.json()["status"] == "classifying"


class TestSyncMode:
    """Verify sync mode still works when REDIS_URL is not set."""

    def test_health_reports_sync(self) -> None:
        import gateway.app as app_module

        orig = app_module._REDIS_URL
        app_module._REDIS_URL = ""
        app_module._documents.clear()

        try:
            client = TestClient(app_module.app)
            response = client.get("/health")
            assert response.json()["mode"] == "sync"
        finally:
            app_module._REDIS_URL = orig
            app_module._documents.clear()

    def test_is_not_async_mode(self) -> None:
        import gateway.app as app_module

        orig = app_module._REDIS_URL
        app_module._REDIS_URL = ""
        try:
            assert app_module.is_async_mode() is False
        finally:
            app_module._REDIS_URL = orig
