import argparse
import json
import sys
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field, field_validator, ValidationError

from src.model_client import complete, ModelClient

# ---------------------------------------------------------------------------
# Config (Part 0 values would normally be pulled in from your SID4 config
# module -- import them here instead of hardcoding once that module exists)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_TASK = "tag_and_summarize"
DEFAULT_TURN_CEILING = 6          # Part 4 compares ceilings of 2 and 10 explicitly;
                                    # this is just the fallback if state doesn't set one.
NUM_TAGS = 3
TAG_MIN_CHARS = 3
TAG_MAX_CHARS = 30
MAX_SUMMARY_WORDS = 25


# ---------------------------------------------------------------------------
# Step 2: Shared state
# ---------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    # Inputs
    title: str                       # e.g. "Route 22 -- Mechanical Breakdown"
    content: str                     # free-text incident description / details
    email: str                       # pass-through; not acted on by this graph yet
    strict: bool                     # True = hard-fail-and-retry on schema violations;
                                      # False = attempt a local auto-fix first
    task: str                        # which prompt template to run
    llm: Any                         # optional model name override (str) or
                                      # a pre-built ModelClient instance

    # Working memory
    planner_proposal: Dict[str, Any]   # {"candidate_tags": [...], "draft_summary": "..."}
    reviewer_feedback: Dict[str, Any]  # {"valid": bool, "tags":..., "summary":..., "error":...}

    # Loop control
    turn_count: int
    turn_ceiling: int


# ---------------------------------------------------------------------------
# Part 4 (1): Pydantic schema for the Reviewer's final output
# ---------------------------------------------------------------------------
class ReviewedOutput(BaseModel):
    tags: List[str] = Field(..., min_length=NUM_TAGS, max_length=NUM_TAGS)
    summary: str

    @field_validator("tags")
    @classmethod
    def check_tag_shape(cls, v: List[str]) -> List[str]:
        for t in v:
            if not isinstance(t, str) or not (TAG_MIN_CHARS <= len(t.strip()) <= TAG_MAX_CHARS):
                raise ValueError(
                    f"tag {t!r} must be a string of {TAG_MIN_CHARS}-{TAG_MAX_CHARS} characters"
                )
        return v

    @field_validator("summary")
    @classmethod
    def check_summary_length(cls, v: str) -> str:
        word_count = len((v or "").split())
        if word_count == 0 or word_count > MAX_SUMMARY_WORDS:
            raise ValueError(
                f"summary must be 1-{MAX_SUMMARY_WORDS} words, got {word_count}"
            )
        return v


# ---------------------------------------------------------------------------
# Model adapter call -- routed through src/model_client.py only, per spec.
# Honors state["llm"] as an optional per-run model override.
# ---------------------------------------------------------------------------
def call_model(state: AgentState, system_prompt: str, user_prompt: str) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    llm_override = state.get("llm")
    if isinstance(llm_override, ModelClient):
        return llm_override.complete(messages=messages, response_format="json")
    if isinstance(llm_override, str) and llm_override:
        return ModelClient(model=llm_override).complete(messages=messages, response_format="json")
    return complete(messages=messages, response_format="json")


# ---------------------------------------------------------------------------
# Prompt templates, keyed by state["task"]. Only one task exists today;
# this makes it straightforward to add more later without touching the
# node functions themselves.
# ---------------------------------------------------------------------------
def _planner_prompts(state: AgentState):
    system_prompt = (
        "You are the Planner agent in a multi-agent pipeline that tags and "
        "summarizes Municipal Transit Incident records (bus/subway/light "
        "rail/streetcar/commuter rail/ferry disruptions). Given a title and "
        "content describing one incident, propose 5 to 7 candidate topical "
        "tags (short lowercase phrases) grounded in specific details from "
        "the content -- e.g. the incident type, transit mode, route/line, "
        "location, or severity if mentioned -- and a rough draft summary "
        "(1-3 sentences, will be trimmed later). Do not invent details that "
        "aren't in the title/content. "
        "Respond ONLY with JSON in this exact shape: "
        '{"candidate_tags": ["...", "...", ...], "draft_summary": "..."}'
    )
    user_prompt = f"Title: {state['title']}\nContent: {state['content']}"

    feedback = state.get("reviewer_feedback") or {}
    if feedback.get("valid") is False and feedback.get("error"):
        user_prompt += (
            f"\n\nYour previous draft was rejected. Validation error: "
            f"{feedback['error']}\nProduce a corrected draft that fixes this "
            f"exactly (tags must be {TAG_MIN_CHARS}-{TAG_MAX_CHARS} characters "
            f"each, and there must be room to trim the summary to "
            f"{MAX_SUMMARY_WORDS} words or fewer)."
        )
    return system_prompt, user_prompt


def _reviewer_prompts(state: AgentState):
    system_prompt = (
        "You are the Reviewer agent in a multi-agent pipeline for Municipal "
        f"Transit Incident records. You will receive a title, content, and "
        f"a Planner's draft (candidate tags + draft summary). Select "
        f"exactly {NUM_TAGS} of the most topical tags from the candidates "
        f"(each must be {TAG_MIN_CHARS}-{TAG_MAX_CHARS} characters), "
        "keeping only ones clearly grounded in the content. Rewrite the "
        f"summary to be at most {MAX_SUMMARY_WORDS} words, factual and "
        "specific -- do not add information that isn't in the title/content. "
        "Respond ONLY with JSON in this exact shape: "
        '{"tags": ["...", "...", "..."], "summary": "..."}'
    )
    proposal = state.get("planner_proposal") or {}
    user_prompt = (
        f"Title: {state['title']}\nContent: {state['content']}\n\n"
        f"Planner draft: {json.dumps(proposal)}"
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 3: Agent nodes
# ---------------------------------------------------------------------------
def planner_node(state: AgentState) -> Dict[str, Any]:
    print("---NODE: Planner ---", file=sys.stderr)
    system_prompt, user_prompt = _planner_prompts(state)
    out = call_model(state, system_prompt, user_prompt)
    proposal = {
        "candidate_tags": out.get("candidate_tags", []),
        "draft_summary": out.get("draft_summary", ""),
    }
    # Clear any prior rejection now that a fresh proposal exists.
    return {"planner_proposal": proposal, "reviewer_feedback": {}}


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    print("---NODE: Reviewer ---", file=sys.stderr)
    system_prompt, user_prompt = _reviewer_prompts(state)
    out = call_model(state, system_prompt, user_prompt)
    tags = out.get("tags", [])
    summary = out.get("summary", "")

    try:
        validated = ReviewedOutput(tags=tags, summary=summary)
        return {
            "reviewer_feedback": {
                "valid": True,
                "tags": validated.tags,
                "summary": validated.summary,
            }
        }
    except ValidationError as exc:
        if not state.get("strict", True):
            # Lenient mode: try a cheap local repair before giving up on it.
            fixed_tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
            fixed_tags = (fixed_tags + ["general incident", "transit delay", "service issue"])[:NUM_TAGS]
            fixed_tags = [t[:TAG_MAX_CHARS] for t in fixed_tags]
            words = (summary or "").split()
            fixed_summary = " ".join(words[:MAX_SUMMARY_WORDS]) or "Incident summary unavailable."
            try:
                validated = ReviewedOutput(tags=fixed_tags, summary=fixed_summary)
                return {
                    "reviewer_feedback": {
                        "valid": True,
                        "tags": validated.tags,
                        "summary": validated.summary,
                        "auto_repaired": True,
                    }
                }
            except ValidationError:
                pass  # fall through to reporting the original failure

        return {"reviewer_feedback": {"valid": False, "error": str(exc)}}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """State-updating half of the Supervisor: just advances the turn
    counter. All branching decisions live in router_logic below."""
    turn_count = state.get("turn_count", 0) + 1
    print(f"---NODE: Supervisor (turn {turn_count}) ---", file=sys.stderr)
    return {"turn_count": turn_count}


# ---------------------------------------------------------------------------
# Step 4: Routing function -- reads state, returns "planner", "reviewer", or END
# ---------------------------------------------------------------------------
def router_logic(state: AgentState) -> str:
    turn_count = state.get("turn_count", 0)
    ceiling = state.get("turn_ceiling", DEFAULT_TURN_CEILING)

    if turn_count >= ceiling:
        print(f"  [Router] turn ceiling ({ceiling}) reached -> END", file=sys.stderr)
        return "end"

    proposal = state.get("planner_proposal")
    if not proposal:
        print("  [Router] no proposal yet -> planner", file=sys.stderr)
        return "planner"

    feedback = state.get("reviewer_feedback")
    if not feedback:
        print("  [Router] proposal exists, unreviewed -> reviewer", file=sys.stderr)
        return "reviewer"

    if feedback.get("valid"):
        print("  [Router] proposal valid -> END", file=sys.stderr)
        return "end"

    print("  [Router] proposal invalid -> planner (retry)", file=sys.stderr)
    return "planner"


# ---------------------------------------------------------------------------
# Step 5: Assembling the graph
# ---------------------------------------------------------------------------
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("reviewer", reviewer_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", "end": END},
    )
    graph.add_edge("planner", "supervisor")
    graph.add_edge("reviewer", "supervisor")

    return graph.compile()


# ---------------------------------------------------------------------------
# Step 6: Running and testing
# ---------------------------------------------------------------------------
def build_initial_state(
    title: str,
    content: str,
    email: str = "",
    strict: bool = True,
    task: str = DEFAULT_TASK,
    llm: Optional[Any] = None,
    turn_ceiling: int = DEFAULT_TURN_CEILING,
) -> AgentState:
    return {
        "title": title,
        "content": content,
        "email": email,
        "strict": strict,
        "task": task,
        "llm": llm,
        "planner_proposal": {},
        "reviewer_feedback": {},
        "turn_count": 0,
        "turn_ceiling": turn_ceiling,
    }


def run_pipeline(
    title: str,
    content: str,
    email: str = "",
    strict: bool = True,
    task: str = DEFAULT_TASK,
    llm: Optional[Any] = None,
    turn_ceiling: int = DEFAULT_TURN_CEILING,
    stream: bool = True,
) -> dict:
    app = build_graph()
    initial_state = build_initial_state(
        title, content, email=email, strict=strict, task=task,
        llm=llm, turn_ceiling=turn_ceiling,
    )

    final_state = dict(initial_state)
    if stream:
        for step in app.stream(initial_state):
            for node_name, update in step.items():
                print(f"[stream] node={node_name} update={json.dumps(update, default=str)}", file=sys.stderr)
                final_state.update(update)
    else:
        final_state = app.invoke(initial_state)

    feedback = final_state.get("reviewer_feedback") or {}
    if feedback.get("valid"):
        return {"tags": feedback["tags"], "summary": feedback["summary"], "abandoned": False}

    return {
        "tags": feedback.get("tags", []),
        "summary": feedback.get("summary", ""),
        "abandoned": True,
        "error": feedback.get("error", "turn ceiling reached before a valid result"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Supervisor/Planner/Reviewer transit-incident tagging graph."
    )
    parser.add_argument("--turn-ceiling", type=int, default=DEFAULT_TURN_CEILING)
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    parser.add_argument("--llm", type=str, default=None, help="Optional model override, e.g. qwen3:8b")
    args = parser.parse_args()

    sample_title = "Route 22 -- Mechanical Breakdown"
    sample_content = (
        "incident_type=Mechanical Breakdown; transit_mode=Bus; "
        "route_or_line=Route 22; location=Downtown Transit Center; "
        "severity=Moderate; delay_minutes=20; description=A Route 22 bus "
        "experienced a mechanical breakdown near the Downtown Transit "
        "Center during evening rush hour. The engine stalled at a signal "
        "and could not restart, blocking one lane of traffic. Riders were "
        "transferred to the following bus after a 20-minute delay. A "
        "maintenance crew towed the disabled vehicle off-route roughly 45 "
        "minutes after the initial report."
    )

    result = run_pipeline(
        sample_title, sample_content,
        strict=args.strict, llm=args.llm, turn_ceiling=args.turn_ceiling,
    )
    print(json.dumps(result))
