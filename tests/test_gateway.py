"""Tests for the FastAPI gateway."""

import io

import pytest
from fastapi.testclient import TestClient

from gateway.app import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    from gateway.app import _documents

    _documents.clear()
    return TestClient(app)


class TestHealthCheck:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data


class TestDocumentUpload:
    def test_upload_pdf(self, client: TestClient) -> None:
        from generator.scenario import LoanScenario
        from generator.templates import DOCUMENT_TYPES

        scenario = LoanScenario.generate()
        pdf_bytes = DOCUMENT_TYPES["invoice"]["generator"](scenario)

        response = client.post(
            "/api/documents",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.pdf"
        assert data["status"] == "completed"
        assert data["classification"] in {"Public", "Confidential", "Secret"}
        assert data["word_count"] > 0

    def test_reject_non_pdf(self, client: TestClient) -> None:
        response = client.post(
            "/api/documents",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 400

    def test_reject_empty_file(self, client: TestClient) -> None:
        response = client.post(
            "/api/documents",
            files={"file": ("test.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert response.status_code == 400


class TestGenerateEndpoint:
    def test_generate_creates_documents(self, client: TestClient) -> None:
        response = client.post("/api/generate", json={"count": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["scenarios_created"] == 2
        assert data["documents_created"] == 10
        assert len(data["loan_ids"]) == 2

    def test_generated_documents_are_listed(self, client: TestClient) -> None:
        client.post("/api/generate", json={"count": 1})
        response = client.get("/api/documents")
        assert response.status_code == 200
        docs = response.json()
        assert len(docs) == 5  # 1 scenario = 5 documents


class TestListDocuments:
    def test_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/documents")
        assert response.status_code == 200
        assert response.json() == []

    def test_filter_by_classification(self, client: TestClient) -> None:
        client.post("/api/generate", json={"count": 2})
        response = client.get("/api/documents?classification=Secret")
        assert response.status_code == 200
        docs = response.json()
        assert all(d["classification"] == "Secret" for d in docs)


class TestWebUI:
    def test_web_ui_returns_html(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "DocumentStream" in response.text
        assert "<!DOCTYPE html>" in response.text

    def test_web_ui_shows_documents(self, client: TestClient) -> None:
        client.post("/api/generate", json={"count": 1})
        response = client.get("/")
        assert response.status_code == 200
        assert "CRE-" in response.text
