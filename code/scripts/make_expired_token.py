"""Print a correctly-signed but already-expired JWT for the HW7 'expired token -> 401' screenshot.

Usage (from code/, same JWT_SECRET as the running server):
    python scripts/make_expired_token.py writer_1066
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security import create_access_token  # noqa: E402
from sql_db import SessionLocal, UserModel  # noqa: E402


def main() -> None:
    """Look up the user and mint a token whose exp is one minute in the past."""
    username = sys.argv[1] if len(sys.argv) > 1 else "reader_1066"
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user is None:
            sys.exit(f"No user named {username!r}; run scripts/migrate_users_hw07.py first.")
        print(create_access_token(user, expires_minutes=-1))
    finally:
        db.close()


if __name__ == "__main__":
    main()
