"""Extract worker — consumes from raw-docs, extracts text, publishes to extracted.

Runs as an infinite loop reading from the Redis 'raw-docs' stream.
For each message:
    1. Decode the base64 PDF
    2. Extract text using PyMuPDF
    3. Publish extracted text + metadata to the 'extracted' stream
    4. Acknowledge the original message

Graceful shutdown on SIGTERM (K8s sends this before killing the pod).
"""

from __future__ import annotations

import logging
import os

from worker.extract import extract_text
from worker.queue import (
    GROUP_EXTRACT,
    STREAM_EXTRACTED,
    STREAM_RAW,
    ShutdownRequestedError,
    ack,
    consume,
    decode_pdf,
    ensure_consumer_group,
    get_redis,
    publish,
    set_doc_status,
    setup_shutdown_handler,
)

logger = logging.getLogger(__name__)

CONSUMER_NAME = os.environ.get("CONSUMER_NAME", f"extract-{os.getpid()}")


def process_message(r: object, msg: object) -> None:
    """Process a single raw-docs message."""
    doc_id = msg.data["doc_id"]
    filename = msg.data["filename"]
    pdf_b64 = msg.data["pdf_b64"]

    logger.info("Extracting: %s (%s)", filename, doc_id)
    set_doc_status(r, doc_id, "extracting")

    pdf_bytes = decode_pdf(pdf_b64)
    result = extract_text(pdf_bytes)

    # Publish to next stage
    publish(
        r,
        STREAM_EXTRACTED,
        {
            "doc_id": doc_id,
            "filename": filename,
            "text": result.text,
            "page_count": result.page_count,
            "word_count": result.word_count,
            "pdf_b64": pdf_b64,  # pass through for blob storage
        },
    )

    ack(r, STREAM_RAW, GROUP_EXTRACT, msg.message_id)
    logger.info(
        "Extracted: %s — %d words, %d pages", filename, result.word_count, result.page_count
    )


def run() -> None:
    """Main worker loop."""
    setup_shutdown_handler()

    r = get_redis()
    ensure_consumer_group(r, STREAM_RAW, GROUP_EXTRACT)

    logger.info("Extract worker started, consumer=%s", CONSUMER_NAME)

    try:
        while True:
            messages = consume(r, STREAM_RAW, GROUP_EXTRACT, CONSUMER_NAME)
            for msg in messages:
                try:
                    process_message(r, msg)
                except Exception:
                    logger.exception("Failed to process message %s", msg.message_id)
                    set_doc_status(r, msg.data.get("doc_id", "unknown"), "failed")
                    ack(r, STREAM_RAW, GROUP_EXTRACT, msg.message_id)
    except ShutdownRequestedError:
        logger.info("Extract worker shutting down gracefully")
    finally:
        r.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run()
