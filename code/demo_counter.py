"""HW9 Part 1 demo: access one transit incident 25 times and show the Redis counter.

Needs Redis (REDIS_URL, default redis://localhost:6379/0) and MySQL (DATABASE_URL).
    docker run -d --name redis-1066 -p 6379:6379 redis:7
    python demo_counter.py                 # uses the first incident in the table
    python demo_counter.py --incident-id 3
"""
import argparse
import logging

from sqlalchemy import inspect, text

from cache import IncidentCache
from database import PREFIX
from sql_db import SessionLocal, engine


def ensure_view_count_column() -> None:
    """One-time migration: add incidents.view_count if the table predates HW9."""
    cols = {c["name"] for c in inspect(engine).get_columns("incidents")}
    if "view_count" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE incidents ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident-id", type=int, default=None)
    parser.add_argument("--accesses", type=int, default=25)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_view_count_column()

    with SessionLocal() as db:
        incident_id = args.incident_id or db.execute(text("SELECT MIN(id) FROM incidents")).scalar()
    if incident_id is None:
        raise SystemExit("No incidents in the database - run seed.py first.")

    cache = IncidentCache(SessionLocal)
    cache.redis_client.delete(f"{PREFIX}:views:incident:{incident_id}")  # start the demo from 0

    print("=== Testing Counter ===\n")
    for i in range(1, args.accesses + 1):
        total = cache.increment_incident_views(incident_id)
        print(f"Access #{i}: Total = {total}")

    with SessionLocal() as db:
        stored = db.execute(text("SELECT view_count FROM incidents WHERE id = :id"), {"id": incident_id}).scalar()
    print(f"\nincidents.view_count for id={incident_id} in MySQL: {stored}")


if __name__ == "__main__":
    main()
