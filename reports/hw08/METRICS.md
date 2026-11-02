# METRICS.md - HW8 (Nathan Pak, SID4 1066, PREFIX s1066)

All values come from my own runs on 2026-11-02 (raw files in reports/hw08/raw/, terminal output in RUN_LOG.txt).
Kafka 3.7.1 (KRaft, single broker, Docker container s1066_kafka). Model: qwen3:8b via local Ollama (Parts 1-2).
Part 3 agents ran with `--rule` (deterministic handlers, no model) so failure behavior is not mixed with model latency.

## Part 1 - Request/response over Kafka
| Metric | Value |
|---|---|
| Topics | s1066_incident_requests -> s1066_incident_responses |
| CREATE_INCIDENT | success, incident_id e3598f5e-53e4-42b0-bfd6-47a5e2e049c8 |
| GET_INCIDENT | success, same incident returned |
| correlation_id preserved | yes (ebedbea2-... create, 245d0f8b-... get) |
| Evidence | raw/part1_demo.json, raw/kafka_flow.jsonl |

## Part 2 - Three-agent pipeline (Planner -> Writer -> Reviewer)
| Metric | Value |
|---|---|
| Topics (partitions) | s1066_inbox (1), s1066_tasks (2), s1066_drafts (1), s1066_final (1), s1066_dead_letter (1) |
| correlation_id | ef749bee-8cb6-4b3e-9df2-50808d6abe17 (unchanged at every stage) |
| Final status | approved |
| End-to-end latency | 23.2 s (Planner ~10.0 s, Writer ~5.0 s, Reviewer ~8.2 s) |
| Path | inbox[p0 o0] -> tasks[p1 o0] -> drafts[p0 o0] -> final[p0 o0] |
| Evidence | raw/part2_final_ef749bee.json, raw/agents_flow.jsonl |

## Part 3 - Failure behavior
| Scenario | Before fix | After fix | Evidence |
|---|---|---|---|
| Duplicate delivery (same correlation_id sent twice) | 2 finals; each agent processed 2x | 1 final; Planner skipped 1 duplicate | part3_dup_before/after.json |
| Consumer killed mid-work (kill -9 Writer, 20 s task) | offset committed on receive; LAG 0; message lost (no final) | offset not committed; LAG 1; redelivered [p1 o5] and completed | part3_crash_before/after.json |
| Poison message (non-JSON) | retried forever (30 failures in 30 s); later message blocked | 3 attempts -> s1066_dead_letter; later message completed 1 ms after | part3_poison_before/after.json |
| Ordering, 20 msgs (VERIFY_SEED 261066), 2 partitions, 2 Writers | unkeyed: 1/4 entities in order | keyed by entity: 4/4 in order, 1 partition per entity, 20/20 finals | part3_order_unkeyed/keyed.json |

Unit tests: tests/test_kafka_incident.py + tests/test_kafka_agents.py (in-memory fake Kafka), all passing.
