# HW6 - run steps (copy everything into `Data260/data260-1066/code/`, overwrite when asked)

```bash
cd ~/Desktop/Data260/data260-1066/code
source venv/bin/activate
pip install pymongo pyyaml pytest
export DATABASE_URL="mysql+pymysql://root:password@localhost:3306/Municipal_rel"   # whatever you used in HW5
export OLLAMA_MODEL="llama3.2:3b"        # <- the model from your HW1 adapter (check: ollama list)
ollama pull nomic-embed-text             # optional; without it a hashing embedding is used
brew services start mongodb-community    # or however you start mongod
```

## 1. Start the server (terminal A) - port 8166
```bash
python main.py
```

## 2. Part 1 screenshots (terminal B, show your name: run `whoami` or `echo "Nathan Pak"` first)
```bash
curl -s -X POST localhost:8166/api/items -H 'Content-Type: application/json' \
  -d '{"title":"Bus 23 breakdown","description":"Engine failure on Winchester Blvd","category":"bus","event_time":"2026-10-19T08:15:00"}'
curl -s localhost:8166/api/items
curl -s localhost:8166/api/items/<ID>
curl -s -X PUT localhost:8166/api/items/<ID> -H 'Content-Type: application/json' \
  -d '{"title":"Bus 23 breakdown","status":"resolved","category":"bus","event_time":"2026-10-19T08:15:00"}'
curl -s -i -X DELETE localhost:8166/api/items/<ID>
# validation (expect 422 / 400 / 404)
curl -s -X POST localhost:8166/api/items -H 'Content-Type: application/json' -d '{"title":"x","category":"ferry"}'
curl -s -X POST localhost:8166/api/items -H 'Content-Type: application/json' -d '{"title":"x","category":"bus","event_time":"yesterday"}'
curl -s localhost:8166/api/items/123
```
Add 2-3 more items, then screenshot Compass → `s1066_doc.transit_incidents`.

## 3. Part 2 - open http://localhost:8166/static/chat.html, send ≥10 messages (user "nathan")
Then screenshot:
```bash
curl -s localhost:8166/api/memory/nathan | python -m json.tool
curl -s localhost:8166/api/aggregate/nathan | python -m json.tool
```
Compass: `messages`, `summaries`, `episodes`.

## 4. Part 3 experiments (start this EARLY - it is the slow part; server can stay running)
```bash
python scripts/run_memory_experiments.py --fast      # ~4 x 35 model calls
# out of time? python scripts/run_memory_experiments.py --fast --turns 15   (say so in the report)
```
Outputs: `reports/hw06/METRICS.md`, `RUN_LOG.txt`, `raw/*.csv`, `raw/probe_scores.json`, `raw/experiment_summary.json`, `raw/chat_log.jsonl`.

## 5. Part 4
```bash
python scripts/make_memory_fixture.py           # writes 55-line MEMORY_original.md and MEMORY.md
python scripts/memory_cli.py /memory | tail -5
python scripts/memory_cli.py /compact           # screenshot: before/after counts
wc -l MEMORY_original.md MEMORY.md
pytest -q tests                                  # screenshot: AGENT.md compliance test passing
```
(`/help`, `/memory`, `/compact`, `/dream` also work in the chat page.)

## 6. Commit, tag, verify
```bash
git add -A && git commit -m "HW6: MongoDB doc API, chat memory, memory cost experiments, file memory"
git tag -f hw6
python scripts/verify_hw06.py                    # writes reports/hw06/verification.json
git add reports/hw06/verification.json && git commit -m "HW6 verification" && git tag -f hw6
git push && git push -f origin hw6
```
Report: fill `reports/hw06/REPORT_DRAFT.md` placeholders + screenshots → export `Pak_HW6.pdf` (also save as `reports/hw06/report.pdf`).
