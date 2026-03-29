"""Redis Streams utilities for the document processing pipeline.

Provides publish/consume/ack operations for the three-stage pipeline:
    raw-docs → extracted → classified

Each stream uses Redis consumer groups for reliable delivery:
- Messages are delivered to exactly one consumer in the group
- Unacknowledged messages are re-delivered after a timeout
- Consumer groups are auto-created with MKSTREAM

Document status is tracked in a Redis hash (doc:{doc_id}) so the gateway
can poll for progress.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import signal
import time
from dataclasses import dataclass
from typing import Any

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all from environment variables)
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

STREAM_RAW = os.environ.get("STREAM_RAW", "raw-docs")
STREAM_EXTRACTED = os.environ.get("STREAM_EXTRACTED", "extracted")
STREAM_CLASSIFIED = os.environ.get("STREAM_CLASSIFIED", "classified")

GROUP_EXTRACT = os.environ.get("GROUP_EXTRACT", "extract-group")
GROUP_CLASSIFY = os.environ.get("GROUP_CLASSIFY", "classify-group")
GROUP_STORE = os.environ.get("GROUP_STORE", "store-group")

# How long to block on XREADGROUP before checking for shutdown (ms)
READ_BLOCK_MS = int(os.environ.get("READ_BLOCK_MS", "2000"))

# Claim pending messages older than this (ms)
CLAIM_MIN_IDLE_MS = int(os.environ.get("CLAIM_MIN_IDLE_MS", "30000"))


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def get_redis(url: str | None = None) -> redis.Redis:
    """Create a Redis connection from URL."""
    return redis.from_url(url or REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Consumer group setup
# ---------------------------------------------------------------------------


def ensure_consumer_group(
    r: redis.Redis,
    stream: str,
    group: str,
) -> None:
    """Create a consumer group if it doesn't already exist.

    Uses MKSTREAM to create the stream if it doesn't exist either.
    """
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("Created consumer group %s on stream %s", group, stream)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group %s already exists on %s", group, stream)
        else:
            raise


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def encode_pdf(pdf_bytes: bytes) -> str:
    """Base64-encode PDF bytes for Redis storage."""
    return base64.b64encode(pdf_bytes).decode("ascii")


def decode_pdf(b64_string: str) -> bytes:
    """Decode base64 PDF string back to bytes."""
    return base64.b64decode(b64_string)


def publish(
    r: redis.Redis,
    stream: str,
    data: dict[str, Any],
) -> str:
    """Publish a message to a Redis stream.

    Args:
        r: Redis connection.
        stream: Stream name.
        data: Message fields. Values must be strings; dicts/lists are
              JSON-serialized automatically.

    Returns:
        The message ID assigned by Redis.
    """
    # Redis streams require string values — serialize complex types
    fields: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            fields[key] = json.dumps(value)
        elif isinstance(value, (int, float)):
            fields[key] = str(value)
        else:
            fields[key] = value

    message_id = r.xadd(stream, fields)
    logger.debug("Published to %s: %s", stream, message_id)
    return message_id


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------


@dataclass
class StreamMessage:
    """A message read from a Redis stream."""

    message_id: str
    data: dict[str, str]

    def get_json(self, key: str) -> Any:
        """Parse a JSON-serialized field."""
        return json.loads(self.data[key])


def consume(
    r: redis.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    count: int = 1,
    block_ms: int | None = None,
) -> list[StreamMessage]:
    """Read new messages from a consumer group.

    Args:
        r: Redis connection.
        stream: Stream name.
        group: Consumer group name.
        consumer: Consumer name (unique per worker instance).
        count: Max messages to read at once.
        block_ms: How long to block waiting for messages (None = use default).

    Returns:
        List of StreamMessage objects (may be empty if block timeout expires).
    """
    if block_ms is None:
        block_ms = READ_BLOCK_MS

    result = r.xreadgroup(
        group,
        consumer,
        {stream: ">"},
        count=count,
        block=block_ms,
    )

    messages: list[StreamMessage] = []
    if result:
        for _stream_name, entries in result:
            for message_id, data in entries:
                messages.append(StreamMessage(message_id=message_id, data=data))

    return messages


def ack(r: redis.Redis, stream: str, group: str, message_id: str) -> None:
    """Acknowledge a message as successfully processed."""
    r.xack(stream, group, message_id)
    logger.debug("Acked %s on %s/%s", message_id, stream, group)


# ---------------------------------------------------------------------------
# Document status tracking
# ---------------------------------------------------------------------------


def set_doc_status(
    r: redis.Redis,
    doc_id: str,
    status: str,
    **extra: str,
) -> None:
    """Update document processing status in Redis.

    Status is stored in a hash at key doc:{doc_id}.
    Extra fields (e.g. classification results) are merged in.
    """
    key = f"doc:{doc_id}"
    fields: dict[str, str] = {"status": status, "updated_at": str(time.time())}
    fields.update(extra)
    r.hset(key, mapping=fields)
    logger.debug("Set status for %s: %s", doc_id, status)


def get_doc_status(r: redis.Redis, doc_id: str) -> dict[str, str] | None:
    """Get the current status of a document.

    Returns:
        Dict of all fields in the status hash, or None if not found.
    """
    key = f"doc:{doc_id}"
    data = r.hgetall(key)
    return data if data else None


# ---------------------------------------------------------------------------
# Graceful shutdown helper
# ---------------------------------------------------------------------------


class ShutdownRequestedError(Exception):
    """Raised when SIGTERM/SIGINT is received."""


def setup_shutdown_handler() -> None:
    """Install signal handlers that raise ShutdownRequestedError.

    Call this at worker startup. The main consume loop should catch
    ShutdownRequestedError and exit cleanly.
    """

    def _handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, requesting shutdown", signum)
        raise ShutdownRequestedError()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
