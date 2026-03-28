"""FastAPI gateway for the DocumentStream document processing pipeline.

Provides REST endpoints for:
- Uploading PDF documents for processing
- Checking processing status
- Viewing classification results
- Health checks for K8s probes
- Generating test documents on demand
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import jinja2
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(
    title="DocumentStream",
    description="Document processing pipeline for commercial real estate loan documents",
    version="0.1.0",
)

# In-memory store for now — will be replaced by Redis + PostgreSQL
_documents: dict[str, dict] = {}

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CLASSIFYING = "classifying"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    # Rule-based classification
    classification: str | None = None
    confidence: float | None = None
    # Semantic classification
    semantic_privacy: str | None = None
    semantic_privacy_confidence: float | None = None
    environmental_impact: str | None = None
    environmental_confidence: float | None = None
    industries: list[str] | None = None
    word_count: int | None = None
    submitted_at: str
    completed_at: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class GenerateRequest(BaseModel):
    count: int = 10


class GenerateResponse(BaseModel):
    scenarios_created: int
    documents_created: int
    loan_ids: list[str]


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint for K8s liveness/readiness probes."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.now(UTC).isoformat(),
    )


@app.post("/api/documents", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(),  # noqa: B008
) -> DocumentResponse:
    """Upload a PDF document for processing.

    The document is queued for the extract -> classify -> store pipeline.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    document_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # For local dev: process synchronously. In K8s: push to Redis queue.
    from worker.classify import classify_text
    from worker.extract import extract_text
    from worker.semantic import classify_semantic

    extraction = extract_text(content)
    rules = classify_text(extraction.text)
    semantic = classify_semantic(extraction.text)

    doc = {
        "document_id": document_id,
        "filename": file.filename,
        "status": DocumentStatus.COMPLETED,
        "classification": rules.classification,
        "confidence": rules.confidence,
        "semantic_privacy": semantic.privacy_level,
        "semantic_privacy_confidence": semantic.privacy_confidence,
        "environmental_impact": semantic.environmental_impact,
        "environmental_confidence": semantic.environmental_confidence,
        "industries": semantic.industries,
        "word_count": extraction.word_count,
        "submitted_at": now,
        "completed_at": datetime.now(UTC).isoformat(),
        "matched_keywords": rules.matched_keywords,
        "scores": rules.scores,
    }
    _documents[document_id] = doc

    return DocumentResponse(**{k: v for k, v in doc.items() if k in DocumentResponse.model_fields})


@app.get("/api/documents", response_model=list[DocumentResponse])
def list_documents(
    classification: str | None = Query(None, description="Filter by classification level"),
    limit: int = Query(50, ge=1, le=500),
) -> list[DocumentResponse]:
    """List processed documents, optionally filtered by classification."""
    docs = list(_documents.values())
    if classification:
        docs = [d for d in docs if d.get("classification") == classification]
    docs.sort(key=lambda d: d["submitted_at"], reverse=True)
    return [
        DocumentResponse(**{k: v for k, v in d.items() if k in DocumentResponse.model_fields})
        for d in docs[:limit]
    ]


@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    """Get details of a specific document."""
    doc = _documents.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**{k: v for k, v in doc.items() if k in DocumentResponse.model_fields})


@app.post("/api/generate", response_model=GenerateResponse)
def generate_documents(request: GenerateRequest) -> GenerateResponse:
    """Generate synthetic loan scenarios and process them.

    Used for demos and load testing — generates N complete loan scenarios
    (5 documents each) and processes them immediately.
    """
    from generator.scenario import LoanScenario
    from generator.templates import DOCUMENT_TYPES
    from worker.classify import classify_text
    from worker.extract import extract_text
    from worker.semantic import classify_semantic

    loan_ids: list[str] = []

    for _ in range(request.count):
        scenario = LoanScenario.generate()
        loan_ids.append(scenario.loan_id)

        for doc_type, config in DOCUMENT_TYPES.items():
            pdf_bytes = config["generator"](scenario)
            extraction = extract_text(pdf_bytes)
            rules = classify_text(extraction.text)
            semantic = classify_semantic(extraction.text)

            document_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()

            _documents[document_id] = {
                "document_id": document_id,
                "filename": f"{scenario.loan_id}/{doc_type}.pdf",
                "status": DocumentStatus.COMPLETED,
                "classification": rules.classification,
                "confidence": rules.confidence,
                "semantic_privacy": semantic.privacy_level,
                "semantic_privacy_confidence": semantic.privacy_confidence,
                "environmental_impact": semantic.environmental_impact,
                "environmental_confidence": semantic.environmental_confidence,
                "industries": semantic.industries,
                "word_count": extraction.word_count,
                "submitted_at": now,
                "completed_at": now,
                "loan_id": scenario.loan_id,
                "doc_type": doc_type,
                "matched_keywords": rules.matched_keywords,
                "scores": rules.scores,
            }

    return GenerateResponse(
        scenarios_created=request.count,
        documents_created=request.count * len(DOCUMENT_TYPES),
        loan_ids=loan_ids,
    )


@app.get("/", response_class=HTMLResponse)
def web_ui() -> str:
    """Simple web UI for the demo."""
    template = jinja2.Template((_TEMPLATE_DIR / "index.html").read_text())

    docs = sorted(
        _documents.values(),
        key=lambda d: d["submitted_at"],
        reverse=True,
    )[:100]

    loan_ids = {d.get("loan_id", "") for d in _documents.values()}
    stats = {
        "total": len(_documents),
        "loans": len(loan_ids - {""}),
        "public": sum(1 for d in _documents.values() if d.get("classification") == "Public"),
        "confidential": sum(
            1 for d in _documents.values() if d.get("classification") == "Confidential"
        ),
        "secret": sum(1 for d in _documents.values() if d.get("classification") == "Secret"),
        "env_high": sum(1 for d in _documents.values() if d.get("environmental_impact") == "High"),
    }

    return template.render(documents=docs, stats=stats)
