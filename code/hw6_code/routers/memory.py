"""Part 2 - chat + memory endpoints (and Part 4 slash commands inside /api/chat)."""
from fastapi import APIRouter, HTTPException
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

import file_memory
import memory_core
from database import episodes_col, messages_col, summaries_col
from llm_adapter import LLMError
from models import ChatRequest

router = APIRouter(prefix="/api", tags=["Chat memory"])


def _clean(doc: dict, drop=("embedding",)) -> dict:
    doc = {k: v for k, v in doc.items() if k not in drop}
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/chat")
def chat(req: ChatRequest):
    try:
        if req.message.strip().startswith("/"):
            recent = memory_core.load_short_term(req.session_id, 20) if req.session_id else []
            mode = memory_core.cfg()["extract_mode"]
            result = file_memory.handle_command(
                req.message, recent, extractor=lambda t: memory_core.extract_episodes(t, mode))
            return {"session_id": req.session_id, **result}
        return memory_core.chat_turn(req.user_id, req.session_id, req.message)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=f"Local model unavailable: {exc}")
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error: {exc}")


@router.get("/memory/{user_id}")
def get_memory(user_id: str):
    try:
        msgs = list(messages_col.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(16))
        sess = summaries_col.find_one({"user_id": user_id, "scope": "session"}, sort=[("created_at", DESCENDING)])
        life = summaries_col.find_one({"user_id": user_id, "scope": "user"}, sort=[("created_at", DESCENDING)])
        eps = list(episodes_col.find({"user_id": user_id}, {"embedding": 0}).sort("created_at", DESCENDING).limit(20))
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error: {exc}")
    return {
        "user_id": user_id,
        "recent_messages": [_clean(m) for m in reversed(msgs)],
        "latest_session_summary": _clean(sess) if sess else None,
        "latest_lifetime_summary": _clean(life) if life else None,
        "episodic_facts": [_clean(e) for e in eps],
    }


@router.get("/aggregate/{user_id}")
def aggregate(user_id: str):
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at",
                                      "timezone": "America/Los_Angeles"}},
            "total": {"$sum": 1},
            "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
            "assistant_messages": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "date": "$_id", "total": 1, "user_messages": 1, "assistant_messages": 1}},
    ]
    try:
        daily = list(messages_col.aggregate(pipeline))
        recent = list(summaries_col.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(5))
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error: {exc}")
    return {"user_id": user_id, "daily_message_counts": daily,
            "recent_summaries": [_clean(s) for s in recent]}
