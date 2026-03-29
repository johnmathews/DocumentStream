"""Storage module — persists classified documents to PostgreSQL.

Inserts document metadata, classification results, and the 384-dimensional
embedding vector into the documents table. The embedding is stored using
pgvector for later semantic search.

Optionally uploads the original PDF to Azure Blob Storage.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import psycopg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://documentstream:documentstream@localhost:5432/documentstream",
)

BLOB_CONNECTION_STRING = os.environ.get("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER = os.environ.get("BLOB_CONTAINER", "documents")


@dataclass
class DocumentRecord:
    """A fully processed document ready for storage."""

    doc_id: str
    filename: str
    text: str
    page_count: int
    word_count: int
    classification: str
    confidence: float
    matched_keywords: dict[str, list[str]]
    scores: dict[str, float]
    semantic_privacy: str
    semantic_privacy_confidence: float
    environmental_impact: str
    environmental_confidence: float
    industries: list[str]
    embedding: list[float]
    pdf_bytes: bytes | None = None


INSERT_SQL = """
INSERT INTO documents (
    doc_id, filename, text, page_count, word_count,
    classification, confidence, matched_keywords, scores,
    semantic_privacy, semantic_privacy_confidence,
    environmental_impact, environmental_confidence,
    industries, embedding
) VALUES (
    %(doc_id)s, %(filename)s, %(text)s, %(page_count)s, %(word_count)s,
    %(classification)s, %(confidence)s, %(matched_keywords)s, %(scores)s,
    %(semantic_privacy)s, %(semantic_privacy_confidence)s,
    %(environmental_impact)s, %(environmental_confidence)s,
    %(industries)s, %(embedding)s
)
ON CONFLICT (doc_id) DO NOTHING
"""


def store_document(record: DocumentRecord, conn: psycopg.Connection | None = None) -> None:
    """Insert a document record into PostgreSQL.

    Args:
        record: The fully processed document to store.
        conn: Optional existing connection. If None, a new connection is created.
    """
    close_conn = False
    if conn is None:
        conn = psycopg.connect(DATABASE_URL)
        close_conn = True

    try:
        with conn.cursor() as cur:
            cur.execute(
                INSERT_SQL,
                {
                    "doc_id": record.doc_id,
                    "filename": record.filename,
                    "text": record.text,
                    "page_count": record.page_count,
                    "word_count": record.word_count,
                    "classification": record.classification,
                    "confidence": record.confidence,
                    "matched_keywords": json.dumps(record.matched_keywords),
                    "scores": json.dumps(record.scores),
                    "semantic_privacy": record.semantic_privacy,
                    "semantic_privacy_confidence": record.semantic_privacy_confidence,
                    "environmental_impact": record.environmental_impact,
                    "environmental_confidence": record.environmental_confidence,
                    "industries": json.dumps(record.industries),
                    "embedding": str(record.embedding),
                },
            )
        conn.commit()
        logger.info("Stored document %s (%s)", record.doc_id, record.filename)
    finally:
        if close_conn:
            conn.close()


def upload_blob(doc_id: str, filename: str, pdf_bytes: bytes) -> str | None:
    """Upload a PDF to Azure Blob Storage.

    Args:
        doc_id: Document ID (used as blob prefix).
        filename: Original filename.
        pdf_bytes: Raw PDF content.

    Returns:
        Blob URL if upload succeeded, None if blob storage is not configured.
    """
    if not BLOB_CONNECTION_STRING:
        logger.debug("Blob storage not configured, skipping upload for %s", doc_id)
        return None

    try:
        from azure.storage.blob import BlobServiceClient

        blob_service = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        container = blob_service.get_container_client(BLOB_CONTAINER)
        blob_name = f"{doc_id}/{filename}"
        container.upload_blob(blob_name, pdf_bytes, overwrite=True)
        logger.info("Uploaded blob: %s", blob_name)
        return blob_name
    except Exception:
        logger.exception("Failed to upload blob for %s", doc_id)
        return None
