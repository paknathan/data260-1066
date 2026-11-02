"""HW8 Part 1 - FastAPI wrapper: HTTP -> Kafka request -> worker -> Kafka response -> HTTP.

Run (inside docker-compose):  uvicorn kafka_service.api:app --host 0.0.0.0 --port 8166
  POST /incidents            body = incident fields     -> CREATE_INCIDENT
  GET  /incidents/{id}                                  -> GET_INCIDENT
  POST /requests             {"operation", "data"}      -> any operation (e.g. to show Unknown operation)
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI
from fastapi.concurrency import run_in_threadpool

from .client import KafkaRequestClient
from .common import flow, get_logger
from .config import PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC

log = get_logger("api")
state: dict[str, KafkaRequestClient] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["client"] = KafkaRequestClient(name="api")
    log.info("FastAPI server started at http://127.0.0.1:%d (requests -> %s, responses <- %s)",
             PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC)
    yield
    state["client"].close()


app = FastAPI(title="s1066 Transit Incident Kafka API", lifespan=lifespan)


async def _call(operation: str, data: dict[str, Any]) -> dict[str, Any]:
    resp = await run_in_threadpool(state["client"].request, operation, data)
    log.info("RETURN to caller correlation_id=%s success=%s", resp.get("correlation_id"), resp.get("success"))
    flow("api", "returned_to_caller", resp.get("correlation_id"), None, resp)
    return resp


@app.post("/incidents")
async def create_incident(incident: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return await _call("CREATE_INCIDENT", incident)


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str) -> dict[str, Any]:
    return await _call("GET_INCIDENT", {"incident_id": incident_id})


@app.post("/requests")
async def raw_request(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return await _call(str(body.get("operation")), body.get("data") or {})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
