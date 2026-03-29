"""Tests for the Redis Streams queue module.

Uses unittest.mock to mock the Redis connection — these are unit tests
that verify the queue module's logic without requiring a running Redis.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from worker.queue import (
    StreamMessage,
    ack,
    consume,
    decode_pdf,
    encode_pdf,
    ensure_consumer_group,
    get_doc_status,
    publish,
    set_doc_status,
)


class TestEncodeDecode:
    """Test base64 encoding/decoding of PDF bytes."""

    def test_roundtrip(self) -> None:
        original = b"%PDF-1.4 fake pdf content here"
        encoded = encode_pdf(original)
        assert isinstance(encoded, str)
        decoded = decode_pdf(encoded)
        assert decoded == original

    def test_empty_bytes(self) -> None:
        encoded = encode_pdf(b"")
        assert decode_pdf(encoded) == b""

    def test_binary_content(self) -> None:
        binary = bytes(range(256))
        assert decode_pdf(encode_pdf(binary)) == binary


class TestEnsureConsumerGroup:
    """Test consumer group creation."""

    def test_creates_group(self) -> None:
        r = MagicMock()
        ensure_consumer_group(r, "test-stream", "test-group")
        r.xgroup_create.assert_called_once_with("test-stream", "test-group", id="0", mkstream=True)

    def test_ignores_existing_group(self) -> None:
        r = MagicMock()
        import redis as redis_lib

        r.xgroup_create.side_effect = redis_lib.ResponseError(
            "BUSYGROUP Consumer Group name already exists"
        )
        # Should not raise
        ensure_consumer_group(r, "test-stream", "test-group")

    def test_raises_other_errors(self) -> None:
        r = MagicMock()
        import redis as redis_lib

        r.xgroup_create.side_effect = redis_lib.ResponseError("some other error")
        with pytest.raises(redis_lib.ResponseError, match="some other error"):
            ensure_consumer_group(r, "test-stream", "test-group")


class TestPublish:
    """Test publishing messages to a stream."""

    def test_publish_simple(self) -> None:
        r = MagicMock()
        r.xadd.return_value = "1234-0"
        msg_id = publish(r, "my-stream", {"doc_id": "abc", "filename": "test.pdf"})
        assert msg_id == "1234-0"
        r.xadd.assert_called_once_with("my-stream", {"doc_id": "abc", "filename": "test.pdf"})

    def test_publish_serializes_complex_types(self) -> None:
        r = MagicMock()
        r.xadd.return_value = "1234-0"
        publish(
            r,
            "my-stream",
            {
                "doc_id": "abc",
                "keywords": ["loan", "property"],
                "scores": {"Public": 1.0, "Secret": 2.0},
                "count": 42,
                "rate": 0.95,
            },
        )
        call_args = r.xadd.call_args[0][1]
        assert call_args["doc_id"] == "abc"
        assert call_args["keywords"] == '["loan", "property"]'
        assert call_args["scores"] == '{"Public": 1.0, "Secret": 2.0}'
        assert call_args["count"] == "42"
        assert call_args["rate"] == "0.95"


class TestConsume:
    """Test consuming messages from a stream."""

    def test_consume_returns_messages(self) -> None:
        r = MagicMock()
        r.xreadgroup.return_value = [
            (
                "my-stream",
                [
                    ("1234-0", {"doc_id": "abc", "filename": "test.pdf"}),
                    ("1234-1", {"doc_id": "def", "filename": "test2.pdf"}),
                ],
            )
        ]
        messages = consume(r, "my-stream", "my-group", "consumer-1")
        assert len(messages) == 2
        assert messages[0].message_id == "1234-0"
        assert messages[0].data["doc_id"] == "abc"
        assert messages[1].message_id == "1234-1"

    def test_consume_empty_result(self) -> None:
        r = MagicMock()
        r.xreadgroup.return_value = None
        messages = consume(r, "my-stream", "my-group", "consumer-1")
        assert messages == []

    def test_consume_uses_block_ms(self) -> None:
        r = MagicMock()
        r.xreadgroup.return_value = None
        consume(r, "my-stream", "my-group", "consumer-1", block_ms=5000)
        r.xreadgroup.assert_called_once_with(
            "my-group", "consumer-1", {"my-stream": ">"}, count=1, block=5000
        )


class TestAck:
    """Test message acknowledgment."""

    def test_ack(self) -> None:
        r = MagicMock()
        ack(r, "my-stream", "my-group", "1234-0")
        r.xack.assert_called_once_with("my-stream", "my-group", "1234-0")


class TestDocStatus:
    """Test document status tracking."""

    def test_set_status(self) -> None:
        r = MagicMock()
        set_doc_status(r, "abc-123", "extracting")
        r.hset.assert_called_once()
        call_kwargs = r.hset.call_args
        mapping = call_kwargs[1]["mapping"]
        assert mapping["status"] == "extracting"
        assert "updated_at" in mapping

    def test_set_status_with_extra(self) -> None:
        r = MagicMock()
        set_doc_status(r, "abc-123", "completed", classification="Secret", confidence="0.85")
        mapping = r.hset.call_args[1]["mapping"]
        assert mapping["status"] == "completed"
        assert mapping["classification"] == "Secret"
        assert mapping["confidence"] == "0.85"

    def test_get_status_exists(self) -> None:
        r = MagicMock()
        r.hgetall.return_value = {"status": "classifying", "updated_at": "123.456"}
        result = get_doc_status(r, "abc-123")
        assert result == {"status": "classifying", "updated_at": "123.456"}
        r.hgetall.assert_called_once_with("doc:abc-123")

    def test_get_status_not_found(self) -> None:
        r = MagicMock()
        r.hgetall.return_value = {}
        result = get_doc_status(r, "nonexistent")
        assert result is None


class TestStreamMessage:
    """Test StreamMessage helper methods."""

    def test_get_json(self) -> None:
        msg = StreamMessage(
            message_id="1234-0",
            data={"keywords": '["loan", "property"]', "scores": '{"Public": 1.0}'},
        )
        assert msg.get_json("keywords") == ["loan", "property"]
        assert msg.get_json("scores") == {"Public": 1.0}
