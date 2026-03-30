"""Locust load test for DocumentStream pipeline.

Usage:
    # Against local dev:
    locust -f locust/locustfile.py --host http://localhost:8000

    # Against AKS (replace with your ingress IP/hostname):
    locust -f locust/locustfile.py --host http://<AKS_INGRESS_IP>

    # Headless (for CI):
    locust -f locust/locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 5 --run-time 2m
"""

from __future__ import annotations

import io

from fpdf import FPDF

from locust import HttpUser, between, task


def _generate_pdf() -> bytes:
    """Generate a minimal valid PDF (single page, one line of text)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Load test document")
    return bytes(pdf.output())


class DocumentStreamUser(HttpUser):
    """Simulates a user interacting with the DocumentStream gateway."""

    wait_time = between(1, 3)

    # Generate the PDF payload once for the entire class so every upload
    # reuses the same bytes instead of rebuilding a PDF per request.
    _pdf_bytes: bytes = _generate_pdf()

    # ------------------------------------------------------------------ #
    # Tasks                                                               #
    # ------------------------------------------------------------------ #

    @task(3)
    def upload_pdf(self) -> None:
        """Upload a small PDF via multipart form — the main pipeline driver."""
        self.client.post(
            "/api/documents",
            files={"file": ("loadtest.pdf", io.BytesIO(self._pdf_bytes), "application/pdf")},
            name="/api/documents [upload]",
        )

    @task(1)
    def generate_scenario(self) -> None:
        """Generate a full loan scenario (5 documents) via the API."""
        self.client.post(
            "/api/generate",
            json={"count": 1},
            name="/api/generate",
        )

    @task(5)
    def list_documents(self) -> None:
        """List processed documents — lightweight read, simulates monitoring."""
        self.client.get(
            "/api/documents",
            name="/api/documents [list]",
        )

    @task(2)
    def health_check(self) -> None:
        """Hit the health endpoint — simulates K8s probes and monitoring."""
        self.client.get(
            "/health",
            name="/health",
        )
