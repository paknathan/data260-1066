#auth.py
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
import time

# Create a router object
# This behaves like a mini FastAPI app
router = APIRouter()

# Configure Jinja2 templates directory
templates = Jinja2Templates(directory="templates")


# Hardcoded credentials for demo purposes only
# In real applications, credentials come from a database
VALID_USERNAME = "admin"
VALID_PASSWORD = "password"
IDLE_TIMEOUT = 60

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """
    Home page route.

    - Checks if a user is logged in using the session
    - Passes user info to the template
    """
    user = request.session.get("user")

    return templates.TemplateResponse(
        "index.html",
        {
            "message": "Welcome Home!",
            "request": request,  
            "user": user
        }
    )

@router.get("/login")
def login_page(request: Request):
    """
    Displays the login form.

    If the user is already logged in,
    the template can choose what to display.
    """
    user = request.session.get("user")
    error = request.session.pop("error", None)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "user": user,
            "error": error
        }
    )


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handles login form submission.

    - Reads username and password from the form
    - Validates credentials
    - Stores user info in session if valid
    """
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        # Store logged-in user in session
        request.session["user"] = username
        request.session["last_activity"] = time.time()

        # Redirect user to dashboard
        return RedirectResponse(
            url="/dashboard",
            status_code=HTTP_302_FOUND
        )

    # If credentials are invalid:
    # Redirect back to login page
    #
    # NOTE:
    # No error message is shown intentionally.
    # Students are expected to add Bootstrap alerts.
    request.session["error"] = "Invalid username or password."

    return RedirectResponse(
        url="/login",
        status_code=HTTP_302_FOUND
    )


@router.get("/dashboard")
def dashboard(request: Request):
    """
    Protected route.

    - Only accessible if user is logged in
    - Redirects to login page if session is missing
    """
    user = request.session.get("user")
    last_activity = request.session.get("last_activity")
    # If user is not logged in, block access
    if not user:
        return RedirectResponse(
            url="/login",
            status_code=HTTP_302_FOUND
        )

    # Session has expired due to inactivity
    if last_activity is None or time.time() - last_activity > IDLE_TIMEOUT:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=HTTP_302_FOUND
        )

    # User is still active, so update last activity time
    request.session["last_activity"] = time.time()

    # If user is logged in, render dashboard
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user
        }
    )


@router.get("/logout")
def logout(request: Request):
    """
    Logs the user out.

    - Clears all session data
    - Redirects back to home page
    """
    request.session.clear()

    return RedirectResponse(
        url="/",
        status_code=HTTP_302_FOUND
    )
