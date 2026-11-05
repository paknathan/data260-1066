"""HW9 Part 1 - Redis-backed access/view counter for transit incidents.

Redis holds the live count (fast INCR on every access); every SYNC_EVERY
increments the current count is written to incidents.view_count in MySQL.
"""
import logging
import os

import redis
from sqlalchemy import text

from database import PREFIX  # s1066

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SYNC_EVERY = 10

logger = logging.getLogger(__name__)


class IncidentCache:
    """Redis cache layer in front of the SQL `incidents` table."""

    def __init__(self, session_factory, redis_client=None):
        # session_factory: a SQLAlchemy sessionmaker (e.g. sql_db.SessionLocal)
        self.SessionLocal = session_factory
        self.redis_client = redis_client or redis.Redis.from_url(REDIS_URL, decode_responses=True)

    def increment_incident_views(self, incident_id: int) -> int:
        """Count one access to an incident; persist to the DB every 10 views. Returns the current count."""
        key = f"{PREFIX}:views:incident:{incident_id}"  # e.g. s1066:views:incident:42
        count = self.redis_client.incr(key)  # atomic, creates the key at 1 if missing

        if count % SYNC_EVERY == 0:
            with self.SessionLocal() as db:
                db.execute(
                    text("UPDATE incidents SET view_count = :count WHERE id = :id"),
                    {"count": count, "id": incident_id},
                )
                db.commit()
            logger.info("✓ Synced views to database")

        return count
