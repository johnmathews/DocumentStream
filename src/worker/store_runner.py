"""Store worker — consumes from classified, persists to PostgreSQL + Blob Storage.

Runs as an infinite loop reading from the Redis 'classified' stream.
For each message:
    1. Parse the classification results
    2. Insert into PostgreSQL (metadata + pgvector embedding)
    3. Optionally upload original PDF to Azure Blob Storage
    4. Update document status to 'completed'
    5. Acknowledge the original message
"""

from __future__ import annotations

import json
import logging
import os

import psycopg

from worker.queue import (
    GROUP_STORE,
    STREAM_CLASSIFIED,
    ShutdownRequestedError,
    ack,
    consume,
    decode_pdf,
    ensure_consumer_group,
    get_redis,
    set_doc_status,
    setup_shutdown_handler,
)
from worker.store import DATABASE_URL, DocumentRecord, store_document, upload_blob

logger = logging.getLogger(__name__)

CONSUMER_NAME = os.environ.get("CONSUMER_NAME", f"store-{os.getpid()}")


def _parse_json_field(data: dict[str, str], key: str) -> list | dict:
    """Parse a JSON field from a stream message, handling both raw and serialized."""
    value = data.get(key, "")
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def process_message(r: object, msg: object, conn: psycopg.Connection) -> None:
    """Process a single classified message."""
    doc_id = msg.data["doc_id"]
    filename = msg.data["filename"]

    logger.info("Storing: %s (%s)", filename, doc_id)
    set_doc_status(r, doc_id, "storing")

    record = DocumentRecord(
        doc_id=doc_id,
        filename=filename,
        text=msg.data["text"],
        page_count=int(msg.data["page_count"]),
        word_count=int(msg.data["word_count"]),
        classification=msg.data["classification"],
        confidence=float(msg.data["confidence"]),
        matched_keywords=_parse_json_field(msg.data, "matched_keywords"),
        scores=_parse_json_field(msg.data, "scores"),
        semantic_privacy=msg.data["semantic_privacy"],
        semantic_privacy_confidence=float(msg.data["semantic_privacy_confidence"]),
        environmental_impact=msg.data["environmental_impact"],
        environmental_confidence=float(msg.data["environmental_confidence"]),
        industries=_parse_json_field(msg.data, "industries"),
        embedding=_parse_json_field(msg.data, "embedding"),
    )

    store_document(record, conn)

    # Upload original PDF to blob storage
    pdf_bytes = decode_pdf(msg.data["pdf_b64"])
    upload_blob(doc_id, filename, pdf_bytes)

    set_doc_status(
        r,
        doc_id,
        "completed",
        classification=record.classification,
        confidence=str(record.confidence),
        environmental_impact=record.environmental_impact,
        word_count=str(record.word_count),
    )

    ack(r, STREAM_CLASSIFIED, GROUP_STORE, msg.message_id)
    logger.info("Stored: %s — %s", filename, record.classification)


def run() -> None:
    """Main worker loop."""
    setup_shutdown_handler()

    r = get_redis()
    conn = psycopg.connect(DATABASE_URL)
    ensure_consumer_group(r, STREAM_CLASSIFIED, GROUP_STORE)

    logger.info("Store worker started, consumer=%s", CONSUMER_NAME)

    try:
        while True:
            messages = consume(r, STREAM_CLASSIFIED, GROUP_STORE, CONSUMER_NAME)
            for msg in messages:
                try:
                    process_message(r, msg, conn)
                except Exception:
                    logger.exception("Failed to process message %s", msg.message_id)
                    set_doc_status(r, msg.data.get("doc_id", "unknown"), "failed")
                    ack(r, STREAM_CLASSIFIED, GROUP_STORE, msg.message_id)
    except ShutdownRequestedError:
        logger.info("Store worker shutting down gracefully")
    finally:
        conn.close()
        r.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run()
