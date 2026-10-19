# Pak_HW6 - DATA-260 Homework 6

**GitHub:** https://github.com/<your-username>/data260-1066  (tag `hw6`, collaborators Sbnikitha + supriyaselvanganesan added)

| Value | Result |
|---|---|
| SID4 | 1066 |
| PORT_BASE | 8000 + (1066 mod 900) = **8166** |
| PREFIX | **s1066** |
| SEED | **1066** |
| VERIFY_SEED | 260000 + 1066 = **261066** |
| DOMAIN_ID | 1066 mod 8 = **2** (Municipal transit incidents) |
| Hardware | <e.g. MacBook Pro M_, __ GB RAM> |
| Local model | <OLLAMA_MODEL, e.g. llama3.2:3b> + embeddings `nomic-embed-text` |
| Tagged commit | <git rev-parse hw6> |

## Part 1 - MongoDB Document API
- DB `s1066_doc`, collection `transit_incidents`. Fields: `title` (required, ≤100), `description` (optional), `status` enum reported/investigating/resolved (default reported), `category` enum bus/light_rail/subway, `event_time` (required datetime), `created_at`/`updated_at` (automatic).
- Validation at two layers: Pydantic (`models.TransitIncidentDoc`, 422 with field-level messages) and a MongoDB `$jsonSchema` validator (`database.py`).
- Files: `main.py` (server config, CORS middleware, validation handler), `database.py` (PyMongo connection), `models.py` (schemas), `routers/documents.py` (routes).
- Status codes: 201 create, 200 read/update, 204 delete, 400 bad ObjectId, 404 not found, 422 invalid data, 503 Mongo down, 500 other DB errors.

[Screenshot: POST / GET all / GET by id / PUT / DELETE]
[Screenshot: 422 responses - missing field, invalid enum, wrong type]
[Screenshot: Compass showing s1066_doc.transit_incidents]

## Part 2 - Short-, long-term and episodic memory
- `POST /api/chat` → `memory_core.chat_turn`: save message → last N window → session + lifetime summaries → top-k episodes (cosine) → compose prompt → Ollama → save reply → extract ≤3 facts + embed → every M=4 user messages summarize; every 2 session summaries condense to lifetime (`scope='user'`, `session_id=null`).
- `GET /api/memory/{user_id}`, `GET /api/aggregate/{user_id}` (`$group` by `$dateToString`).

[Screenshot: chat page conversation (≥10 messages)]
[JSON: GET /api/memory/nathan]  [JSON: GET /api/aggregate/nathan]
[Screenshot: Compass messages / summaries / episodes]
[Snippets: chat_turn, extract_episodes, maybe_summarize, retrieve_episodes, compose_prompt]

## Part 3 - What memory costs
Paste the tables from `reports/hw06/METRICS.md`.

**Compression policy:** keep the newest 4 window messages verbatim, compress older window messages to a ~90-character gist, and retrieve only episodes with importance ≥ 0.4. Facts that fall out of the verbatim window survive through the session summary and episodic memory.

**Best/worst selection:** worst = highest cost per conversation; best = cheapest setting whose mean probe score is within 0.5 of the top score (cheap settings that forget the probe facts are not "best").

## Part 4 - File-based memory
- `file_memory.py`: `load_memory_files`, `build_system_prompt`, `read_last_consolidated`, `needs_consolidation` (>40 non-comment lines or >24 h), `consolidate`.
- Commands `/memory`, `/compact`, `/dream`, `/help` via `/api/chat` or `python scripts/memory_cli.py`.
- Consolidation rule: duplicates (same key, same normalized value) merged; contradictions resolved by newest date; every superseded value kept under "Resolved contradictions"; when an `(unconfirmed)` value beats a `(confirmed)` one the line is marked **REVIEW - possibly resolved incorrectly**. In my run `auth.session_ttl` was resolved incorrectly by "newest wins" (24 h unconfirmed beat 8 h confirmed; the code in `main.py` uses 8 hours).
- 55 → <40 lines; original in `MEMORY_original.md`, consolidated in `MEMORY.md`.
- Generated function `transit_utils.classify_delay` verified against AGENT.md by `tests/test_agent_md_compliance.py` (AST checks for snake_case, type hints, docstrings, no print; normal/boundary/invalid tests).

[Screenshot: /compact output with before/after counts]  [Screenshot: pytest -q passing]

### MongoDB memory vs file-based memory
| Criterion | MongoDB memory | File-based memory (AGENT.md / MEMORY.md) |
|---|---|---|
| Inspectability | Needs Compass/queries; embeddings are opaque float arrays | Plain Markdown, readable and diffable in Git |
| Persistence after restart | Persists as long as the DB volume persists | Persists in the repo and version history; survives DB loss |
| Scalability across many sessions | Indexed per user/session; retrieval selects only top-k, so prompt cost stays bounded | Whole file goes into every prompt; needs consolidation to stay under 40 lines; one shared file, not per user |
| Facts that must not be forgotten | Risky: summaries are lossy and retrieval may not rank a fact in the top-k | Better: always in the system prompt, human-reviewed, and contradictions are audited instead of dropped |

Conclusion: use MongoDB for high-volume per-user conversational memory, and file memory for a small set of durable, must-keep rules and facts.

## AI_USE
Paste `reports/hw06/AI_USE.md`.
