# AI_USE.md - HW8 (Nathan Pak, SID4 1066)

## 1. What I used an AI assistant for, and what I did myself

I used Claude (an AI assistant) heavily on this homework. It drafted most of the code:

- Part 1: the Kafka request/response client, worker, FastAPI wrapper, schema validation, docker-compose file and homework_demo.py.
- Part 2: the shared agent runner (kafka_agents/base.py), planner.py, writer.py, reviewer.py, send_question.py and the topic-creation script.
- Part 3: the failure switches in the agent runner (idempotency, commit timing, bounded retries and dead letter, partition key), part3.py, and the in-memory fake Kafka used by the unit tests.

It also drafted scripts/verify_hw08.py, METRICS.md and first drafts of the report paragraphs.

What I did myself:

- Chose the domain (municipal transit incidents) and ran everything on my own machine: Kafka in Docker, the local Ollama qwen3:8b model, all agents in separate terminals.
- Created the topics with the Kafka CLI, ran every before/after experiment, killed the Writer, read the consumer-group offsets, and took all screenshots.
- Checked each output against the assignment and reported problems back so they could be fixed.
- Committed, tagged and wrote the final report.

All numbers in the report come from my own runs (RUN_LOG.txt and reports/hw08/raw/), not from the assistant.

## 2. One AI-produced output that was wrong or unsuitable

The first consumer-death procedure the assistant gave me was unreliable, and part3.py reported a misleading result. I was told to start part3.py and then run `pkill -9 -f writer.py` by hand in another terminal while the Writer was working. In two runs my kill arrived after the Writer had already finished its 20-second task, so nothing was actually interrupted. part3.py still printed "message redelivered after restart and completed", because it printed that whenever a final answer arrived. For the "before" run (commit before processing) it even reported success instead of a lost message.

## 3. How I detected the problem

The Writer's own log did not match the summary. It showed `SENT -> s1066_drafts` and `COMMITTED offset 5 after processing` before `Killed: 9`, so the process was killed after the work was done. The consumer-group command also showed LAG 0 in both runs, and the part3 summary listed only one "received" event from the same Writer, with no second delivery. A real redelivery needs a second "received" from the restarted Writer.

## 4. What I changed, and why it works now

I replaced the manual kill with one command that sends the message, waits 5 seconds (inside the 20-second processing window), runs kill -9, and reads the consumer-group offsets right away:

`python part3.py crash --label after --wait 90 & sleep 5; pkill -9 -f writer.py; sleep 1; docker exec s1066_kafka ... kafka-consumer-groups.sh --describe --group s1066_writer_group; wait`

With the timing fixed, the results are correct and consistent with the logs:

- Before (commit before processing): `COMMITTED offset 5 BEFORE processing`, `Killed: 9`, LAG 0, the restarted Writer received nothing, so the message was lost.
- After (commit after processing): `Killed: 9` with no commit, LAG 1, and the restarted Writer received the same `[p1 o5]` again and completed it.

scripts/verify_hw08.py no longer trusts the summary line. It only accepts the after run if the Writer received the message at least twice (a real redelivery).
