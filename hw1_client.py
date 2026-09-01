import atexit
import json
import sys
from src.model_client import complete

# Conversation and metric state
messages = [
    {"role": "system", "content": "You are a helpful assistant."}
]
cumulative_input_tokens = 0
cumulative_output_tokens = 0
turn_count = 0


def print_summary_on_exit():
    """Triggered on script exit to display total conversation usage stats."""
    if turn_count > 0:
        total_cumulative = cumulative_input_tokens + cumulative_output_tokens
        print("\n" + "=" * 50)
        print("CUMULATIVE SESSION STATS")
        print("=" * 50)
        print(f"Total Turns: {turn_count}")
        print(f"Cumulative Input Tokens:  {cumulative_input_tokens}")
        print(f"Cumulative Output Tokens: {cumulative_output_tokens}")
        print(f"Cumulative Total Tokens:  {total_cumulative}")
        print("=" * 50)


# Register exit hook
atexit.register(print_summary_on_exit)


def print_current_stats():
    """Prints live stats including serialized conversation history length."""
    serialized_history = json.dumps(messages)
    history_char_length = len(serialized_history)
    total_tokens = cumulative_input_tokens + cumulative_output_tokens

    print("\n" + "-" * 40)
    print("LIVE STATS REPORT")
    print("-" * 40)
    print(f"Turn Count:                  {turn_count}")
    print(f"Cumulative Input Tokens:     {cumulative_input_tokens}")
    print(f"Cumulative Output Tokens:    {cumulative_output_tokens}")
    print(f"Cumulative Total Tokens:     {total_tokens}")
    print(f"Serialized History Length:   {history_char_length} characters")
    print(f"Message Stack Count:         {len(messages)} messages")
    print("-" * 40 + "\n")


def main():
    global cumulative_input_tokens, cumulative_output_tokens, turn_count, messages

    print("Interactive Chat Loop (Commands: '/stats', 'exit', 'quit')\n")

    while True:
        try:
            user_input = input("User > ").strip()
            if not user_input:
                continue

            # Command: Exit
            if user_input.lower() in ("exit", "quit"):
                break

            # Command: /stats
            if user_input.lower() == "/stats":
                print_current_stats()
                continue

            # Append user turn to ongoing conversation history
            messages.append({"role": "user", "content": user_input})
            turn_count += 1

            # Request text completion passing full conversation history
            response = complete(messages=messages, response_format=None)

            content = response.get("content", "")
            usage = response.get("_usage", {})

            # Append assistant response to history
            messages.append({"role": "assistant", "content": content})

            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            tot_tok = usage.get("total_tokens", 0)

            # Accumulate token metrics
            cumulative_input_tokens += in_tok
            cumulative_output_tokens += out_tok

            print(f"\nAssistant > {content}\n")
            print(
                f"[Turn {turn_count} Usage] Input Tokens: {in_tok} | "
                f"Output Tokens: {out_tok} | Total Tokens: {tot_tok}\n"
            )

        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()