"""MySQL engine, session dependency and the HW7 `users` table (JWT + roles)."""

import enum
import os
from collections.abc import Iterator

from sqlalchemy import Column, Enum, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Run `export DATABASE_URL=...` first.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Role(str, enum.Enum):
    """The three HW7 roles, lowest to highest privilege."""

    reader = "reader"
    writer = "writer"
    moderator = "moderator"


class UserModel(Base):
    """users(id, username UNIQUE, password_hash, role) - only bcrypt hashes are stored."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        Enum(Role, values_callable=lambda e: [m.value for m in e], name="user_role"),
        nullable=False,
        default=Role.reader,
    )
