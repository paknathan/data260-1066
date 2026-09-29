# routers/auth.py
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
import time

router = APIRouter()

# Hardcoded credentials for testing (Replace with MySQL queries in Part 2)
VALID_EMAIL = "admin@transit.org"
VALID_PASSWORD = "password"
IDLE_TIMEOUT = 3600

@router.post("/login")
async def login(request: Request):
    """
    Receives JSON body from Login.jsx with email and password.
    Sets server-side session cookie upon success.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    email = data.get("email")
    password = data.get("password")

    if email == VALID_EMAIL and password == VALID_PASSWORD:
        request.session["user"] = email
        request.session["last_activity"] = time.time()
        return JSONResponse(content={"message": "Logged in successfully", "email": email})

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password."
    )

@router.get("/me")
async def get_current_user(request: Request):
    """
    Checks active HTTP-only session cookie when App.jsx loads.
    """
    user = request.session.get("user")
    last_activity = request.session.get("last_activity")

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    if last_activity and time.time() - last_activity > IDLE_TIMEOUT:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    request.session["last_activity"] = time.time()
    return {"email": user}

@router.post("/logout")
@router.get("/logout")
async def logout(request: Request):
    """
    Clears session cookie.
    """
    request.session.clear()
    return {"message": "Logged out successfully"}