"""HW7 Part 1 - password hashing, JWT access tokens and role-based FastAPI dependencies."""

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from sql_db import Role, UserModel, get_db

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is not set. Run `export JWT_SECRET=$(openssl rand -hex 32)`.")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# auto_error=False so a missing header gives OUR 401 (not FastAPI's default 403).
bearer_scheme = HTTPBearer(auto_error=False)
__all__ = ["hash_password", "verify_password", "create_access_token", "decode_access_token", "get_current_user", "require_roles"]


# ---------------------------------------------------------------- passwords
def hash_password(plain: str) -> str:
    """Return a salted bcrypt hash of `plain`."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """Check `plain` against a stored bcrypt hash; False on any mismatch or bad hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------- tokens
def create_access_token(user: UserModel, expires_minutes: int | None = None) -> str:
    """Sign a JWT carrying the username (sub), user id and role."""
    now = datetime.now(timezone.utc)
    minutes = ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else expires_minutes
    payload = {
        "sub": user.username,
        "uid": user.id,
        "role": Role(user.role).value,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    """Build a 401 with the standard Bearer challenge header."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry and return the claims, or raise 401."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc


# ---------------------------------------------------------------- dependencies
def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    """Resolve `Authorization: Bearer <jwt>` to a live user row, else 401."""
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise _unauthorized("Not authenticated")
    claims = decode_access_token(creds.credentials)
    user = db.query(UserModel).filter(UserModel.username == claims["sub"]).first()
    if user is None:  # user deleted after the token was issued
        raise _unauthorized("User no longer exists")
    return user


def require_roles(*allowed: Role) -> Callable[..., UserModel]:
    """Dependency factory: 401 if unauthenticated, 403 if the user's role is not in `allowed`."""
    allowed_values = {Role(r).value for r in allowed}

    def _checker(user: UserModel = Depends(get_current_user)) -> UserModel:
        if Role(user.role).value not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{Role(user.role).value}' may not perform this action; requires one of {sorted(allowed_values)}",
            )
        return user

    return _checker
