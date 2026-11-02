"""HW8 Part 2 - Writer agent: s1066_tasks (2 partitions) -> s1066_drafts.

Follows the Planner's steps and writes a draft answer with the local model.
Run from code/:  python writer.py   (second instance for Part 3: python writer.py --instance writer-2)
"""

from kafka_agents import llm
from kafka_agents.base import agent_args, run_agent
from kafka_agents.config import DRAFTS, TASKS

SYSTEM = ("You are the Writer in a municipal transit incident assistant. Follow the plan steps and write a clear, "
          "factual answer for riders in at most 120 words. Do not invent specific times, numbers or names that are "
          "not in the question; say what riders should do next.")


def make_handler(args):
    def handle(msg: dict) -> tuple[dict, str | None]:
        steps = msg["plan"]["steps"]
        if args.rule:
            draft = f"Draft answer to: {msg['question']} (followed {len(steps)} plan steps)"
        else:
            user = f"Question: {msg['question']}\nPlan steps:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
            draft = llm.ask_text(SYSTEM, user)
        if not draft:
            raise ValueError("writer produced an empty draft")
        out = {"stage": "draft", "question": msg["question"], "plan": msg["plan"], "draft": draft,
               "writer": "rule" if args.rule else llm.model_name(), "writer_instance": args.instance}
        for k in ("entity", "seq", "key_mode"):
            if k in msg:
                out[k] = msg[k]
        return out, None
    return handle


if __name__ == "__main__":
    a = agent_args("Writer agent").parse_args()
    run_agent("writer", TASKS, DRAFTS, make_handler(a), a)
