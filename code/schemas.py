from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

# --- Congestion Index Schemas ---
class CongestionIndexBase(BaseModel):
    level_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    # Format pattern validation: e.g., CONG-HIGH-01
    index_code: str = Field(
        ..., 
        pattern=r"^CONG-[A-Z0-9]+-[0-9]+$", 
        description="Format: CONG-LEVEL-NUMBER (e.g., CONG-HIGH-01)"
    )

class CongestionIndexCreate(CongestionIndexBase):
    pass

class CongestionIndexUpdate(BaseModel):
    level_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    index_code: Optional[str] = Field(None, pattern=r"^CONG-[A-Z0-9]+-[0-9]+$")

class CongestionIndexResponse(CongestionIndexBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Transit Incident Schemas ---
class TransitIncidentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    # Format pattern validation: e.g., INC-2026-001
    incident_code: str = Field(
        ..., 
        pattern=r"^INC-\d{4}-\d{3,}$", 
        description="Format: INC-YYYY-NUMBER (e.g., INC-2026-001)"
    )
    delay_minutes: int = Field(0, ge=0)
    congestion_index_id: int

class TransitIncidentCreate(TransitIncidentBase):
    pass

class TransitIncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    incident_code: Optional[str] = Field(None, pattern=r"^INC-\d{4}-\d{3,}$")
    delay_minutes: Optional[int] = Field(None, ge=0)
    congestion_index_id: Optional[int] = None

class TransitIncidentResponse(TransitIncidentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True