"""Part 4 - consolidation checks on the 55-line fixture."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import file_memory as fm  # noqa: E402
from make_memory_fixture import build  # noqa: E402


def test_fixture_is_55_lines_and_needs_consolidation():
    text = build()
    assert len(text.splitlines()) == 55
    due, reasons = fm.needs_consolidation(text, datetime(2026, 10, 19, tzinfo=timezone.utc))
    assert due and len(reasons) == 2


def test_consolidation_merges_resolves_and_flags():
    new, report = fm.consolidate(build())
    assert len(new.splitlines()) < 40
    assert len(report["duplicates_merged"]) >= 3
    assert len(report["contradictions_resolved"]) >= 3
    # superseded values are kept in the audit section, not silently deleted
    for c in report["contradictions_resolved"]:
        for s in c["superseded"]:
            assert s["value"] in new
    assert report["flagged_possibly_incorrect"] == ["auth.session_ttl"]
    assert not fm.needs_consolidation(new)[0]
