"""Classify worker — consumes from extracted, classifies, publishes to classified.

Runs as an infinite loop reading from the Redis 'extracted' stream.
For each message:
    1. Run rule-based classification (privacy level)
    2. Run semantic classification (environmental impact, industries)
    3. Publish all results to the 'classified' stream
    4. Acknowledge the original message

This worker loads the ONNX embedding model on startup (~90MB),
so it uses more memory than other workers (~300-400MB total).
"""

from __future__ import annotations

import logging
import os

from worker.classify import classify_text
from worker.queue import (
    GROUP_CLASSIFY,
    STREAM_CLASSIFIED,
    STREAM_EXTRACTED,
    ShutdownRequestedError,
    ack,
    consume,
    ensure_consumer_group,
    get_redis,
    publish,
    set_doc_status,
    setup_shutdown_handler,
)
from worker.semantic import classify_semantic

logger = logging.getLogger(__name__)

CONSUMER_NAME = os.environ.get("CONSUMER_NAME", f"classify-{os.getpid()}")


def process_message(r: object, msg: object) -> None:
    """Process a single extracted message."""
    doc_id = msg.data["doc_id"]
    filename = msg.data["filename"]
    text = msg.data["text"]

    logger.info("Classifying: %s (%s)", filename, doc_id)
    set_doc_status(r, doc_id, "classifying")

    rules = classify_text(text)
    semantic = classify_semantic(text)

    publish(
        r,
        STREAM_CLASSIFIED,
        {
            "doc_id": doc_id,
            "filename": filename,
            "text": text,
            "page_count": msg.data["page_count"],
            "word_count": msg.data["word_count"],
            "pdf_b64": msg.data["pdf_b64"],
            # Rule-based results
            "classification": rules.classification,
            "confidence": rules.confidence,
            "matched_keywords": rules.matched_keywords,
            "scores": rules.scores,
            # Semantic results
            "semantic_privacy": semantic.privacy_level,
            "semantic_privacy_confidence": semantic.privacy_confidence,
            "environmental_impact": semantic.environmental_impact,
            "environmental_confidence": semantic.environmental_confidence,
            "industries": semantic.industries,
            "embedding": semantic.embedding,
        },
    )

    ack(r, STREAM_EXTRACTED, GROUP_CLASSIFY, msg.message_id)
    logger.info(
        "Classified: %s — %s (%.1f%%), env=%s",
        filename,
        rules.classification,
        rules.confidence * 100,
        semantic.environmental_impact,
    )


def run() -> None:
    """Main worker loop."""
    setup_shutdown_handler()

    r = get_redis()
    ensure_consumer_group(r, STREAM_EXTRACTED, GROUP_CLASSIFY)

    logger.info("Classify worker started, consumer=%s", CONSUMER_NAME)

    try:
        while True:
            messages = consume(r, STREAM_EXTRACTED, GROUP_CLASSIFY, CONSUMER_NAME)
            for msg in messages:
                try:
                    process_message(r, msg)
                except Exception:
                    logger.exception("Failed to process message %s", msg.message_id)
                    set_doc_status(r, msg.data.get("doc_id", "unknown"), "failed")
                    ack(r, STREAM_EXTRACTED, GROUP_CLASSIFY, msg.message_id)
    except ShutdownRequestedError:
        logger.info("Classify worker shutting down gracefully")
    finally:
        r.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run()
