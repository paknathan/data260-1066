"""HW8 Part 1 - incident worker logic + full request/response wiring (in-memory fake Kafka, no broker needed)."""

import json
import threading
import time

import fake_kafka
import pytest

from kafka_service import client as client_mod
from kafka_service import common, worker
from kafka_service.config import REQUEST_TOPIC, RESPONSE_TOPIC
from kafka_service.schema import validate_incident

GOOD = {"incident_type": "Delay", "transit_mode": "Bus", "route_or_line": "Route 22", "location": "1st & Santa Clara",
        "date_reported": "2026-11-01", "time_reported": "07:45", "severity": "Moderate", "status": "Reported",
        "delay_minutes": 12}


def req(op, data, corr="c-1"):
    return {"correlation_id": corr, "reply_to": RESPONSE_TOPIC, "operation": op, "data": data}


def test_create_then_get_roundtrip():
    store = {}
    created = worker.handle_request(req("CREATE_INCIDENT", GOOD, "c-1"), store)
    assert created["success"] and created["correlation_id"] == "c-1" and created["message"] == "Incident created"
    got = worker.handle_request(req("GET_INCIDENT", {"incident_id": created["incident_id"]}, "c-2"), store)
    assert got["success"] and got["correlation_id"] == "c-2"
    assert got["incident"] == {"incident_id": created["incident_id"], **GOOD}


@pytest.mark.parametrize("data,needle", [
    ({**GOOD, "location": ""}, "Missing or empty"),
    ({k: v for k, v in GOOD.items() if k != "severity"}, "Missing or empty"),
    ({**GOOD, "severity": "Extreme"}, "Invalid severity"),
    ({**GOOD, "date_reported": "11/01/2026"}, "Invalid date_reported"),
    ({**GOOD, "time_reported": "25:99"}, "Invalid time_reported"),
    ({**GOOD, "delay_minutes": -5}, "Invalid delay_minutes"),
    ({**GOOD, "rider_email": "a@b.c"}, "Unknown field"),
    ("not an object", "JSON object"),
])
def test_create_rejects_bad_data_with_correlation_id(data, needle):
    r = worker.handle_request(req("CREATE_INCIDENT", data, "bad-1"), {})
    assert r["success"] is False and needle in r["error"] and r["correlation_id"] == "bad-1"


def test_unknown_operation_and_missing_entity():
    assert worker.handle_request(req("DELETE_INCIDENT", {}, "u"), {}) == {
        "correlation_id": "u", "success": False, "error": "Unknown operation"}
    nf = worker.handle_request(req("GET_INCIDENT", {"incident_id": "nope"}, "n"), {})
    assert nf == {"correlation_id": "n", "success": False, "error": "Incident not found"}
    assert worker.handle_request({"operation": "GET_INCIDENT"}, {})["success"] is False
    assert validate_incident(GOOD)[1] is None


def test_end_to_end_over_fake_kafka(monkeypatch, tmp_path):
    for mod in (worker, client_mod):
        monkeypatch.setattr(mod, "Consumer", fake_kafka.Consumer)
        monkeypatch.setattr(mod, "Producer", fake_kafka.Producer)
    monkeypatch.setattr(client_mod, "TopicPartition", fake_kafka.TopicPartition)
    monkeypatch.setattr(common, "AdminClient", fake_kafka.AdminClient)
    monkeypatch.setattr(common, "FLOW_LOG", tmp_path / "flow.jsonl")
    fake_kafka.BROKER.__init__()
    worker.INCIDENTS.clear()
    stop = {"on": True}
    real_poll = fake_kafka.Consumer.poll

    def poll(self, timeout=1.0):  # let the worker loop end when the test finishes
        if not stop["on"] and self.group == worker.WORKER_GROUP:
            import signal  # noqa: F401
            raise KeyboardInterrupt
        return real_poll(self, min(timeout, 0.2))
    monkeypatch.setattr(fake_kafka.Consumer, "poll", poll)
    t = threading.Thread(target=lambda: _run_worker(), daemon=True)
    t.start()
    time.sleep(0.3)
    c = client_mod.KafkaRequestClient(name="test_client")
    created = c.request("CREATE_INCIDENT", GOOD, correlation_id="corr-create")
    got = c.request("GET_INCIDENT", {"incident_id": created["incident_id"]}, correlation_id="corr-get")
    stop["on"] = False
    c.close()
    assert created["correlation_id"] == "corr-create" and created["success"]
    assert got["correlation_id"] == "corr-get" and got["incident"]["route_or_line"] == "Route 22"
    req_log = fake_kafka.BROKER.topics[REQUEST_TOPIC][0]
    assert json.loads(req_log[0][1])["reply_to"] == RESPONSE_TOPIC
    events = [json.loads(x)["event"] for x in (tmp_path / "flow.jsonl").read_text().splitlines()
              if "corr-create" in x]
    assert events == ["sent", "received", "processed", "replied", "response_received"]
    assert fake_kafka.BROKER.committed[(worker.WORKER_GROUP, REQUEST_TOPIC, 0)] == 2  # committed after replies


def _run_worker():
    try:
        worker.main()
    except KeyboardInterrupt:
        pass
