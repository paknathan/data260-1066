# AI_USE - HW6 (Nathan Pak, SID4 1066)

**1. What I used an AI assistant for vs. what I did myself**
I used Claude to draft the HW6 code: the MongoDB validators and connection module, the Part 2 memory logic (`memory_core.py`), the chat/memory/aggregate routes, the Part 3 experiment runner and probes, the Part 4 file-memory module and consolidation, and the `verify_hw06.py` smoke test. I chose the transit-incident domain fields (carried over from HW5), ran MongoDB + Ollama locally, ran every experiment and the verify script myself, took the screenshots, checked the generated numbers against the raw CSV/JSON, and wrote the analysis.

**2. One AI-produced output that was wrong/unsuitable (and one thing I verified)**
My original `database.py` (also AI-assisted, HW6 Part 1 draft) created a hard-coded MySQL engine (`mysql+pymysql://root:password@...`) at import time, and `routers/documents.py` imported from it. That meant the MongoDB router silently depended on a second SQL engine with a hard-coded password, separate from the `DATABASE_URL` engine in `main.py` - two `Base` objects and a credential in source code. The first draft of the document routes also used the Pydantic v1 `item.dict()` API, and would have stored Python `Enum` objects that PyMongo cannot encode once enums were added.

**3. How I detected/verified it**
Reading the import chain (`main.py -> routers/documents.py -> database.py`) showed the extra engine; AGENT.md rule 10 forbids hard-coded credentials. For the enum issue, I checked that a created document comes back with plain strings (`"status": "reported"`, `"category": "bus"`) and that an invalid category returns a 422 with a field-level message. I verified the consolidation result independently by checking `compact_report.json` against the fixture: 4 contradictory keys in `scripts/make_memory_fixture.py`, 4 entries in the "Resolved contradictions" section, and the `auth.session_ttl` case correctly flagged.

**4. What I changed and why it works now**
`database.py` is now MongoDB-only (plus a bare `declarative_base` for the legacy `models.py`), reads `MONGO_URI` from the environment, and creates `$jsonSchema` validators for all four collections. Routes use `model_dump()` with `use_enum_values=True`, so stored documents contain plain strings that also pass the server-side validator. `pytest -q` and `make verify-hw06` both pass on the tagged commit.

> Edit any line above that does not match what you actually did before submitting.
