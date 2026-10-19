"""Run a file-memory command from the terminal: python scripts/memory_cli.py /compact"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import file_memory  # noqa: E402

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "/help"
    extractor = None
    if cmd == "/dream":
        import memory_core
        extractor = lambda t: memory_core.extract_episodes(t, memory_core.cfg()["extract_mode"])  # noqa: E731
    recent = []
    if cmd == "/dream" and len(sys.argv) > 2:  # optional session id -> read its recent messages from MongoDB
        import memory_core
        recent = memory_core.load_short_term(sys.argv[2], 20)
    result = file_memory.handle_command(cmd, recent, extractor)
    print(result["reply"])
    if "report" in result:
        print(json.dumps({k: result["report"][k] for k in ("lines_before", "lines_after", "facts_before",
                                                             "facts_after", "flagged_possibly_incorrect")}, indent=2))
