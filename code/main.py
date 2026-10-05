import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Response, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

# ------------------------------------------------------------------------------
# 1. Database Configuration & Models
# ------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Run `export DATABASE_URL=...` first.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Auth Models ---
class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")

class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("UserModel", back_populates="sessions")

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
# 2. Database Dependency
# ------------------------------------------------------------------------------
def get_db():
    db_session_basede26 = SessionLocal()
    try:
        yield db_session_basede26
    finally:
        db_session_basede26.close()

# ------------------------------------------------------------------------------
# 3. Pydantic Schemas with Format Validation
# ------------------------------------------------------------------------------
# Auth Schemas
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

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
app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------------------------------------------------------------------
# 5. Session Authentication Helper
# ------------------------------------------------------------------------------
def get_current_user(request: Request, db_session_basede26: Session = Depends(get_db)) -> UserModel:
    session_token = request.cookies.get("session_id")
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session_record = db_session_basede26.query(SessionModel).filter(
        SessionModel.id == session_token
    ).first()

    if not session_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    if datetime.utcnow() > session_record.expires_at:
        db_session_basede26.delete(session_record)
        db_session_basede26.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    return session_record.user

# ------------------------------------------------------------------------------
# 6. Auth Endpoints
# ------------------------------------------------------------------------------
@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db_session_basede26: Session = Depends(get_db)):
    existing_user = db_session_basede26.query(UserModel).filter(UserModel.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(user_data.password.encode('utf-8'), salt).decode('utf-8')

    new_user = UserModel(name=user_data.name, email=user_data.email, password_hash=hashed_pw)
    db_session_basede26.add(new_user)
    db_session_basede26.commit()
    return {"message": "User registered successfully"}

@app.post("/login")
def login(login_data: UserLogin, response: Response, db_session_basede26: Session = Depends(get_db)):
    user = db_session_basede26.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not bcrypt.checkpw(login_data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_token = str(uuid.uuid4())
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=8)

    session_record = SessionModel(
        id=session_token, user_id=user.id, created_at=created_at, expires_at=expires_at
    )
    db_session_basede26.add(session_record)
    db_session_basede26.commit()

    response.set_cookie(key="session_id", value=session_token, httponly=True, samesite="lax", secure=False)
    return {"email": user.email, "name": user.name}

@app.post("/logout")
def logout(request: Request, response: Response, db_session_basede26: Session = Depends(get_db)):
    session_token = request.cookies.get("session_id")
    if session_token:
        db_session_basede26.query(SessionModel).filter(SessionModel.id == session_token).delete()
        db_session_basede26.commit()

    response.delete_cookie("session_id")
    return {"message": "Logged out successfully"}

@app.get("/me")
def get_me(current_user: UserModel = Depends(get_current_user)):
    return {"email": current_user.email, "name": current_user.name}

# ------------------------------------------------------------------------------
# 7. Secondary Entity CRUD Endpoints (Congestion Indexes)
# ------------------------------------------------------------------------------
@app.post("/congestion-indexes", response_model=CongestionIndexResponse, status_code=status.HTTP_201_CREATED)
def create_congestion_index(
    data: CongestionIndexCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        index_obj = CongestionIndexModel(**data.model_dump())
        db.add(index_obj)
        db.commit()
        db.refresh(index_obj)
        return index_obj
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Index code '{data.index_code}' already exists.")

@app.get("/congestion-indexes", response_model=List[CongestionIndexResponse])
def get_all_congestion_indexes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(CongestionIndexModel).offset(skip).limit(limit).all()

@app.get("/congestion-indexes/{index_id}", response_model=CongestionIndexResponse)
def get_congestion_index(
    index_id: int,
    current_user: UserModel = Depends(get_current_user),
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
    current_user: UserModel = Depends(get_current_user),
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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Index code conflict.")

@app.delete("/congestion-indexes/{index_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_congestion_index(
    index_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    obj = db.query(CongestionIndexModel).filter(CongestionIndexModel.id == index_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Congestion index not found")

    try:
        db.delete(obj)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete congestion index with existing associated transit incidents."
        )
# ------------------------------------------------------------------------------
# 8. Primary Entity CRUD Endpoints (Transit Incidents)
# ------------------------------------------------------------------------------
@app.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    data: IncidentCreate,
    current_user: UserModel = Depends(get_current_user),
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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Incident code '{data.incident_code}' already exists.")

@app.get("/incidents", response_model=List[IncidentResponse])
def get_all_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),  # Increased max limit to 1000 & default to 50
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Sorts by newest created incidents first
    return db.query(IncidentModel).order_by(IncidentModel.id.desc()).offset(skip).limit(limit).all()

@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident_by_id(
    incident_id: int,
    current_user: UserModel = Depends(get_current_user),
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
    current_user: UserModel = Depends(get_current_user),
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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Incident code conflict.")

@app.delete("/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(
    incident_id: int,
    current_user: UserModel = Depends(get_current_user),
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
    current_user: UserModel = Depends(get_current_user),
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
    uvicorn.run("main:app", host="0.0.0.0", port=8166, reload=True)