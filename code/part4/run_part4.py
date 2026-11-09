"""HW9 Part 4 - self-improving two-agent system: train -> validate -> demo -> test.

Run from code/ (Ollama with qwen3:8b running; Kafka/Redis are NOT needed):
    python -m part4.run_part4 all          # everything below, in order
    python -m part4.run_part4 train        # training_data.json with evaluator repair; mine lessons from repeated failures
    python -m part4.run_part4 validate     # validation_data.json before/after each candidate lesson -> kept/rejected
    python -m part4.run_part4 demo         # 4.1 controlled revision sequence + 4.2 lesson reuse on a later question
    python -m part4.run_part4 test         # test_data.json on the 4 variants -> results table

Variants (cumulative):  baseline = 1 attempt, no lessons | evaluator_repair = up to 2 attempts with feedback |
  lesson_memory = repair + every saved lesson | validated_improvement = repair + only lessons that passed validation.
test_data.json is used only by `test`, after lessons are selected; the test run never creates or edits lessons
(it does not even persist use_count).
"""

import argparse
import copy
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from .agents import (
    CODE_TO_TEMPLATE,
    HERE,
    AnsweringAgent,
    EvaluatorAgent,
    LessonStore,
    ReferenceStore,
    llm_text,
    run_question,
)

RAW = HERE.parents[1] / "reports" / "hw09" / "raw"
VARIANTS = [("Baseline", False, "none"), ("Evaluator Repair", True, "none"),
            ("Lesson Memory", True, "all"), ("Validated Improvement", True, "kept")]
CONTROLLED_CASE = {"id": "C01", "question": "What is the current delay for incident INC-2026-1101?",
                   "injected_initial_answer": "Incident INC-2026-1101 is affecting Route 22 service near downtown. "
                                              "Riders should check for updates before travelling."}
REUSE_QUESTION = {"id": "R01", "question": "What is the current delay for incident INC-2026-1108?"}


def load(name: str) -> list[dict]:
    return json.loads((HERE / name).read_text())


def save_raw(name: str, obj) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False))


class System:
    def __init__(self, llm=llm_text):
        self.reference = ReferenceStore()
        self.answering = AnsweringAgent(self.reference, llm)
        self.evaluator = EvaluatorAgent(self.reference)

    def run_set(self, items, lessons, repair, label, count_use=False) -> list[dict]:
        print(f"\n--- {label}: {len(items)} questions | repair={repair} | lessons={[x['lesson_id'] for x in lessons]} ---")
        out = []
        for item in items:
            r = run_question(item, self.answering, self.evaluator, lessons, repair)
            if count_use:
                for lsn in lessons:
                    lsn["use_count"] += lsn["lesson_id"] in r["lessons_loaded"]
            codes = r["attempts"][0]["evaluation"]["failure_codes"]
            print(f"  [{r['id']}] {r['final_result']:<4} attempts={r['n_attempts']} first={codes or 'PASS'} "
                  f"lessons={r['lessons_loaded'] or '-'} {r['latency_ms'] / 1000:.1f}s | {r['question']}")
            out.append(r)
        return out


def summarize(results: list[dict]) -> dict:
    return {"correct": sum(r["final_result"] == "PASS" for r in results),
            "incorrect": sum(r["final_result"] != "PASS" for r in results),
            "avg_attempts": round(statistics.mean(r["n_attempts"] for r in results), 2),
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1)}


def print_sequence(r: dict) -> None:
    print(f"Question: {r['question']}")
    for a in r["attempts"]:
        ev = a["evaluation"]
        tag = " (INJECTED controlled test case)" if a.get("injected") else ""
        print(f"\n  Attempt {a['attempt']}{tag} | lessons used: {a['lessons_used'] or 'none'} | "
              f"reference consulted: {a['reference_used']}")
        print(f"  Answer: {a['answer']}")
        print(f"  Evaluator -> {ev['result']}: {ev['explanation']}")
        if ev["feedback"]:
            print(f"  Feedback: {ev['feedback']}")
    print(f"\n  Final result: {r['final_result']} after {r['n_attempts']} attempt(s) | latency {r['latency_ms'] / 1000:.1f}s")
    print(f"  Final response: {r['final_answer']}")


# ---- commands ----------------------------------------------------------------------------------
def cmd_train(sys_, args) -> None:
    store = LessonStore()
    if store.lessons and not args.reset:
        sys.exit("lessons.json already has lessons; pass --reset to retrain from scratch")
    store.lessons = []
    results = sys_.run_set(load("training_data.json"), [], repair=True, label="TRAINING (evaluator repair, no lessons)")
    failures = defaultdict(list)  # lesson template -> training cases whose FIRST answer failed that way
    for r in results:
        for code in r["attempts"][0]["evaluation"]["failure_codes"]:
            if r["id"] not in failures[CODE_TO_TEMPLATE[code]]:
                failures[CODE_TO_TEMPLATE[code]].append(r["id"])
    print("\nFailure patterns on first attempts:", dict(failures) or "none")
    for template, ids in failures.items():
        if len(ids) >= args.min_repeats:
            lsn = store.add(template, ids)
            print(f"  LESSON CREATED {lsn['lesson_id']} ({template}) from repeated failures {ids}")
        else:
            print(f"  no lesson for {template}: seen {len(ids)}x (< {args.min_repeats})")
    store.save()
    save_raw("part4_training.json", {"run_at": now(), "summary": summarize(results), "failures": failures,
                                     "lessons": store.lessons, "results": results})


def cmd_validate(sys_, args) -> None:
    store = LessonStore()
    items = load("validation_data.json")
    kept = [lsn for lsn in store.lessons if lsn["status"] == "kept"]
    before = sys_.run_set(items, kept, repair=False, label="VALIDATION before (single attempt, current kept lessons)")
    log = []
    for cand in [lsn for lsn in store.lessons if lsn["status"] == "candidate"]:
        after = sys_.run_set(items, kept + [cand], repair=False, count_use=True,
                             label=f"VALIDATION after adding {cand['lesson_id']}")
        b = {r["id"]: r for r in before}
        fixed = [r["id"] for r in after if r["final_result"] == "PASS" and b[r["id"]]["final_result"] != "PASS"]
        regressed = [r["id"] for r in after if r["final_result"] != "PASS" and b[r["id"]]["final_result"] == "PASS"]
        fail_b = sum(r["final_result"] != "PASS" for r in before)
        fail_a = sum(r["final_result"] != "PASS" for r in after)
        new_unsupported = [r["id"] for r in after if not r["covered"] and r["final_result"] != "PASS"
                           and b[r["id"]]["final_result"] == "PASS"]
        keep = fail_a <= fail_b and not regressed and not new_unsupported
        cand["status"] = "kept" if keep else "rejected"
        cand["validation"] = {"validated_at": now(), "failures_before": fail_b, "failures_after": fail_a,
                              "fixed": fixed, "regressed": regressed, "new_unsupported_answers": new_unsupported,
                              "decision": cand["status"]}
        print(f"  => {cand['lesson_id']}: failures {fail_b} -> {fail_a}, fixed={fixed}, regressed={regressed}, "
              f"new unsupported={new_unsupported} => {cand['status'].upper()}")
        log.append({"lesson_id": cand["lesson_id"], **cand["validation"],
                    "before": summarize(before), "after": summarize(after), "after_results": after})
        if keep:
            kept.append(cand)
            before = after
    store.save()
    save_raw("part4_validation.json", {"run_at": now(), "log": log, "lessons": store.lessons})


def cmd_demo(sys_, args) -> None:
    store = LessonStore()
    print("\n================ 4.1 Controlled revision sequence ================")
    c = CONTROLLED_CASE
    r1 = run_question(c, sys_.answering, sys_.evaluator, [], repair=True, inject_initial=c["injected_initial_answer"])
    print_sequence(r1)

    print("\n================ 4.2 Lesson created earlier, reused on a later question ================")
    lessons = store.select("kept") or store.select("all")
    if not lessons:
        sys.exit("no lessons yet - run train (and validate) first")
    for lsn in lessons:
        print(f"Stored {lsn['lesson_id']} (status={lsn['status']}, created {lsn['created_at']} from failed answers "
              f"{lsn['source_cases']}, use_count={lsn['use_count']}): {lsn['failure_pattern']}")
    print("\n[without lessons]")
    r_without = run_question(REUSE_QUESTION, sys_.answering, sys_.evaluator, [], repair=False)
    print_sequence(r_without)
    print("\n[with stored lessons loaded]")
    r2 = run_question(REUSE_QUESTION, sys_.answering, sys_.evaluator, lessons, repair=True)
    for lsn in lessons:
        if lsn["lesson_id"] in r2["lessons_loaded"]:
            lsn["use_count"] += 1
            print(f"Loaded {lsn['lesson_id']} -> use_count now {lsn['use_count']}")
    print_sequence(r2)
    store.save()
    save_raw("part4_demo.json", {"run_at": now(), "controlled_revision": r1, "reuse_without_lessons": r_without,
                                 "reuse_with_lessons": r2, "lessons": store.lessons})


def cmd_test(sys_, args) -> None:
    store = LessonStore()
    items = load("test_data.json")
    rows, detail = [], {}
    for name, repair, which in VARIANTS:
        lessons = copy.deepcopy(store.select(which))  # read-only: the test run never changes lessons.json
        res = sys_.run_set(items, lessons, repair, label=f"TEST - {name}")
        rows.append({"variant": name, **summarize(res), "lessons": [x["lesson_id"] for x in lessons]})
        detail[name] = res
    table = ["| Variant | Correct answers | Incorrect answers | Average attempts | Average latency |",
             "|---|---|---|---|---|"]
    table += [f"| {r['variant']} | {r['correct']}/{len(items)} | {r['incorrect']}/{len(items)} | {r['avg_attempts']:.2f} | "
              f"{r['avg_latency_ms'] / 1000:.1f} s |" for r in rows]
    print("\n=== Final test results (test_data.json, " + str(len(items)) + " questions) ===")
    print("\n".join(table))
    for r in rows:
        print(f"  {r['variant']}: lessons={r['lessons'] or '-'}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part4_results_table.md").write_text("\n".join(table) + "\n")
    save_raw("part4_test.json", {"run_at": now(), "rows": rows, "results": detail})


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["train", "validate", "demo", "test", "all"])
    ap.add_argument("--reset", action="store_true", help="train: discard existing lessons.json")
    ap.add_argument("--min-repeats", type=int, default=2, help="failures of one pattern needed to create a lesson")
    args = ap.parse_args()
    s = System()
    if args.command == "all":
        args.reset = True
        for f in (cmd_train, cmd_validate, cmd_demo, cmd_test):
            f(s, args)
    else:
        {"train": cmd_train, "validate": cmd_validate, "demo": cmd_demo, "test": cmd_test}[args.command](s, args)


if __name__ == "__main__":
    main()
