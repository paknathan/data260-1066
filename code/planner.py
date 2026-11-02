"""HW8 Part 2 - Planner agent: s1066_inbox -> s1066_tasks.

Reads a user question, asks the local model (qwen3:8b) for a short plan, and publishes one task for the Writer.
Run from code/:  python planner.py            (--rule: deterministic plan without the model)
"""

from kafka_agents import llm
from kafka_agents.base import agent_args, run_agent
from kafka_agents.config import INBOX, TASKS

SYSTEM = ("You are the Planner in a municipal transit incident assistant. Break the user's question into 2-4 short, "
          "concrete steps a writer should follow to answer it. Return JSON: "
          '{"intent": "<one short phrase>", "steps": ["...", "..."], "audience": "<who the answer is for>"}')


def rule_plan(question: str) -> dict:
    return {"intent": "answer transit incident question",
            "steps": ["Identify the incident type, route and impact in the question",
                      "Explain the likely cause and expected delay", "Give riders a clear next action"],
            "audience": "transit riders"}


def make_handler(args):
    def handle(msg: dict) -> tuple[dict, str | None]:
        question = str(msg["question"]).strip()
        if not question:
            raise ValueError("empty question")
        plan = rule_plan(question) if args.rule else llm.ask_json(SYSTEM, question)
        if not isinstance(plan.get("steps"), list) or not plan["steps"]:
            raise ValueError(f"planner model returned no steps: {plan}")
        task = {"stage": "task", "question": question, "plan": plan, "created_at": msg.get("created_at"),
                "planner": "rule" if args.rule else llm.model_name()}
        for k in ("entity", "seq", "key_mode"):  # Part 3 ordering fields pass through untouched
            if k in msg:
                task[k] = msg[k]
        # Part 3 keyed mode: all messages for one entity go to the same s1066_tasks partition
        key = str(msg["entity"]) if msg.get("key_mode") == "entity" and msg.get("entity") else None
        return task, key
    return handle


if __name__ == "__main__":
    a = agent_args("Planner agent").parse_args()
    run_agent("planner", INBOX, TASKS, make_handler(a), a)
