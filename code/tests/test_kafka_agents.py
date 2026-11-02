"""HW8 Part 2/3 - three-agent pipeline over the in-memory fake Kafka (rule mode, no model, no broker)."""

import json
import threading
import time
from types import SimpleNamespace

import fake_kafka
import pytest

import planner
import reviewer
import writer
from kafka_agents import base
from kafka_agents.config import DEAD_LETTER, DRAFTS, FINAL, INBOX, PARTITIONS, TASKS


@pytest.fixture()
def env(monkeypatch, tmp_path):
    fake_kafka.BROKER.__init__()
    for t, n in PARTITIONS.items():
        fake_kafka.BROKER.ensure(t, n)
    monkeypatch.setattr(base, "Consumer", fake_kafka.Consumer)
    monkeypatch.setattr(base, "Producer", fake_kafka.Producer)
    monkeypatch.setattr(base, "check_topics", lambda log: None)
    monkeypatch.setattr(base, "RAW", tmp_path)
    monkeypatch.setattr(base, "FLOW", tmp_path / "flow.jsonl")
    monkeypatch.setattr(base, "STATE", tmp_path / "state")
    handlers = []
    monkeypatch.setattr(base.signal, "signal", lambda sig, h: handlers.append(h))
    yield tmp_path
    for h in handlers:  # stop every agent thread started by this test
        h()
    time.sleep(1.2)


def args(**kw):
    d = {"instance": "t", "no_idempotency": False, "commit_before": False, "no_dlq": False, "max_retries": 2,
         "delay": 0.0, "rule": True}
    d.update(kw)
    return SimpleNamespace(**d)


def start(name, mod, src, dst, a):
    def target():
        base.run_agent(name, src, dst, mod.make_handler(a), a)
    th = threading.Thread(target=target, daemon=True)
    th.start()
    return th


def send(value):
    fake_kafka.Producer({}).produce(INBOX, key=b"k", value=value if isinstance(value, bytes) else json.dumps(value).encode())


def topic(name):
    return [json.loads(v) for part in fake_kafka.BROKER.topics[name] for _, v in part]


def wait(pred, t=8):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_full_journey_preserves_correlation_id(env):
    a = args()
    start("planner", planner, INBOX, TASKS, a)
    start("writer", writer, TASKS, DRAFTS, a)
    start("reviewer", reviewer, DRAFTS, FINAL, a)
    send({"correlation_id": "c-42", "question": "Why is Route 22 late?"})
    assert wait(lambda: topic(FINAL))
    final = topic(FINAL)[0]
    assert final["correlation_id"] == "c-42" and final["status"] == "approved" and final["answer"]
    assert topic(TASKS)[0]["correlation_id"] == topic(DRAFTS)[0]["correlation_id"] == "c-42"
    events = [(r["agent"], r["event"]) for r in map(json.loads, (env / "flow.jsonl").read_text().splitlines())]
    for agent in ("planner", "writer", "reviewer"):
        assert (agent, "received") in events and (agent, "sent") in events


def test_duplicate_skipped_with_idempotency(env):
    start("planner", planner, INBOX, TASKS, args())
    send({"correlation_id": "dup", "question": "q"})
    send({"correlation_id": "dup", "question": "q"})
    assert wait(lambda: "duplicate_skipped" in (env / "flow.jsonl").read_text() if (env / "flow.jsonl").exists() else False)
    assert len(topic(TASKS)) == 1


def test_poison_goes_to_dead_letter_and_pipeline_continues(env):
    start("planner", planner, INBOX, TASKS, args())
    send(b"this is not json")
    send({"correlation_id": "ok-1", "question": "q"})
    assert wait(lambda: topic(TASKS) and topic(DEAD_LETTER))
    dead = topic(DEAD_LETTER)[0]
    assert dead["agent"] == "planner" and dead["attempts"] == 2 and "poison" in dead["error"]
    assert topic(TASKS)[0]["correlation_id"] == "ok-1"


def test_keyed_mode_routes_entity_to_one_partition(env):
    start("planner", planner, INBOX, TASKS, args())
    for i in range(6):
        send({"correlation_id": f"o-{i}", "question": "q", "entity": "Route 22", "seq": i, "key_mode": "entity"})
    assert wait(lambda: sum(len(p) for p in fake_kafka.BROKER.topics[TASKS]) == 6)
    assert sorted(len(p) for p in fake_kafka.BROKER.topics[TASKS]) == [0, 6]
