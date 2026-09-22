#main.py
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from routers.auth import router
import re
import uvicorn
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="Municipal Transit Incident API")

app.add_middleware(
    SessionMiddleware,
    secret_key="data260-session-secret",
    https_only=True,
    same_site="lax",
    max_age=3600)

app.include_router(router)

templates = Jinja2Templates(directory="templates")

incidents_db = [
    {
        "incident_id": "INC-00147",
        "route_or_line": "Route 22",
        "incident_type": "Mechanical Breakdown",
        "email": "operator@transit.org",
        "description": "Engine failure near 4th street stop."
    }
]

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, updated: str | None = None, q: str | None = None):
    search_query = (q or "").strip()

    if search_query:
        needle = search_query.lower()
        filtered_incidents = [
            incident for incident in incidents_db
            if needle in incident["route_or_line"].lower()
            or needle in incident["incident_type"].lower()
        ]
    else:
        filtered_incidents = incidents_db

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "incidents": filtered_incidents,
            "updated_id": updated,
            "search_query": search_query,
            "has_incidents": bool(incidents_db),
        }
    )

@app.post("/add")
def add_incident(
    incident_id: str = Form(...),
    route_or_line: str = Form(...),
    incident_type: str = Form(...),
    email: str = Form(...),
    description: str = Form(...)
):
    new_record = {
        "incident_id": incident_id,
        "route_or_line": route_or_line,
        "incident_type": incident_type,
        "email": email,
        "description": description
    }
    incidents_db.append(new_record)
    
    # 303 Redirect back to GET home view
    return RedirectResponse(url="/", status_code=303)

@app.post("/update/{incident_id}")
def update_incident(
    incident_id: str,
    route_or_line: str = Form(...),
    incident_type: str = Form(...)
):
    # Update the primary (route/line) and secondary (incident type) fields
    # for the matching record with whatever values were submitted.
    for incident in incidents_db:
        if incident["incident_id"] == incident_id:
            incident["route_or_line"] = route_or_line
            incident["incident_type"] = incident_type
            break

    # Redirect back to GET home view, flagging which record just changed
    return RedirectResponse(url=f"/?updated={incident_id}", status_code=303)

def _numeric_id(incident_id: str) -> int:
    """Extract the numeric portion of an incident_id like 'INC-00147' -> 147.
    Records with no digits at all sort lowest (treated as -1)."""
    digits = re.findall(r"\d+", incident_id)
    return int("".join(digits)) if digits else -1

@app.post("/delete-highest")
def delete_highest_incident():
    if incidents_db:
        highest = max(incidents_db, key=lambda incident: _numeric_id(incident["incident_id"]))
        incidents_db.remove(highest)

    # Redirect back to GET home view, which re-renders the (now shorter) list
    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8166, reload=True, ssl_keyfile="key.pem", ssl_certfile="cert.pem")