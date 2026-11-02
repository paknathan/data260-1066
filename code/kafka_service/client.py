"""Kafka request/response client used by homework_demo.py and the FastAPI wrapper.

request() creates ONE correlation_id (or keeps the caller's), sends it to s1066_incident_requests with
reply_to=s1066_incident_responses, and waits for the response carrying the same correlation_id.
"""

import json
import threading
import uuid
from typing import Any

from confluent_kafka import Consumer, Producer, TopicPartition

from .common import ensure_topics, flow, get_logger
from .config import BOOTSTRAP, PREFIX, REQUEST_TOPIC, RESPONSE_TOPIC


class KafkaRequestClient:
    """Thread-safe request/response over Kafka; a background thread reads the response topic."""

    def __init__(self, name: str = "client", bootstrap: str = BOOTSTRAP) -> None:
        self.name, self.log = name, get_logger(name)
        ensure_topics({REQUEST_TOPIC: 1, RESPONSE_TOPIC: 1}, bootstrap=bootstrap, log=self.log)
        self.producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
        self.consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": f"{PREFIX}_{name}_{uuid.uuid4().hex[:8]}",
                                  "enable.auto.commit": False})
        parts = self.consumer.list_topics(RESPONSE_TOPIC, timeout=10).topics[RESPONSE_TOPIC].partitions
        # start at the current end of every partition, so only responses to OUR new requests are seen
        assignment = []
        for p in parts:
            _, high = self.consumer.get_watermark_offsets(TopicPartition(RESPONSE_TOPIC, p), timeout=10)
            assignment.append(TopicPartition(RESPONSE_TOPIC, p, high))
        self.consumer.assign(assignment)
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        while not self._stop.is_set():
            m = self.consumer.poll(0.5)
            if m is None or m.error():
                continue
            try:
                resp = json.loads(m.value())
            except (json.JSONDecodeError, TypeError):
                continue
            corr = resp.get("correlation_id")
            with self._lock:
                slot = self._pending.get(corr)
            if slot is not None:  # a response to one of our requests
                slot["response"], slot["partition"], slot["offset"] = resp, m.partition(), m.offset()
                slot["event"].set()

    def request(self, operation: str, data: dict, correlation_id: str | None = None, timeout: float = 20.0) -> dict:
        """Send one request and block until its response (same correlation_id) arrives."""
        corr = correlation_id or str(uuid.uuid4())  # created once, never changed afterwards
        msg = {"correlation_id": corr, "reply_to": RESPONSE_TOPIC, "operation": operation, "data": data}
        slot = {"event": threading.Event()}
        with self._lock:
            self._pending[corr] = slot
        self.producer.produce(REQUEST_TOPIC, key=corr.encode(), value=json.dumps(msg).encode())
        self.producer.flush(10)
        self.log.info("SEND -> %s correlation_id=%s message=%s", REQUEST_TOPIC, corr, json.dumps(msg))
        flow(self.name, "sent", corr, REQUEST_TOPIC, msg)
        try:
            if not slot["event"].wait(timeout):
                raise TimeoutError(f"no response for correlation_id={corr} within {timeout}s (is the worker running?)")
        finally:
            with self._lock:
                self._pending.pop(corr, None)
        resp = slot["response"]
        self.log.info("RESPONSE <- %s [partition %d offset %d] correlation_id=%s response=%s",
                      RESPONSE_TOPIC, slot["partition"], slot["offset"], resp.get("correlation_id"), json.dumps(resp))
        flow(self.name, "response_received", resp.get("correlation_id"), RESPONSE_TOPIC, resp)
        if resp.get("correlation_id") != corr:
            raise RuntimeError(f"correlation_id changed: sent {corr}, got {resp.get('correlation_id')}")
        return resp

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.consumer.close()
