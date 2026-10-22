"""HW7 Part 1 - bring the MySQL `users` table to (id, username UNIQUE, password_hash, role) and seed 3 demo users.

Non-destructive: the HW4 table had (id, name, email, password_hash). We ADD `username` + `role`,
backfill username from email for old rows (role=reader), and relax the old NOT NULL name/email
columns so new users don't need them. Safe to run repeatedly.

Usage (from code/):
    export DATABASE_URL=mysql+pymysql://...   JWT_SECRET=...   DEMO_PASSWORD=...
    python scripts/migrate_users_hw07.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make code/ importable

from sqlalchemy import inspect, text  # noqa: E402

from security import hash_password  # noqa: E402
from sql_db import Base, Role, SessionLocal, UserModel, engine  # noqa: E402

SID4 = 1066
DEMO_USERS = [
    (f"reader_{SID4}", Role.reader),
    (f"writer_{SID4}", Role.writer),
    (f"moderator_{SID4}", Role.moderator),
]


def migrate_schema() -> list[str]:
    """Create or alter `users` so it matches the HW7 schema; return the statements that ran."""
    ran: list[str] = []
    insp = inspect(engine)
    if not insp.has_table("users"):
        Base.metadata.create_all(bind=engine, tables=[UserModel.__table__])
        return ["CREATE TABLE users (via SQLAlchemy)"]

    cols = {c["name"]: c for c in insp.get_columns("users")}
    stmts: list[str] = []
    if "username" not in cols:
        stmts += [
            "ALTER TABLE users ADD COLUMN username VARCHAR(120) NULL AFTER id",
            "UPDATE users SET username = email WHERE username IS NULL" if "email" in cols
            else "UPDATE users SET username = CONCAT('user_', id) WHERE username IS NULL",
            "ALTER TABLE users MODIFY username VARCHAR(120) NOT NULL",
            "ALTER TABLE users ADD UNIQUE INDEX uq_users_username (username)",
        ]
    if "role" not in cols:
        stmts.append(
            "ALTER TABLE users ADD COLUMN role ENUM('reader','writer','moderator') NOT NULL DEFAULT 'reader'"
        )
    # Legacy HW4 columns: keep the data, but stop requiring them.
    if "name" in cols and not cols["name"]["nullable"]:
        stmts.append("ALTER TABLE users MODIFY name VARCHAR(100) NULL")
    if "email" in cols and not cols["email"]["nullable"]:
        stmts.append("ALTER TABLE users MODIFY email VARCHAR(120) NULL")

    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))
            ran.append(sql)
    return ran


def seed_demo_users(password: str) -> list[tuple[str, str, str]]:
    """Upsert one user per role with a bcrypt-hashed password; return (username, role, action)."""
    results = []
    db = SessionLocal()
    try:
        for username, role in DEMO_USERS:
            user = db.query(UserModel).filter(UserModel.username == username).first()
            if user is None:
                db.add(UserModel(username=username, password_hash=hash_password(password), role=role))
                results.append((username, role.value, "created"))
            else:
                user.password_hash = hash_password(password)
                user.role = role
                results.append((username, role.value, "updated"))
        db.commit()
    finally:
        db.close()
    return results


def main() -> None:
    """Run the migration, seed users, and print the resulting table (no plaintext passwords)."""
    password = os.getenv("DEMO_PASSWORD")
    if not password:
        sys.exit("Set DEMO_PASSWORD first (the password all three demo users will share).")

    for sql in migrate_schema() or ["(schema already up to date)"]:
        print("migrate:", sql)
    for username, role, action in seed_demo_users(password):
        print(f"seed:    {action:7s} {username:16s} role={role}")

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, username, role, LEFT(password_hash, 7) AS hash_prefix FROM users ORDER BY id"))
        print("\nid | username | role | password_hash prefix")
        for r in rows:
            print(f"{r.id} | {r.username} | {r.role} | {r.hash_prefix}...")


if __name__ == "__main__":
    main()
