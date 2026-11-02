"""HW8 Part 1 - incident worker: consumes s1066_incident_requests, processes CREATE_INCIDENT / GET_INCIDENT,
replies to the topic named in reply_to with the unchanged correlation_id. Entities live in a plain dict.

Run (inside docker-compose):  python -m kafka_service.worker
"""

import json
import signal
import uuid
from typing import Any

from confluent_kafka import Consumer, KafkaError, Producer

from .common import ensure_topics, flow, get_logger
from .config import BOOTSTRAP, PREFIX, REQUEST_TOPIC, RESPONSE_TOPIC, WORKER_GROUP
from .schema import validate_incident

log = get_logger("worker")
INCIDENTS: dict[str, dict[str, Any]] = {}  # plain in-memory store: incident_id -> incident


def handle_request(msg: Any, store: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Pure request handler: request message -> response message (always echoes correlation_id)."""
    corr = msg.get("correlation_id") if isinstance(msg, dict) else None
    base = {"correlation_id": corr}
    if not isinstance(msg, dict):
        return {**base, "success": False, "error": "Request must be a JSON object"}
    missing = [k for k in ("correlation_id", "reply_to", "operation", "data") if k not in msg]
    if missing:
        return {**base, "success": False, "error": f"Request missing field(s): {missing}"}
    op, data = msg["operation"], msg["data"]
    if op == "CREATE_INCIDENT":
        incident, error = validate_incident(data)
        if error:
            return {**base, "success": False, "error": error}
        incident_id = str(uuid.uuid4())
        store[incident_id] = {"incident_id": incident_id, **incident}
        return {**base, "success": True, "incident_id": incident_id, "message": "Incident created"}
    if op == "GET_INCIDENT":
        incident_id = data.get("incident_id") if isinstance(data, dict) else None
        if not isinstance(incident_id, str) or not incident_id.strip():
            return {**base, "success": False, "error": "data.incident_id is required"}
        if incident_id not in store:
            return {**base, "success": False, "error": "Incident not found"}
        return {**base, "success": True, "incident": store[incident_id]}
    return {**base, "success": False, "error": "Unknown operation"}


def main() -> None:
    """Consume -> process -> reply -> commit (offset committed only after the reply is delivered)."""
    ensure_topics({REQUEST_TOPIC: 1, RESPONSE_TOPIC: 1}, log=log)
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": WORKER_GROUP, "enable.auto.commit": False,
                         "auto.offset.reset": "earliest"})
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    running = {"on": True}
    try:  # docker stop -> SIGTERM -> finish the current message and exit cleanly
        signal.signal(signal.SIGTERM, lambda *_: running.update(on=False))
    except ValueError:  # not the main thread (tests)
        pass

    def on_assign(c: Consumer, parts: list) -> None:
        log.info("Consumer is ready and listening... topic=%s group=%s partitions=%s",
                 REQUEST_TOPIC, WORKER_GROUP, [p.partition for p in parts])

    consumer.subscribe([REQUEST_TOPIC], on_assign=on_assign)
    try:
        while running["on"]:
            m = consumer.poll(1.0)
            if m is None:
                continue
            if m.error():
                if m.error().code() != KafkaError._PARTITION_EOF:
                    log.info("consumer error: %s", m.error())
                continue
            try:
                req = json.loads(m.value())
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                req = None
            corr = req.get("correlation_id") if isinstance(req, dict) else None
            log.info("RECEIVED <- %s [partition %d offset %d] correlation_id=%s message=%s",
                     m.topic(), m.partition(), m.offset(), corr, json.dumps(req))
            flow("worker", "received", corr, m.topic(), req)
            op = req.get("operation") if isinstance(req, dict) else None
            log.info("PROCESSING %s correlation_id=%s", op, corr)
            resp = handle_request(req, INCIDENTS)
            flow("worker", "processed", corr, None, {"operation": op, "success": resp["success"],
                                                     "store_size": len(INCIDENTS)})
            reply_to = req.get("reply_to") if isinstance(req, dict) else None
            if not (isinstance(reply_to, str) and reply_to.startswith(f"{PREFIX}_")):
                reply_to = RESPONSE_TOPIC  # never write to arbitrary topics named by a client
            producer.produce(reply_to, key=(corr or "").encode(), value=json.dumps(resp).encode())
            producer.flush(10)
            log.info("REPLY -> %s correlation_id=%s response=%s", reply_to, corr, json.dumps(resp))
            flow("worker", "replied", corr, reply_to, resp)
            consumer.commit(message=m, asynchronous=False)
    finally:
        consumer.close()
        log.info("worker stopped")


if __name__ == "__main__":
    main()
