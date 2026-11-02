"""HW8 shared Kafka configuration (Section 0 values: SID4 1066 -> PREFIX s1066, PORT_BASE 8166)."""

import os
from pathlib import Path

SID4 = 1066
PREFIX = f"s{SID4}"
PORT_BASE = 8000 + (SID4 % 900)  # 8166
SEED = SID4
VERIFY_SEED = 260000 + SID4

ENTITY = "incident"
REQUEST_TOPIC = f"{PREFIX}_{ENTITY}_requests"    # s1066_incident_requests
RESPONSE_TOPIC = f"{PREFIX}_{ENTITY}_responses"  # s1066_incident_responses
WORKER_GROUP = f"{PREFIX}_{ENTITY}_worker"

# localhost:9092 from the Mac; kafka:19092 inside the docker-compose network
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

_DEFAULT_FLOW_LOG = Path(__file__).resolve().parents[2] / "reports" / "hw08" / "raw" / "kafka_flow.jsonl"
FLOW_LOG = Path(os.getenv("FLOW_LOG", str(_DEFAULT_FLOW_LOG)))
