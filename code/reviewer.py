"""HW8 Part 2 - Reviewer agent: s1066_drafts -> s1066_final.

Checks the draft against the question and plan and publishes the final JSON (status + answer).
Run from code/:  python reviewer.py
"""

from datetime import datetime, timezone

from kafka_agents import llm
from kafka_agents.base import agent_args, run_agent
from kafka_agents.config import DRAFTS, FINAL

SYSTEM = ("You are the Reviewer in a municipal transit incident assistant. Check the draft answer: it must answer "
          "the question, follow the plan, be clear for riders, and not invent facts that are not in the question. "
          "Fix small problems yourself. Return JSON: "
          '{"status": "approved" or "rejected", "answer": "<final answer text>", "review_notes": "<one sentence>"}')


def make_handler(args):
    def handle(msg: dict) -> tuple[dict, str | None]:
        if args.rule:
            review = {"status": "approved", "answer": msg["draft"], "review_notes": "rule-based review"}
        else:
            user = (f"Question: {msg['question']}\nPlan: {llm.dumps(msg['plan'])}\nDraft answer:\n{msg['draft']}")
            review = llm.ask_json(SYSTEM, user)
        status = str(review.get("status", "")).lower()
        if status not in ("approved", "rejected") or not str(review.get("answer", "")).strip():
            raise ValueError(f"reviewer model returned an invalid review: {review}")
        final = {"stage": "final", "status": status, "answer": review["answer"].strip(),
                 "review_notes": review.get("review_notes", ""), "question": msg["question"],
                 "pipeline": {"plan_steps": len(msg["plan"]["steps"]), "writer_instance": msg.get("writer_instance"),
                              "model": "rule" if args.rule else llm.model_name()},
                 "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        for k in ("entity", "seq", "key_mode"):
            if k in msg:
                final[k] = msg[k]
        return final, None
    return handle


if __name__ == "__main__":
    a = agent_args("Reviewer agent").parse_args()
    run_agent("reviewer", DRAFTS, FINAL, make_handler(a), a)
