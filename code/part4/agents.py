"""HW9 Part 4 - Answering Agent, Evaluator Agent, lesson store and the revision loop.

Agent communication: in-process JSON-style messages.
    question --> AnsweringAgent.answer() --> {"answer", "lessons_used", "reference_used"}
             --> EvaluatorAgent.evaluate() --> {"result": PASS|REVISE, "explanation", "feedback", "failure_codes"}
    REVISE  --> AnsweringAgent.answer(previous_answer, feedback) --> EvaluatorAgent.evaluate() --> stop.
At most MAX_ATTEMPTS = 2 answers per question; the second evaluation is final (PASS, or FAIL if it still says REVISE).

The Answering Agent is the local LLM (qwen3:8b through the HW1 adapter). It does NOT see the reference data by
default; a lesson whose action is "consult_reference" makes it look the question up before answering.
The Evaluator Agent is deterministic: it finds the reference records for the question and checks that the answer
states every required fact (or, for questions with no record, that it declines instead of inventing details).
"""

import json
import re
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_ATTEMPTS = 2

CODE_RE = re.compile(r"INC-\d{4}-\d{4}")
DECLINE_RE = re.compile(
    r"(don'?t|do not|does not|doesn'?t) have|no (record|information|data|details)|not (available|found|listed|in (the|our)"
    r"( reference)? (records?|data))|unable to (find|confirm|provide|locate)|can(no|')t (find|confirm|provide|locate)|"
    r"no reference|not aware of", re.I)
SPECIFIC_CLAIM_RE = re.compile(r"\b\d+\s*(minutes?|mins?)\b|\$\s?\d", re.I)
MINUTES_RE = re.compile(r"\b(\d+)\s*(?:minutes?|mins?)\b", re.I)

# which incident fields a question asks about (evaluator's reading of the question; no answers stored in inputs)
INTENTS = {
    "delay_minutes": r"delay|how long|late\b|minutes",
    "status": r"status|resolved|still|cleared|over\b",
    "cause": r"cause|why|what happened|reason",
    "rider_guidance": r"what should riders|what should i|detour|alternative|options|how (can|do) (i|riders) get",
}


def llm_text(system: str, user: str) -> str:
    """Default model call: the HW1 adapter (Ollama qwen3:8b) via kafka_agents.llm."""
    from kafka_agents import llm
    return llm.ask_text(system, user)


# ---- reference dataset ---------------------------------------------------------------------------
class ReferenceStore:
    def __init__(self, path: Path = HERE / "reference_data.json"):
        data = json.loads(Path(path).read_text())
        self.status_patterns = data["status_patterns"]
        self.incidents = {i["incident_code"]: i for i in data["incidents"]}
        self.policies = data["policies"]

    def lookup(self, question: str) -> list[dict]:
        """Reference records relevant to a question (incident codes it names + policies whose topic it mentions)."""
        recs = [{"kind": "incident", **self.incidents[c]} for c in CODE_RE.findall(question) if c in self.incidents]
        recs += [{"kind": "policy", **p} for p in self.policies if re.search(p["match"], question, re.I)]
        return recs

    @staticmethod
    def public_view(rec: dict) -> dict:
        """What the Answering Agent is shown (facts only, no evaluator matching rules)."""
        return {k: v for k, v in rec.items() if not k.endswith("patterns") and k not in ("match", "kind")}


# ---- lessons ---------------------------------------------------------------------------------
# One template per failure family. The evaluator's failure codes map onto these.
LESSON_TEMPLATES = {
    "REFERENCE_VALUE": {
        "codes": ["MISSING_FACT", "WRONG_VALUE"],
        "failure_pattern": "The answer omits or invents a specific value that the reference dataset records "
                           "(incident delay, status, cause, detour, fare or policy number).",
        "correction": "Check the reference dataset before answering questions about incidents, fares or policies, "
                      "and state the recorded values exactly.",
        "trigger": r"INC-\d{4}-\d{4}|delay|status|resolved|cause|detour|fare|pass|refund|policy|severity|alert|"
                   r"bike|bicycle|lost|suspicious|elevator|how much|how long|how many",
        "action": "consult_reference",
    },
    "NO_RECORD": {
        "codes": ["UNSUPPORTED_ANSWER"],
        "failure_pattern": "The answer gives delays, fares or causes for an incident or topic that has no record "
                           "in the reference dataset.",
        "correction": "If the reference dataset has no record for the incident or topic, say you do not have that "
                      "information and point riders to official service alerts; do not guess numbers or causes.",
        "trigger": r".",
        "action": "consult_reference",
    },
}
CODE_TO_TEMPLATE = {c: name for name, t in LESSON_TEMPLATES.items() for c in t["codes"]}


class LessonStore:
    def __init__(self, path: Path = HERE / "lessons.json"):
        self.path = Path(path)
        self.lessons: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self) -> None:
        self.path.write_text(json.dumps(self.lessons, indent=2, ensure_ascii=False))

    def add(self, template: str, source_cases: list[str]) -> dict:
        t = LESSON_TEMPLATES[template]
        lesson = {"lesson_id": f"lesson_{len(self.lessons) + 1:03d}", "failure_pattern": t["failure_pattern"],
                  "correction": t["correction"], "created_at": date.today().isoformat(), "use_count": 0,
                  "template": template, "trigger": t["trigger"], "action": t["action"],
                  "source_cases": source_cases, "status": "candidate", "validation": None}
        self.lessons.append(lesson)
        return lesson

    def select(self, which: str) -> list[dict]:
        """which: none | all (every saved lesson) | kept (only lessons that passed validation)."""
        if which == "none":
            return []
        return [lsn for lsn in self.lessons if which == "all" or lsn["status"] == "kept"]

    @staticmethod
    def relevant(lessons: list[dict], question: str) -> list[dict]:
        return [lsn for lsn in lessons if re.search(lsn["trigger"], question, re.I)]


# ---- agents ----------------------------------------------------------------------------------
class AnsweringAgent:
    SYSTEM = ("You are the Answering Agent of a municipal transit incident assistant (San Jose area). Answer the "
              "rider's question directly in at most 80 words.")

    def __init__(self, reference: ReferenceStore, llm=llm_text):
        self.reference = reference
        self.llm = llm

    def answer(self, question: str, lessons: list[dict], previous: str | None = None,
               feedback: str | None = None) -> dict:
        system = self.SYSTEM
        if lessons:
            system += "\n\nLessons learned from earlier evaluator feedback (apply them):\n" + "\n".join(
                f"- [{lsn['lesson_id']}] Problem: {lsn['failure_pattern']} Fix: {lsn['correction']}" for lsn in lessons)
        user = f"Question: {question}"
        reference_used = any(lsn["action"] == "consult_reference" for lsn in lessons)
        if reference_used:
            recs = [ReferenceStore.public_view(r) for r in self.reference.lookup(question)]
            user += ("\n\nReference dataset records for this question:\n" + json.dumps(recs, indent=1) if recs else
                     "\n\nReference dataset lookup: no record found for this question.")
        if feedback:
            user += (f"\n\nYour previous answer:\n{previous}\n\nEvaluator feedback:\n{feedback}\n\n"
                     "Write a corrected answer that fixes every point in the feedback.")
        return {"answer": self.llm(system, user).strip(), "lessons_used": [lsn["lesson_id"] for lsn in lessons],
                "reference_used": reference_used}


class EvaluatorAgent:
    def __init__(self, reference: ReferenceStore):
        self.reference = reference

    def requirements(self, question: str, rec: dict) -> list[tuple[str, str, list[str]]]:
        """(fact name, reference value, regexes that must all appear in the answer) for one record."""
        if rec["kind"] == "policy":
            return [(rec["policy_id"], rec["fact"], rec["required_patterns"])]
        fields = [f for f, rx in INTENTS.items() if re.search(rx, question, re.I)] or ["delay_minutes", "status"]
        pats = {"delay_minutes": [rf"\b{rec['delay_minutes']}\b"],
                "status": [self.reference.status_patterns[rec["status"]]],
                "cause": rec["cause_patterns"], "rider_guidance": rec["guidance_patterns"]}
        return [(f"{rec['incident_code']}.{f}", str(rec[f]), pats[f]) for f in fields]

    def evaluate(self, question: str, answer: str) -> dict:
        recs = self.reference.lookup(question)
        if not recs:  # nothing in the reference: the only correct behaviour is to decline without specifics
            declined = bool(DECLINE_RE.search(answer))
            claims = SPECIFIC_CLAIM_RE.findall(answer)
            if declined and not claims:
                return {"result": "PASS", "covered": False, "failure_codes": [], "feedback": None,
                        "explanation": "No reference record exists; the answer correctly declines without inventing details."}
            return {"result": "REVISE", "covered": False, "failure_codes": ["UNSUPPORTED_ANSWER"],
                    "explanation": "No reference record exists for this question, but the answer "
                                   + ("states specific values not supported by the reference." if claims
                                      else "does not say the information is unavailable."),
                    "feedback": "The reference dataset has no record for this incident or topic. Say that you do not "
                                "have that information and point riders to official service alerts. Do not state "
                                "delays, fares or causes."}
        missing, codes, required = [], [], []
        for rec in recs:
            for name, value, pats in self.requirements(question, rec):
                required.append((name, value))
                if not all(re.search(p, answer, re.I) for p in pats):
                    missing.append((name, value))
                    wrong_minutes = name.endswith("delay_minutes") and MINUTES_RE.search(answer)
                    codes.append("WRONG_VALUE" if wrong_minutes else "MISSING_FACT")
        if not missing:
            return {"result": "PASS", "covered": True, "failure_codes": [], "feedback": None,
                    "explanation": "All required facts match the reference dataset."}
        return {"result": "REVISE", "covered": True, "failure_codes": sorted(set(codes)),
                "explanation": "Missing or incorrect: " + ", ".join(n for n, _ in missing) + ".",
                "feedback": "The answer does not match the reference dataset. Missing or incorrect: "
                            + ", ".join(n for n, _ in missing) + ". The answer must state all of these facts: "
                            + "; ".join(f"{n} = {v}" for n, v in required) + ". State these values exactly."}


# ---- revision loop -----------------------------------------------------------------------------
def run_question(item: dict, answering: AnsweringAgent, evaluator: EvaluatorAgent, lessons: list[dict],
                 repair: bool, inject_initial: str | None = None) -> dict:
    """One question through the workflow. repair=False -> single attempt (baseline)."""
    t0 = time.perf_counter()
    question = item["question"]
    relevant = LessonStore.relevant(lessons, question)
    attempts, previous, feedback = [], None, None
    for n in range(1, (MAX_ATTEMPTS if repair else 1) + 1):
        if n == 1 and inject_initial is not None:  # controlled test case: deliberately incomplete first answer
            out = {"answer": inject_initial, "lessons_used": [], "reference_used": False, "injected": True}
        else:
            out = answering.answer(question, relevant, previous, feedback)
        ev = evaluator.evaluate(question, out["answer"])
        attempts.append({"attempt": n, **out, "evaluation": ev})
        if ev["result"] == "PASS":
            break
        previous, feedback = out["answer"], ev["feedback"]
    final = attempts[-1]
    return {"id": item["id"], "question": question, "attempts": attempts, "n_attempts": len(attempts),
            "final_answer": final["answer"], "final_result": "PASS" if final["evaluation"]["result"] == "PASS" else "FAIL",
            "covered": final["evaluation"]["covered"], "lessons_loaded": [lsn["lesson_id"] for lsn in relevant],
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
