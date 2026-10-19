"""Part 2/3 - short-term, long-term (summaries) and episodic memory + cost logging.

Config (env vars, read on every call so experiments can override them):
  SHORT_TERM_N               sliding-window size (default 12)
  SUMMARIZE_EVERY_USER_MSGS  M - session summary every M user messages (default 4)
  LIFETIME_EVERY_SUMMARIES   condense into lifetime summary every K session summaries (default 2)
  EPISODE_TOP_K              episodic facts retrieved per turn (default 3)
  MEMORY_POLICY              none | compress   (Part 3.4 memory-saving policy)
  EXTRACT_MODE               llm | heuristic   (how episodic facts are extracted)
  FILE_MEMORY                1 | 0  include AGENT.md + MEMORY.md in the system prompt (Part 4)
  CHAT_LOG                   path of the per-turn JSONL usage log
"""
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pymongo import DESCENDING

import file_memory
import llm_adapter as llm
from database import episodes_col, messages_col, summaries_col, utcnow

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "reports" / "hw06" / "raw" / "chat_log.jsonl"

SYSTEM_PRIMER = (
    "You are TransitBot, the assistant for the Municipal Transit Incident Manager (project s1066). "
    "Help the user track bus, light-rail and subway incidents. Be concise (max 4 sentences). "
    "Use the memory sections below when they are relevant; if you do not know something, say so "
    "instead of guessing."
)

COMPRESS_KEEP_VERBATIM = 4
COMPRESS_GIST_CHARS = 90


def cfg(overrides: Optional[dict] = None) -> dict:
    c = {
        "short_term_n": int(os.getenv("SHORT_TERM_N", "12")),
        "summarize_every": int(os.getenv("SUMMARIZE_EVERY_USER_MSGS", "4")),
        "lifetime_every": int(os.getenv("LIFETIME_EVERY_SUMMARIES", "2")),
        "top_k": int(os.getenv("EPISODE_TOP_K", "3")),
        "policy": os.getenv("MEMORY_POLICY", "none"),
        "extract_mode": os.getenv("EXTRACT_MODE", "llm"),
        "file_memory": os.getenv("FILE_MEMORY", "1") == "1",
        "log_path": os.getenv("CHAT_LOG", str(DEFAULT_LOG)),
    }
    if overrides:
        c.update({k: v for k, v in overrides.items() if v is not None})
    return c


# ------------------------------------------------------------------------------
# Messages / short-term window
# ------------------------------------------------------------------------------
def save_message(user_id: str, session_id: str, role: str, content: str):
    return messages_col.insert_one({
        "user_id": user_id, "session_id": session_id, "role": role,
        "content": content, "created_at": utcnow(),
    }).inserted_id


def load_short_term(session_id: str, n: int, exclude_id=None) -> List[Dict[str, str]]:
    """Last n messages of the session (oldest first), excluding the current message."""
    query = {"session_id": session_id}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    docs = list(messages_col.find(query).sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(n))
    return [{"role": d["role"], "content": d["content"]} for d in reversed(docs)]


def apply_policy(window: List[Dict[str, str]], policy: str) -> List[Dict[str, str]]:
    """Memory-saving policy 'compress': keep the newest 4 messages verbatim and
    compress every older message in the window to a short gist (first ~90 chars)."""
    if policy != "compress" or len(window) <= COMPRESS_KEEP_VERBATIM:
        return window
    older, recent = window[:-COMPRESS_KEEP_VERBATIM], window[-COMPRESS_KEEP_VERBATIM:]
    gisted = []
    for m in older:
        text = m["content"].replace("\n", " ")
        if len(text) > COMPRESS_GIST_CHARS:
            text = text[:COMPRESS_GIST_CHARS].rsplit(" ", 1)[0] + " …"
        gisted.append({"role": m["role"], "content": text})
    return gisted + recent


# ------------------------------------------------------------------------------
# Long-term summaries
# ------------------------------------------------------------------------------
def latest_summary(user_id: str, scope: str, session_id: Optional[str] = None) -> Optional[dict]:
    q = {"user_id": user_id, "scope": scope}
    if scope == "session":
        q["session_id"] = session_id
    return summaries_col.find_one(q, sort=[("created_at", DESCENDING), ("_id", DESCENDING)])


def _summarize(text: str, instruction: str) -> str:
    out = llm.chat([
        {"role": "system", "content": "You write concise memory summaries as 3-6 short bullet points starting with '- '. "
                                      "Keep names, numbers, routes, preferences and decisions. No preamble."},
        {"role": "user", "content": f"{instruction}\n\n{text}"},
    ], temperature=0.0, max_tokens=250)
    return out["text"]


def maybe_summarize(user_id: str, session_id: str, c: dict) -> Dict[str, bool]:
    """Every M user messages: write a session summary; every K session summaries: refresh lifetime summary."""
    flags = {"session_summary_created": False, "lifetime_summary_created": False}
    n_user = messages_col.count_documents({"session_id": session_id, "role": "user"})
    if n_user == 0 or n_user % c["summarize_every"] != 0:
        return flags

    recent = load_short_term(session_id, 2 * c["summarize_every"])
    prev = latest_summary(user_id, "session", session_id)
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    text = (f"Previous session summary:\n{prev['text']}\n\n" if prev else "") + f"Recent conversation:\n{convo}"
    summary = _summarize(text, "Update the session summary with the recent conversation.")
    summaries_col.insert_one({"user_id": user_id, "session_id": session_id, "scope": "session",
                              "text": summary, "created_at": utcnow()})
    flags["session_summary_created"] = True

    n_sess = summaries_col.count_documents({"user_id": user_id, "scope": "session"})
    if n_sess % c["lifetime_every"] == 0:
        sess = list(summaries_col.find({"user_id": user_id, "scope": "session"})
                    .sort("created_at", DESCENDING).limit(5))
        life = latest_summary(user_id, "user")
        body = (f"Current lifetime summary:\n{life['text']}\n\n" if life else "") + \
            "Session summaries:\n" + "\n\n".join(s["text"] for s in reversed(sess))
        lifetime = _summarize(body, "Condense these into one lifetime profile of the user (durable facts only).")
        summaries_col.insert_one({"user_id": user_id, "session_id": None, "scope": "user",
                                  "text": lifetime, "created_at": utcnow()})
        flags["lifetime_summary_created"] = True
    return flags


# ------------------------------------------------------------------------------
# Episodic memory
# ------------------------------------------------------------------------------
_FACT_HINTS = re.compile(r"\b(i|i'm|im|my|me|we|our|prefer|always|never|live|work|commute|name|favorite|allergic)\b", re.I)


def _heuristic_facts(message: str) -> List[Dict]:
    facts = []
    for sent in re.split(r"(?<=[.!?])\s+", message.strip()):
        s = sent.strip()
        if 12 <= len(s) <= 240 and _FACT_HINTS.search(s) and not s.endswith("?"):
            importance = 0.8 if re.search(r"\b(always|never|prefer|name|allergic|must)\b", s, re.I) else 0.5
            facts.append({"fact": s[:200], "importance": importance})
    return facts[:3]


def extract_episodes(message: str, mode: str = "llm") -> List[Dict]:
    """Extract up to 3 short durable facts (with importance 0..1) from one user message."""
    if mode != "llm":
        return _heuristic_facts(message)
    prompt = (
        "Extract at most 3 short, durable facts about the user from the message below "
        "(identity, preferences, routes, incidents they report, plans). Ignore questions and small talk. "
        'Return JSON: {"facts": [{"fact": "<= 20 words, third person", "importance": 0.0-1.0}]}. '
        'Return {"facts": []} if there are none.\n\nMessage: ' + message
    )
    try:
        out = llm.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=200, json_mode=True)
        data = json.loads(out["text"])
        facts = []
        for f in data.get("facts", [])[:3]:
            fact = str(f.get("fact", "")).strip()
            if fact:
                imp = float(f.get("importance", 0.5))
                facts.append({"fact": fact[:200], "importance": max(0.0, min(1.0, imp))})
        return facts
    except (llm.LLMError, ValueError, AttributeError, TypeError):
        return _heuristic_facts(message)


def store_episodes(user_id: str, session_id: str, facts: List[Dict]) -> List[Dict]:
    stored = []
    for f in facts:
        doc = {"user_id": user_id, "session_id": session_id, "fact": f["fact"],
               "importance": float(f["importance"]), "embedding": llm.embed(f["fact"]),
               "created_at": utcnow()}
        episodes_col.insert_one(doc)
        stored.append({"fact": doc["fact"], "importance": doc["importance"]})
    return stored


def retrieve_episodes(user_id: str, query_vec: List[float], k: int, min_importance: float = 0.0) -> List[Dict]:
    """Top-k episodes for this user by cosine similarity to the current message embedding."""
    cands = episodes_col.find({"user_id": user_id, "importance": {"$gte": min_importance}},
                              {"fact": 1, "importance": 1, "embedding": 1}).sort("created_at", DESCENDING).limit(500)
    scored = [(llm.cosine(query_vec, e["embedding"]), e) for e in cands]
    scored.sort(key=lambda t: (t[0], t[1]["importance"]), reverse=True)
    seen, out = set(), []
    for score, e in scored:
        key = e["fact"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"fact": e["fact"], "importance": e["importance"], "score": round(score, 4)})
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------------------
# Prompt assembly
# ------------------------------------------------------------------------------
def compose_prompt(system_primer: str, session_summary: Optional[str], lifetime_summary: Optional[str],
                   window: List[Dict[str, str]], message: str, episodes: List[Dict]) -> Tuple[List[Dict], Dict]:
    """system primer + long-term summaries + short-term window + current message + episodic facts."""
    long_term = ""
    if lifetime_summary:
        long_term += f"## Lifetime summary of the user\n{lifetime_summary}\n"
    if session_summary:
        long_term += f"## Summary of this session so far\n{session_summary}\n"
    episodic = ""
    if episodes:
        episodic = "## Relevant facts remembered about the user\n" + "\n".join(f"- {e['fact']}" for e in episodes)

    system = system_primer + ("\n\n" + long_term if long_term else "")
    current = message + ("\n\n" + episodic if episodic else "")
    messages = [{"role": "system", "content": system}] + window + [{"role": "user", "content": current}]
    breakdown = {
        "system_primer_tokens": llm.approx_tokens(system_primer),
        "long_term_tokens": llm.approx_tokens(long_term),
        "short_term_tokens": sum(llm.approx_tokens(m["content"]) for m in window),
        "episodic_tokens": llm.approx_tokens(episodic),
        "current_message_tokens": llm.approx_tokens(message),
    }
    return messages, breakdown


# ------------------------------------------------------------------------------
# One chat turn (used by POST /api/chat and by the Part 3 experiment runner)
# ------------------------------------------------------------------------------
def log_usage(row: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def chat_turn(user_id: str, session_id: Optional[str], message: str, overrides: Optional[dict] = None,
              run_label: str = "api") -> Dict:
    c = cfg(overrides)
    session_id = session_id or f"sess-{uuid.uuid4().hex[:10]}"
    t0 = time.perf_counter()

    # 1. save user message
    msg_id = save_message(user_id, session_id, "user", message)
    # 2. short-term window (+ optional compression policy)
    window = apply_policy(load_short_term(session_id, c["short_term_n"], exclude_id=msg_id), c["policy"])
    # 3. long-term summaries
    sess = latest_summary(user_id, "session", session_id)
    life = latest_summary(user_id, "user")
    # 4. episodic retrieval
    min_imp = 0.4 if c["policy"] == "compress" else 0.0
    episodes = retrieve_episodes(user_id, llm.embed(message), c["top_k"], min_imp)
    # 5. compose prompt (system primer may include AGENT.md + MEMORY.md)
    primer = file_memory.build_system_prompt(SYSTEM_PRIMER) if c["file_memory"] else SYSTEM_PRIMER
    prompt, breakdown = compose_prompt(primer, sess["text"] if sess else None,
                                       life["text"] if life else None, window, message, episodes)
    # 6. call model
    out = llm.chat(prompt)
    # 7. save reply
    save_message(user_id, session_id, "assistant", out["text"])
    # 8. episodic extraction for this user message
    new_facts = store_episodes(user_id, session_id, extract_episodes(message, c["extract_mode"]))
    # 9. summarization trigger
    flags = maybe_summarize(user_id, session_id, c)
    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    usage = {
        "prompt_tokens": out["prompt_tokens"], "completion_tokens": out["completion_tokens"],
        **breakdown, "model_latency_ms": out["latency_ms"], "request_latency_ms": total_ms,
        "model": out["model"], "embed_backend": llm.embed_backend(),
    }
    log_usage({"ts": utcnow().isoformat(), "run": run_label, "user_id": user_id, "session_id": session_id,
               "short_term_n": c["short_term_n"], "policy": c["policy"], **usage}, c["log_path"])

    return {
        "reply": out["text"],
        "session_id": session_id,
        "memory_used": {
            "short_term_count": len(window),
            "short_term": window,
            "session_summary": sess["text"] if sess else None,
            "lifetime_summary": life["text"] if life else None,
            "episodic_facts": episodes,
            "new_episodes_stored": new_facts,
            **flags,
        },
        "usage": usage,
    }
