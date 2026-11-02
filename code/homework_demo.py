"""HW8 Part 1 demonstration: CREATE_INCIDENT -> GET_INCIDENT over Kafka, with the full correlation_id flow.

Prerequisite: `docker compose -f docker-compose.hw8.yml up -d --build` (Kafka + worker + API running).
Run from code/:   python homework_demo.py | tee -a ../reports/hw08/RUN_LOG.txt
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from kafka_service.client import KafkaRequestClient
from kafka_service.common import get_logger
from kafka_service.config import FLOW_LOG, REQUEST_TOPIC, RESPONSE_TOPIC

log = get_logger("demo")
INCIDENT = {
    "incident_type": "Signal / Track Problem",
    "transit_mode": "Light Rail",
    "route_or_line": "Blue Line",
    "location": "Tasman Station",
    "date_reported": "2026-11-01",
    "time_reported": "08:15",
    "severity": "High",
    "status": "Under Investigation",
    "delay_minutes": 25,
    "description": "Signal failure between Tasman and Baypointe; trains single-tracking.",
    "reported_by": "Transit Staff",
}


def show_sequence(corr: str, label: str) -> None:
    """Print every component's event for one correlation_id, in time order (from the shared flow log)."""
    events = [json.loads(line) for line in FLOW_LOG.read_text(encoding="utf-8").splitlines() if corr in line]
    events.sort(key=lambda e: e["ts"])
    names = {"sent": "client SEND", "received": "worker RECEIVE", "processed": "worker PROCESS",
             "replied": "worker REPLY", "response_received": "client RESPONSE"}
    log.info("---- %s full sequence (correlation_id=%s) ----", label, corr)
    for e in events:
        detail = {k: v for k, v in (e["payload"] or {}).items() if k in ("operation", "success", "incident_id",
                                                                          "error", "store_size")}
        log.info("  %s  %-16s %-26s corr=%s %s", e["ts"][11:23], names.get(e["event"], e["event"]),
                 e["topic"] or "", e["correlation_id"], json.dumps(detail))


def main() -> None:
    log.info("=" * 90)
    log.info("Nathan Pak (s1066) | HW8 Part 1 | request topic=%s | response topic=%s", REQUEST_TOPIC, RESPONSE_TOPIC)
    client = KafkaRequestClient(name="demo_client")
    time.sleep(0.5)

    # 1. one correlation_id for the CREATE request
    create_corr = str(uuid.uuid4())
    log.info("STEP 1  created correlation_id=%s", create_corr)
    # 2-6. send CREATE_INCIDENT, worker processes + replies, client receives
    log.info("STEP 2-3  sending CREATE_INCIDENT to %s", REQUEST_TOPIC)
    created = client.request("CREATE_INCIDENT", INCIDENT, correlation_id=create_corr)
    log.info("STEP 6  CREATE response: %s", json.dumps(created))
    # 7. extract the generated incident_id
    incident_id = created["incident_id"]
    log.info("STEP 7  generated incident_id=%s", incident_id)

    # 8-9. GET_INCIDENT with that id (its own correlation_id)
    get_corr = str(uuid.uuid4())
    log.info("STEP 8  sending GET_INCIDENT incident_id=%s correlation_id=%s", incident_id, get_corr)
    fetched = client.request("GET_INCIDENT", {"incident_id": incident_id}, correlation_id=get_corr)

    # 10. show the entity and confirm correlation ids were preserved
    time.sleep(0.5)  # let the worker's last flow-log line land
    show_sequence(create_corr, "CREATE_INCIDENT")
    show_sequence(get_corr, "GET_INCIDENT")
    log.info("STEP 10 retrieved incident:\n%s", json.dumps(fetched["incident"], indent=2))
    log.info("STEP 10 correlation_id preserved: CREATE sent=%s returned=%s -> %s | GET sent=%s returned=%s -> %s",
             create_corr, created["correlation_id"], created["correlation_id"] == create_corr,
             get_corr, fetched["correlation_id"], fetched["correlation_id"] == get_corr)
    log.info("STEP 10 round trip matches: %s", {k: v for k, v in fetched["incident"].items() if k != "incident_id"} == INCIDENT)

    # error paths (clean errors, correlation_id still echoed)
    for op, data in (("GET_INCIDENT", {"incident_id": "does-not-exist"}),
                     ("CREATE_INCIDENT", {**INCIDENT, "severity": "Extreme", "location": ""}),
                     ("DELETE_INCIDENT", {"incident_id": incident_id})):
        r = client.request(op, data)
        log.info("ERROR CASE %-16s -> success=%s error=%r correlation_id=%s", op, r["success"], r.get("error"),
                 r["correlation_id"])

    out = Path(FLOW_LOG).parent / "part1_demo.json"
    out.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "create": created, "get": fetched,
                               "create_correlation_id": create_corr, "get_correlation_id": get_corr}, indent=2))
    client.close()
    log.info("saved %s", out)


if __name__ == "__main__":
    main()
