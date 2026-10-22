"""HW7 Part 1 - JWT login and identity endpoints (replaces the HW4 session flow, kept at tag hw4)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, get_current_user, verify_password
from sql_db import Role, UserModel, get_db

router = APIRouter(prefix="/auth", tags=["Auth (JWT)"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Role


class MeResponse(BaseModel):
    id: int
    username: str
    role: Role


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Look the user up in MySQL, verify the bcrypt hash, and only then issue a JWT."""
    user = db.query(UserModel).filter(UserModel.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
    )


@router.get("/me", response_model=MeResponse)
def me(user: UserModel = Depends(get_current_user)) -> MeResponse:
    """Return the identity and role encoded by the caller's valid token."""
    return MeResponse(id=user.id, username=user.username, role=user.role)
