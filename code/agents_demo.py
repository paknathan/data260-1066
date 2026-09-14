import argparse
import json
import sys
import requests
from src.model_client import complete

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"
MAX_SUMMARY_WORDS = 25
NUM_TAGS = 3
MAX_RETRIES = 3


def call_model(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict:
    """Delegates execution directly to the central model-adapter."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return complete(messages=messages, temperature=temperature, response_format="json")


def planner_step(title: str, content: str, temperature: float = 0.0) -> dict:

    system_prompt = (
        "You are the Planner agent in a small multi-agent pipeline. "
        "Given a title and content describing some record or event, "
        "propose 5 to 7 candidate topical tags (short lowercase phrases) "
        "that are directly grounded in specific details from the given "
        "content, and a rough draft summary (1-3 sentences, will be "
        "trimmed later). Base every tag and the summary strictly on what "
        "the title/content actually say — do not invent topics that "
        "aren't supported by the text. "
        "Respond ONLY with JSON in this exact shape: "
        '{"candidate_tags": ["...", "...", ...], "draft_summary": "..."}'
    )
    user_prompt = f"Title: {title}\nContent: {content}"
    return call_model(system_prompt, user_prompt, temperature=temperature)


def reviewer_step(planner_output: dict, title: str, content: str, temperature: float = 0.0) -> dict:

    system_prompt = (
        "You are the Reviewer agent in a small multi-agent pipeline. You "
        "will receive a title, content, and a Planner's draft (candidate "
        f"tags + draft summary). Select exactly {NUM_TAGS} of the most "
        "topical tags from the candidates, keeping only ones clearly "
        "grounded in the content (you may lightly reword them, but "
        f"prefer the given candidates). Rewrite the summary to be at "
        f"most {MAX_SUMMARY_WORDS} words, factual and specific to the "
        "content — do not add information that isn't in the title/content. "
        "Respond ONLY with JSON in this exact shape: "
        '{"tags": ["...", "...", "..."], "summary": "..."}'
    )
    user_prompt = (
        f"Title: {title}\nContent: {content}\n\n"
        f"Planner draft: {json.dumps(planner_output)}"
    )
    return call_model(system_prompt, user_prompt, temperature=temperature)


def finalizer_step(reviewer_output: dict, title: str, content: str, temperature: float = 0.0) -> dict:

    tags = reviewer_output.get("tags", [])
    summary = reviewer_output.get("summary", "")

    if _is_valid(tags, summary):
        return {"tags": tags, "summary": summary}

    try:
        system_prompt = (
            "You are the Finalizer agent. The previous output violated the "
            f"required contract: exactly {NUM_TAGS} tags and a summary of at "
            f"most {MAX_SUMMARY_WORDS} words. Fix it using only the given "
            "title/content as grounding — do not introduce new topics. "
            "Respond ONLY with JSON in this exact shape: "
            '{"tags": ["...", "...", "..."], "summary": "..."}'
        )
        user_prompt = (
            f"Title: {title}\nContent: {content}\n\n"
            f"Invalid output to fix: {json.dumps(reviewer_output)}"
        )
        fixed = call_model(system_prompt, user_prompt, temperature=temperature)
        tags = fixed.get("tags", tags)
        summary = fixed.get("summary", summary)
    except RuntimeError as exc:
        print(f"  Finalizer corrective call failed, using local fallback: {exc}",
              file=sys.stderr)

    if _is_valid(tags, summary):
        return {"tags": tags, "summary": summary}

    tags = (tags + ["general"] * NUM_TAGS)[:NUM_TAGS]
    words = summary.split()
    if len(words) > MAX_SUMMARY_WORDS:
        summary = " ".join(words[:MAX_SUMMARY_WORDS])
    return {"tags": tags, "summary": summary}


def _is_valid(tags, summary) -> bool:
    return (
        isinstance(tags, list)
        and len(tags) == NUM_TAGS
        and all(isinstance(t, str) and t.strip() for t in tags)
        and isinstance(summary, str)
        and 0 < len(summary.split()) <= MAX_SUMMARY_WORDS
    )


def run_pipeline(title: str, content: str, temperature: float = 0.0) -> dict:
    print("Planner working...", file=sys.stderr)
    planner_output = planner_step(title, content, temperature=temperature)
    print(f"  Planner output: {json.dumps(planner_output)}", file=sys.stderr)

    print("Reviewer working...", file=sys.stderr)
    reviewer_output = reviewer_step(planner_output, title, content, temperature=temperature)
    print(f"  Reviewer output: {json.dumps(reviewer_output)}", file=sys.stderr)

    print("Finalizer working...", file=sys.stderr)
    final_output = finalizer_step(reviewer_output, title, content, temperature=temperature)
    return final_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the multi-agent transit incident pipeline.")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Temperature passed to the Ollama model calls.")
    args = parser.parse_args()

    # Example input matching the Municipal Transit Incident domain schema
    # (route_or_line as the primary field, description as the content field).
    sample_title = "Route 22 Bus Breakdown Near Downtown Transit Center"
    sample_content = (
        "A Route 22 bus experienced a mechanical breakdown near the "
        "Downtown Transit Center during evening rush hour. The engine "
        "stalled at a signal and could not restart, blocking one lane of "
        "traffic. Riders were transferred to the following bus after a "
        "20-minute delay. A maintenance crew towed the disabled vehicle "
        "off-route roughly 45 minutes after the initial report."
    )

    result = run_pipeline(sample_title, sample_content, temperature=args.temperature)
    print(json.dumps(result))
