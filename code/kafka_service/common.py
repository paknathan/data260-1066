"""Kafka helpers shared by the worker, client, API wrapper and demo: topic setup + structured flow logging."""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

from confluent_kafka.admin import AdminClient, NewTopic

from .config import BOOTSTRAP, FLOW_LOG

LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(name)s] %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Console logger with millisecond timestamps (component name shown in brackets)."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger(name)


def flow(component: str, event: str, correlation_id: str | None, topic: str | None, payload: Any) -> None:
    """Append one structured event to the shared flow log (lets the demo show the full cross-process sequence)."""
    try:
        FLOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FLOW_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                 "component": component, "event": event, "correlation_id": correlation_id,
                                 "topic": topic, "payload": payload}, default=str) + "\n")
    except OSError:
        pass  # logging must never break message handling


def ensure_topics(topics: dict[str, int], bootstrap: str = BOOTSTRAP, log: logging.Logger | None = None) -> None:
    """Create topics (name -> partitions) if missing. Retries while the broker is still starting."""
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for _attempt in range(30):
        try:
            existing = set(admin.list_topics(timeout=5).topics)
            break
        except Exception as exc:  # broker not up yet
            if log:
                log.info("waiting for Kafka at %s (%s)", bootstrap, exc)
            time.sleep(2)
    else:
        raise RuntimeError(f"Kafka not reachable at {bootstrap}")
    new = [NewTopic(t, num_partitions=p, replication_factor=1) for t, p in topics.items() if t not in existing]
    for topic, fut in admin.create_topics(new).items() if new else []:
        try:
            fut.result()
            if log:
                log.info("created topic %s", topic)
        except Exception as exc:
            if "TOPIC_ALREADY_EXISTS" not in str(exc) and log:
                log.info("topic %s: %s", topic, exc)
