import sys
import os
from src.model_client import complete

# Sample code with intentional issues to review
CODE_TO_REVIEW = """
def process_user_data(data):
    # Bug: SQL injection risk
    query = "SELECT * FROM users WHERE id = '" + data['id'] + "'"
    
    # Bug: Bare except
    try:
        result = execute_query(query)
        return result
    except:
        return None
"""

def verify_compliance(response_text: str) -> tuple[bool, list[str]]:
    """Checks whether the response strictly adheres to AGENT.md formatting rules."""
    lines = [line.strip() for line in response_text.strip().split("\n") if line.strip()]
    violations = []

    for idx, line in enumerate(lines, 1):
        # 1. Must start with a bullet character
        if not (line.startswith("* ") or line.startswith("- ")):
            violations.append(f"Line {idx} does not start with a bullet point: '{line[:40]}...'")
        
        # 2. Must not contain Markdown headers
        if line.startswith("#"):
            violations.append(f"Line {idx} uses Markdown header formatting: '{line[:20]}...'")

    is_compliant = len(violations) == 0
    return is_compliant, violations


def main():
    agent_md_path = "AGENT.md"
    if not os.path.exists(agent_md_path):
        print(f"Error: {agent_md_path} not found. Please create it first.")
        sys.exit(1)

    with open(agent_md_path, "r", encoding="utf-8") as f:
        agent_instructions = f.read()

    messages = [
        {"role": "system", "content": agent_instructions},
        {
            "role": "user",
            "content": f"Please review this code:\n\n```python\n{CODE_TO_REVIEW}\n```",
        },
    ]

    print("Sending code review request using AGENT.md system prompt...\n")
    
    # Request standard text format to verify natural model compliance
    result = complete(messages=messages, temperature=0.0, response_format=None)
    review_output = result.get("content", "")

    print("--- Model Output Start ---")
    print(review_output)
    print("--- Model Output End ---\n")

    # Verify formatting constraints
    is_compliant, violations = verify_compliance(review_output)

    print("=" * 50)
    print("VERIFICATION RESULT")
    print("=" * 50)
    if is_compliant:
        print(" SUCCESS: Model strictly followed the AGENT.md bullet-only protocol!")
    else:
        print(" FAILED: Model violated formatting rules:")
        for v in violations:
            print(f"  - {v}")
    print("=" * 50)


if __name__ == "__main__":
    main()