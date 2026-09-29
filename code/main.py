import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, EmailStr
import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

# ------------------------------------------------------------------------------
# 1. Database Configuration & Models (Database: Municipal_Rel)
# ------------------------------------------------------------------------------
# Update host, user, and password as per your local MySQL setup
# Reads from terminal environment variable; falls back or raises an error if missing
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Run `export DATABASE_URL=...` first.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# User Table
class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")

# Server-Side Sessions Table
class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True, index=True)  # Opaque Session Token (UUID)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("UserModel", back_populates="sessions")

# Primary Domain Entity Table (Incident)
class IncidentModel(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    route_or_line = Column(String(100), nullable=False)  # Primary field
    incident_type = Column(String(100), nullable=False)  # Secondary field
    description = Column(Text, nullable=True)

# Create tables in MySQL if they do not exist
Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# 2. Database Dependency (Strictly using db_session_basede26)
# ------------------------------------------------------------------------------
def get_db():
    db_session_basede26 = SessionLocal()
    try:
        yield db_session_basede26
    finally:
        db_session_basede26.close()

# ------------------------------------------------------------------------------
# 3. Pydantic Schemas
# ------------------------------------------------------------------------------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class IncidentCreate(BaseModel):
    route_or_line: str
    incident_type: str
    description: Optional[str] = None

class IncidentUpdate(BaseModel):
    route_or_line: Optional[str] = None
    incident_type: Optional[str] = None
    description: Optional[str] = None

class IncidentResponse(BaseModel):
    incident_id: int
    route_or_line: str
    incident_type: str
    description: Optional[str] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------------------------
# 4. FastAPI Setup
# ------------------------------------------------------------------------------
app = FastAPI(title="Municipal Transit Incident Manager")

# Mount static files
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
@app.post("/register", status_code=status.HTTP_210_CREATED if hasattr(status, 'HTTP_210_CREATED') else 201)
def register(user_data: UserCreate, db_session_basede26: Session = Depends(get_db)):
    existing_user = db_session_basede26.query(UserModel).filter(UserModel.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(user_data.password.encode('utf-8'), salt).decode('utf-8')

    new_user = UserModel(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed_pw
    )
    db_session_basede26.add(new_user)
    db_session_basede26.commit()
    return {"message": "User registered successfully"}

@app.post("/login")
def login(login_data: UserLogin, response: Response, db_session_basede26: Session = Depends(get_db)):
    user = db_session_basede26.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not bcrypt.checkpw(login_data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate opaque server-side session token
    session_token = str(uuid.uuid4())
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=8)

    session_record = SessionModel(
        id=session_token,
        user_id=user.id,
        created_at=created_at,
        expires_at=expires_at
    )
    db_session_basede26.add(session_record)
    db_session_basede26.commit()

    # Set HTTP-Only opaque cookie
    response.set_cookie(
        key="session_id",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=False  # Set True in HTTPS production
    )
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
# 7. Domain Entity CRUD Endpoints (POST, GET all, GET by ID, PUT, DELETE)
# ------------------------------------------------------------------------------

# 1. Add a new record (POST)
@app.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    data: IncidentCreate,
    current_user: UserModel = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db)
):
    incident = IncidentModel(
        route_or_line=data.route_or_line,
        incident_type=data.incident_type,
        description=data.description
    )
    db_session_basede26.add(incident)
    db_session_basede26.commit()
    db_session_basede26.refresh(incident)
    return IncidentResponse(
        incident_id=incident.id,
        route_or_line=incident.route_or_line,
        incident_type=incident.incident_type,
        description=incident.description
    )

# 2. View all records (GET)
@app.get("/incidents", response_model=List[IncidentResponse])
def get_all_incidents(
    current_user: UserModel = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db)
):
    records = db_session_basede26.query(IncidentModel).all()
    return [
        IncidentResponse(
            incident_id=item.id,
            route_or_line=item.route_or_line,
            incident_type=item.incident_type,
            description=item.description
        ) for item in records
    ]

@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident_by_id(
    incident_id: int,
    current_user: UserModel = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db)
):
    incident = db_session_basede26.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")
    return IncidentResponse(
        incident_id=incident.id,
        route_or_line=incident.route_or_line,
        incident_type=incident.incident_type,
        description=incident.description
    )

# 4. Update record details (PUT)
@app.put("/incidents/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    current_user: UserModel = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db)
):
    incident = db_session_basede26.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")

    if data.route_or_line is not None:
        incident.route_or_line = data.route_or_line
    if data.incident_type is not None:
        incident.incident_type = data.incident_type
    if data.description is not None:
        incident.description = data.description

    db_session_basede26.commit()
    db_session_basede26.refresh(incident)
    return IncidentResponse(
        incident_id=incident.id,
        route_or_line=incident.route_or_line,
        incident_type=incident.incident_type,
        description=incident.description
    )

# 5. Delete a record (DELETE)
@app.delete("/incidents/{incident_id}")
def delete_incident(
    incident_id: int,
    current_user: UserModel = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db)
):
    incident = db_session_basede26.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident record not found")

    db_session_basede26.delete(incident)
    db_session_basede26.commit()
    return {"message": f"Incident record {incident_id} successfully deleted"}

# ------------------------------------------------------------------------------
# 8. Frontend Index Route
# ------------------------------------------------------------------------------
@app.get("/{full_path:path}")
def serve_react_app(full_path: str):
    return FileResponse("templates/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8166, reload=True)