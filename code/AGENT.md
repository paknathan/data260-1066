# AGENT.md - Municipal Transit Incident Manager (s1066)

<!-- Durable project + agent instructions. Loaded into the system prompt by file_memory.build_system_prompt(). -->

## Project description
1. This project is the Municipal Transit Incident Manager for DATA-260 (SID4 1066). It tracks bus, light-rail and subway incidents, congestion indexes, and a chat assistant with memory.
2. The app always runs on PORT_BASE 8166; the MongoDB database is `s1066_doc`; SEED is 1066 and VERIFY_SEED is 261066.

## Technology stack
3. Backend is FastAPI + Uvicorn; relational data uses SQLAlchemy (MySQL), document and memory data use PyMongo (MongoDB).
4. The chat model is a local Ollama model called only through `llm_adapter.py` - never call a hosted/paid API.

## Coding conventions
5. Use snake_case names, type hints on every parameter and return value, and a one-line docstring on every public function.
6. Validate inputs explicitly and raise `ValueError` (or `HTTPException` in routes) with a clear message; never fail silently.
7. Library code must not use `print()`; return values instead so code is testable.

## Testing approach
8. Every new helper gets pytest tests in `tests/` covering a normal case, a boundary case and an invalid input. Run with `pytest -q`.
9. `make verify-hw06` (scripts/verify_hw06.py) must pass on the tagged commit before submission.

## Prohibited actions
10. Never commit secrets (`.env`, passwords, `key.pem`), never hard-code credentials, and never drop or overwrite MongoDB collections from application code.
11. Do not modify the Part 1 `transit_incidents` collection schema when working on memory features.
