import os
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, relationship

from database import PORT_BASE, init_mongo
from routers import auth, documents, memory  # HW7: JWT auth; HW6: Mongo document API + chat memory
from security import get_current_user, require_roles
from sql_db import (  # noqa: F401  (re-exported for seed.py)
    DATABASE_URL,
    Base,
    Role,
    SessionLocal,
    UserModel,
    engine,
    get_db,
)

# ------------------------------------------------------------------------------
# 1. Database Models
#    Engine, get_db() and the HW7 `users` table now live in sql_db.py.
#    The HW4 cookie-session tables/endpoints were removed (history: git tag hw4).
# ------------------------------------------------------------------------------

# HW7 permission policy for the graded domain routes
ANY_ROLE = get_current_user                                      # list / read
CAN_WRITE = require_roles(Role.writer, Role.moderator)           # create / update
CAN_DELETE = require_roles(Role.moderator)                       # delete

# --- HW5 Secondary Entity Table ---
class CongestionIndexModel(Base):
    __tablename__ = "Congestion_indexes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    level_name = Column(String(100), nullable=False)          # Primary text field
    description = Column(Text, nullable=True)                 # Secondary text field
    index_code = Column(String(20), unique=True, nullable=False, index=True) # Unique field
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    incidents = relationship("IncidentModel", back_populates="congestion_index")

# --- HW5 Updated Primary Entity Table ---
class IncidentModel(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)               # Primary text field
    incident_code = Column(String(50), unique=True, nullable=False, index=True) # Unique field
    delay_minutes = Column(Integer, nullable=False, default=0) # Numeric field with default
    congestion_index_id = Column(Integer, ForeignKey("Congestion_indexes.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    congestion_index = relationship("CongestionIndexModel", back_populates="incidents")
    logs = relationship("IncidentLogModel", back_populates="incident", lazy="select")

class IncidentLogModel(Base):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    notes = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    incident = relationship("IncidentModel", back_populates="logs")

Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# 3. Pydantic Schemas with Format Validation
# ------------------------------------------------------------------------------
# Congestion Index Schemas
class CongestionIndexCreate(BaseModel):
    level_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    index_code: str = Field(..., pattern=r"^CONG-[A-Z0-9]+-[0-9]+$")

class CongestionIndexUpdate(BaseModel):
    level_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    index_code: Optional[str] = Field(None, pattern=r"^CONG-[A-Z0-9]+-[0-9]+$")

class CongestionIndexResponse(BaseModel):
    id: int
    level_name: str
    description: Optional[str] = None
    index_code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Incident Schemas
class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    incident_code: str = Field(..., pattern=r"^INC-\d{4}-\d{3,}$")
    delay_minutes: int = Field(0, ge=0)
    congestion_index_id: int

class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    incident_code: Optional[str] = Field(None, pattern=r"^INC-\d{4}-\d{3,}$")
    delay_minutes: Optional[int] = Field(None, ge=0)
    congestion_index_id: Optional[int] = None

class IncidentResponse(BaseModel):
    id: int
    title: str
    incident_code: str
    delay_minutes: int
    congestion_index_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Log Schemas
class LogResponse(BaseModel):
    id: int
    notes: str
    class Config:
        from_attributes = True

class IncidentWithLogsResponse(BaseModel):
    id: int
    title: str
    incident_code: str
    logs: List[LogResponse]
    class Config:
        from_attributes = True

# ------------------------------------------------------------------------------
# 4. FastAPI Setup
# ------------------------------------------------------------------------------
app = FastAPI(title="Municipal Transit Incident Manager")

# HW6: CORS middleware (FastAPI parses JSON request bodies into the Pydantic models)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return clear, field-level validation messages with HTTP 422."""
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})


@app.on_event("startup")
def _startup_mongo():
    init_mongo()


app.mount("/static", StaticFiles(directory="static"), name="static")
# HW6 routers (must be registered before the catch-all frontend route)
app.include_router(auth.router)  # HW7: POST /auth/login, GET /auth/me
app.include_router(documents.router)
app.include_router(memory.router)

# ------------------------------------------------------------------------------
# 7. Secondary Entity CRUD Endpoints (Congestion Indexes)
# ------------------------------------------------------------------------------
@app.post("/congestion-indexes", response_model=CongestionIndexResponse, status_code=status.HTTP_201_CREATED)
def create_congestion_index(
    data: CongestionIndexCreate,
    current_user: UserModel = Depends(CAN_WRITE),
    db: Session = Depends(get_db)
):
    try:
        index_obj = CongestionIndexModel(**data.model_dump())
        db.add(index_obj)
        db.commit()
        db.refresh(index_obj)
        return index_obj
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Index code '{data.index_code}' already exists.") from exc

@app.get("/congestion-indexes", response_model=List[CongestionIndexResponse])
def get_all_congestion_indexes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: UserModel = Depends(ANY_ROLE),
    db: Session = Depends(get_db)
):
    return db.query(CongestionIndexModel).offset(skip).limit(limit).all()

@app.get("/congestion-indexes/{index_id}", response_model=CongestionIndexResponse)
def get_congestion_index(
    index_id: int,
    current_user: UserModel = Depends(ANY_ROLE),
    db: Session = Depends(get_db)
):
    obj = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == index_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Congestion index not found")
    return obj

@app.put("/congestion-indexes/{index_id}", response_model=CongestionIndexResponse)
def update_congestion_index(
    index_id: int,
    data: CongestionIndexUpdate,
    current_user: UserModel = Depends(CAN_WRITE),
    db: Session = Depends(get_db)
):
    obj = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == index_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Congestion index not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)

    try:
        db.commit()
        db.refresh(obj)
        return obj
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Index code conflict.") from exc

@app.delete("/congestion-indexes/{index_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_congestion_index(
    index_id: int,
    current_user: UserModel = Depends(CAN_DELETE),
    db: Session = Depends(get_db)
):
    obj = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == index_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Congestion index not found")

    try:
        db.delete(obj)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete congestion index with existing associated transit incidents."
        ) from exc
# ------------------------------------------------------------------------------
# 8. Primary Entity CRUD Endpoints (Transit Incidents)
# ------------------------------------------------------------------------------
@app.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    data: IncidentCreate,
    current_user: UserModel = Depends(CAN_WRITE),
    db: Session = Depends(get_db)
):
    related = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == data.congestion_index_id).first()
    if not related:
        raise HTTPException(status_code=400, detail=f"Congestion index ID {data.congestion_index_id} does not exist.")

    try:
        incident = IncidentModel(**data.model_dump())
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return incident
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Incident code '{data.incident_code}' already exists.") from exc

@app.get("/incidents", response_model=List[IncidentResponse])
def get_all_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),  # Increased max limit to 1000 & default to 50
    current_user: UserModel = Depends(ANY_ROLE),
    db: Session = Depends(get_db)
):
    # Sorts by newest created incidents first
    return db.query(IncidentModel).order_by(IncidentModel.id.desc()).offset(skip).limit(limit).all()

@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident_by_id(
    incident_id: int,
    current_user: UserModel = Depends(ANY_ROLE),
    db: Session = Depends(get_db)
):
    incident = db.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")
    return incident

@app.put("/incidents/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    current_user: UserModel = Depends(CAN_WRITE),
    db: Session = Depends(get_db)
):
    incident = db.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")

    if data.congestion_index_id is not None:
        related = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == data.congestion_index_id).first()
        if not related:
            raise HTTPException(status_code=400, detail="Target congestion index ID does not exist.")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(incident, key, value)

    try:
        db.commit()
        db.refresh(incident)
        return incident
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Incident code conflict.") from exc

@app.delete("/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(
    incident_id: int,
    current_user: UserModel = Depends(CAN_DELETE),
    db: Session = Depends(get_db)
):
    incident = db.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")

    db.delete(incident)
    db.commit()

# ------------------------------------------------------------------------------
# 9. Relationship Query Endpoint
# ------------------------------------------------------------------------------
@app.get("/congestion-indexes/{index_id}/incidents", response_model=List[IncidentResponse])
def get_incidents_by_congestion_index(
    index_id: int,
    current_user: UserModel = Depends(ANY_ROLE),
    db: Session = Depends(get_db)
):
    parent = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == index_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Congestion index not found")

    return db.query(IncidentModel).filter(IncidentModel.congestion_index_id == index_id).all()

# ------------------------------------------------------------------------------
# 10. Frontend Catch-All Route
# ------------------------------------------------------------------------------
@app.get("/{full_path:path}")
def serve_react_app(full_path: str):
    return FileResponse("templates/index.html")

if __name__ == "__main__":
    import uvicorn

    # Pass the app object (not "main:app") so this module is imported only once; a second import would
    # re-declare the SQLAlchemy tables on the shared sql_db.Base. For auto-reload use:
    #   uvicorn main:app --reload --port 8166
    uvicorn.run(app, host="0.0.0.0", port=PORT_BASE)  # 8166
