from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


# ------------------------------------------------------------------------------
# Legacy SQL models (HW5) - unchanged
# ------------------------------------------------------------------------------
class CongestionIndex(Base):
    __tablename__ = "Congestion_indexes"

    id = Column(Integer, primary_key=True, index=True)
    level_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    index_code = Column(String(20), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    incidents = relationship("TransitIncident", back_populates="congestion_index")


class TransitIncident(Base):
    __tablename__ = "Transit_incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    incident_code = Column(String(50), unique=True, nullable=False, index=True)
    delay_minutes = Column(Integer, nullable=False, default=0)
    congestion_index_id = Column(Integer, ForeignKey("Congestion_indexes.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    congestion_index = relationship("CongestionIndex", back_populates="incidents")


# ------------------------------------------------------------------------------
# HW6 Part 1 - MongoDB document model (Pydantic)
# ------------------------------------------------------------------------------
class IncidentStatus(str, Enum):
    reported = "reported"
    investigating = "investigating"
    resolved = "resolved"


class TransitCategory(str, Enum):
    bus = "bus"
    light_rail = "light_rail"
    subway = "subway"


class TransitIncidentDoc(BaseModel):
    """Request body for create (POST) and full update (PUT)."""
    model_config = ConfigDict(use_enum_values=True, str_strip_whitespace=True, extra="forbid")

    title: str = Field(..., min_length=1, max_length=100, description="Required short summary")
    description: Optional[str] = Field(None, max_length=2000, description="Optional details")
    status: IncidentStatus = Field(IncidentStatus.reported, description="reported | investigating | resolved")
    category: TransitCategory = Field(..., description="bus | light_rail | subway")
    event_time: datetime = Field(..., description="ISO 8601 date/time the incident occurred")


# ------------------------------------------------------------------------------
# HW6 Part 2 - chat / memory schemas
# ------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    session_id: Optional[str] = Field(None, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    memory_used: Dict[str, Any]
    usage: Dict[str, Any]
