"""HW8 Part 2/3 topic names and shared settings (PREFIX s1066)."""

from kafka_service.config import BOOTSTRAP, PREFIX, SEED, VERIFY_SEED  # noqa: F401

INBOX = f"{PREFIX}_inbox"
TASKS = f"{PREFIX}_tasks"          # 2 partitions (Part 3 ordering test)
DRAFTS = f"{PREFIX}_drafts"
FINAL = f"{PREFIX}_final"
DEAD_LETTER = f"{PREFIX}_dead_letter"
PARTITIONS = {INBOX: 1, TASKS: 2, DRAFTS: 1, FINAL: 1, DEAD_LETTER: 1}
