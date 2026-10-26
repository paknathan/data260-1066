"""HW7 Part 4 - run the Bay Wheels agent from the command line (same code path as the UI).

From code/, with Ollama running:
    python scripts/run_bikeshare_hw07.py --csv ../reports/hw07/cases/part4/scenario_membership.csv --label scenario_membership
    python scripts/run_bikeshare_hw07.py --csv ../reports/hw07/cases/part4/scenario_paygo.csv --label scenario_paygo
Saves reports/hw07/raw/part4/<label>/{result.json, pricing_snapshot.txt, pricing_snapshot_meta.json}
and appends the console output to reports/hw07/RUN_LOG.txt.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "scripts"))

from run_agent_hw07 import setup_logging  # noqa: E402

from routers.bikeshare import run_and_save  # noqa: E402

DEFAULT_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
log = logging.getLogger("hw07.part4")


def main() -> None:
    """Run one scenario and print a compact summary."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--url", default=DEFAULT_URL, help="pricing page URL (or a saved copy of it)")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    setup_logging()
    log.info("=" * 78)
    log.info("Nathan Pak (s1066) | HW7 Part 4 | %s | csv=%s | url=%s", args.label, args.csv.name, args.url)
    r = run_and_save(args.csv.read_text(encoding="utf-8"), args.url, args.label)
    for t in r["timeline"]:
        if t["type"] == "tool":
            obs = t["observation"]
            brief = obs.get("error") or json.dumps(obs.get("data"), default=str)[:160]
            log.info("  step %d %s %s -> %s", t["step"], t["tool"], json.dumps(t["input"])[:160], brief)
        elif t["type"] in ("error", "repair"):
            log.info("  [%s] %s", t["type"], t["text"])
    a, e = r.get("agent_costs") or {}, r["engine_check"]
    log.info("DECISION: %s", r["decision"])
    log.info("JUSTIFICATION: %s", r["justification"])
    log.info("agent costs : %s", json.dumps(a))
    log.info("engine check: pay-per-use $%s | membership $%s (fees $%s + residual $%s) | %s rides / %s months | "
             "break-even %s rides/month vs actual %s | cheaper: %s",
             e.get("pay_per_use_total"), e.get("membership_total"), e.get("membership_fees"),
             e.get("membership_residual"), e.get("rides"), e.get("months"), e.get("break_even_rides_per_month"),
             e.get("rides_per_month"), e.get("cheaper")) if e.get("ok") else log.info("engine check: %s", e)
    for s in r["pricing_snapshots"]:
        log.info("snapshot: %s | captured %s | sha256 %s | %s chars", s["source_url"], s["accessed_at"], s["sha256"], s["chars"])
    m = r["metrics"]
    log.info("METRICS: steps=%s model_turns=%s total_time=%ss stop_reason=%s tokens=%s",
             m["steps"], m["model_turns"], m["total_time_s"], m["stop_reason"], m["tokens"])
    log.info("saved: reports/hw07/raw/part4/%s/", r["label"])


if __name__ == "__main__":
    main()
