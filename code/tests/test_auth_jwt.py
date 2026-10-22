"""HW7 Part 1 - JWT auth + role checks, run against a throwaway SQLite DB (no MySQL/Mongo needed)."""

import os
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "auth_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789")

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import auth  # noqa: E402
from security import create_access_token, get_current_user, hash_password, require_roles, verify_password  # noqa: E402
from sql_db import Base, Role, SessionLocal, UserModel, engine  # noqa: E402

PW = "pw-1066"

app = FastAPI()
app.include_router(auth.router)


@app.get("/things")
def list_things(_: UserModel = Depends(get_current_user)) -> list:
    return []


@app.post("/things", status_code=201)
def create_thing(_: UserModel = Depends(require_roles(Role.writer, Role.moderator))) -> dict:
    return {"ok": True}


@app.delete("/things/1", status_code=204)
def delete_thing(_: UserModel = Depends(require_roles(Role.moderator))) -> None:
    return None


@pytest.fixture(scope="module")
def client() -> TestClient:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    for name, role in [("r", Role.reader), ("w", Role.writer), ("m", Role.moderator)]:
        db.add(UserModel(username=name, password_hash=hash_password(PW), role=role))
    db.commit()
    db.close()
    return TestClient(app)


def _hdr(client: TestClient, user: str) -> dict:
    tok = client.post("/auth/login", json={"username": user, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_hash_is_not_plaintext_and_verifies() -> None:
    h = hash_password("secret")
    assert h != "secret" and h.startswith("$2")
    assert verify_password("secret", h) and not verify_password("wrong", h)
    assert verify_password("x", "not-a-bcrypt-hash") is False  # invalid input


def test_login_ok_and_bad(client: TestClient) -> None:
    ok = client.post("/auth/login", json={"username": "r", "password": PW})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    assert client.post("/auth/login", json={"username": "r", "password": "nope"}).status_code == 401
    assert client.post("/auth/login", json={"username": "ghost", "password": PW}).status_code == 401


def test_me(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    body = client.get("/auth/me", headers=_hdr(client, "w")).json()
    assert body["username"] == "w" and body["role"] == "writer"


def test_expired_token_is_401(client: TestClient) -> None:
    db = SessionLocal()
    user = db.query(UserModel).filter_by(username="m").one()
    expired = create_access_token(user, expires_minutes=-1)
    db.close()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()


@pytest.mark.parametrize(
    "user,method,expected",
    [
        ("r", "get", 200), ("r", "post", 403), ("w", "post", 201),
        ("w", "delete", 403), ("m", "delete", 204), ("m", "post", 201),
    ],
)
def test_role_matrix(client: TestClient, user: str, method: str, expected: int) -> None:
    url = "/things/1" if method == "delete" else "/things"
    assert getattr(client, method)(url, headers=_hdr(client, user)).status_code == expected
