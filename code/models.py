from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

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