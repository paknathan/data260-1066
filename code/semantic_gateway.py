"""HW9 Part 2 - semantic-cache ingress in front of the HW8 Planner -> Writer -> Reviewer pipeline.

    question -> embed -> Redis KNN search (cosine, current data version)
        similarity >= threshold : CACHE HIT  -> stored final answer, is_cached=True (agents not run)
        otherwise               : CACHE MISS -> s1066_inbox -> planner -> writer -> reviewer -> s1066_final,
                                  store {query, embedding, answer, data_version}, is_cached=False

Run (Kafka + the three agents from HW8 must be running):
    uvicorn semantic_gateway:app --port 8167
    curl -X POST localhost:8167/ask -H 'Content-Type: application/json' -d '{"question": "Why is the Blue Line delayed?"}'
"""

import json
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from fastapi import Body, FastAPI
from fastapi.concurrency import run_in_threadpool

from kafka_agents.base import flow
from kafka_agents.config import BOOTSTRAP, INBOX
from kafka_service.common import get_logger
from semantic_cache import SemanticCache
from send_question import final_listener

log = get_logger("semcache")
_producer = None


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def run_agent_pipeline(question: str, timeout: float = 600) -> dict:
    """The unchanged HW8 path: publish to s1066_inbox and wait for the matching s1066_final message."""
    global _producer
    _producer = _producer or Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    corr = str(uuid.uuid4())
    consumer = final_listener(log)  # positioned at the end of s1066_final before we send
    try:
        msg = {"correlation_id": corr, "question": question,
               "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _producer.produce(INBOX, key=corr.encode(), value=json.dumps(msg).encode())
        _producer.flush(10)
        flow("gateway", "semcache", "sent", corr, out_topic=INBOX)
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = consumer.poll(1.0)
            if m is None or m.error():
                continue
            body = json.loads(m.value())
            if body.get("correlation_id") == corr:
                flow("gateway", "semcache", "final_received", corr, topic=m.topic(), offset=m.offset())
                return body
    finally:
        consumer.close()
    raise TimeoutError(f"no final answer for correlation_id={corr} within {timeout:.0f}s")


class CachedQA:
    """Query handler with the semantic cache at ingress. `pipeline` is injectable for tests."""

    def __init__(self, cache: SemanticCache | None = None, pipeline=run_agent_pipeline):
        self.cache = cache or SemanticCache()
        self.pipeline = pipeline

    def ask(self, question: str) -> dict:
        question = question.strip()
        t_start = time.perf_counter()
        timings = {}

        t = time.perf_counter()
        vec = self.cache.embed(question)
        timings["embed_ms"] = _ms(t)

        t = time.perf_counter()
        version = self.cache.data_version()
        entry, similarity = self.cache.search(vec, version)
        timings["search_ms"] = _ms(t)

        if entry is not None and similarity >= self.cache.threshold:
            latency = _ms(t_start)
            log.info("CACHE HIT  similarity=%.4f (threshold %.2f) latency=%.1fms matched=%r",
                     similarity, self.cache.threshold, latency, entry["query"])
            return {"question": question, "answer": entry["answer"], "is_cached": True,
                    "similarity": round(similarity, 4), "latency_ms": latency, "matched_query": entry["query"],
                    "data_version": version, "timings": timings}

        best = "none (no entries for current data version)" if similarity is None else f"{similarity:.4f}"
        log.info("CACHE MISS best_similarity=%s (threshold %.2f) -> running HW8 agent pipeline", best,
                 self.cache.threshold)
        t = time.perf_counter()
        final = self.pipeline(question)
        timings["agent_ms"] = _ms(t)
        answer, status = final.get("answer", ""), final.get("status")

        t = time.perf_counter()
        if status == "approved" and answer:  # never cache a rejected answer
            self.cache.store(question, vec, answer, version, status=status,
                             correlation_id=final.get("correlation_id", ""))
        timings["store_ms"] = _ms(t)

        latency = _ms(t_start)
        log.info("CACHE MISS done latency=%.1fms (agents %.1fms) stored=%s", latency, timings["agent_ms"],
                 status == "approved")
        return {"question": question, "answer": answer, "is_cached": False,
                "similarity": None if similarity is None else round(similarity, 4), "latency_ms": latency,
                "matched_query": None if entry is None else entry["query"], "data_version": version,
                "status": status, "timings": timings}


# ---- FastAPI ingress ------------------------------------------------------------------------------
app = FastAPI(title="s1066 Transit Q&A with semantic cache")
_qa: CachedQA | None = None


def _get_qa() -> CachedQA:
    global _qa
    _qa = _qa or CachedQA()
    return _qa


@app.post("/ask")
async def ask(body: dict = Body(..., examples=[{"question": "Why is the Blue Line delayed at Tasman?"}])) -> dict:
    return await run_in_threadpool(_get_qa().ask, str(body.get("question", "")))


@app.post("/cache/bump-data-version")
def bump(body: dict = Body(default={})) -> dict:
    return {"data_version": _get_qa().cache.bump_data_version(body.get("reason", "manual bump"))}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
