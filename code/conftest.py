"""Make code/ importable for tests, so both `pytest` and `python -m pytest` work from code/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
