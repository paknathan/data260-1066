# MEMORY.md - durable facts (consolidated)
<!-- last_consolidated: 2026-10-19T21:50:34+00:00 -->
<!-- source: 53 fact lines; merged 23 duplicate lines; resolved 4 contradictions -->
## Facts
- [2026-09-30] project.name: Municipal Transit Incident Manager
- [2026-10-05] project.port: 8166
- [2026-09-22] project.prefix: s1066
- [2026-09-25] stack.backend: FastAPI with Uvicorn
- [2026-09-14] stack.llm: local Ollama model via llm_adapter.py
- [2026-10-02] user.name: Nathan
- [2026-09-26] user.timezone: America/Los_Angeles
- [2026-10-03] testing.framework: pytest
- [2026-09-21] style.naming: snake_case
- [2026-09-30] ops.ollama_url: http://localhost:11434
- [2026-09-22] repo.collaborators: Sbnikitha, supriyaselvanganesan
- [2026-10-13] user.preferred_contact: SMS text alerts
- [2026-10-15] user.home_station: Winchester light-rail station
- [2026-10-16] user.commute_line: Blue Line light rail
- [2026-09-28] db.sql_database: MySQL database Municipal_rel
- [2026-10-01] incidents.code_format: INC-YYYY-NNN
- [2026-10-01] congestion.code_format: CONG-<LEVEL>-<N>
- [2026-09-28] policy.delete_index: a congestion index with linked incidents cannot be deleted
- [2026-10-17] auth.session_ttl: 24 hours (unconfirmed)
- [2026-10-02] report.formatting: headings 14pt bold, subheadings 12pt bold, body 11pt
- [2026-10-10] db.mongo_database: s1066_doc
- [2026-10-06] incidents.categories: bus, light_rail, subway
- [2026-10-07] incidents.statuses: reported, investigating, resolved
- [2026-10-19] memory.short_term_n: 12
- [2026-10-19] memory.summarize_every: 4 user messages
- [2026-10-19] deadline.hw6: 2026-10-19 at 3 PM
## Resolved contradictions (kept for audit - nothing silently deleted)
- user.preferred_contact: kept "SMS text alerts" (2026-10-13) over "email alerts" (2026-09-20)
- user.home_station: kept "Winchester light-rail station" (2026-10-15) over "Campbell light-rail station" (2026-09-20)
- user.commute_line: kept "Blue Line light rail" (2026-10-16) over "Green Line light rail" (2026-09-21)
- REVIEW - possibly resolved incorrectly: auth.session_ttl: kept "24 hours (unconfirmed)" (2026-10-17) over "8 hours (confirmed)" (2026-09-28)
