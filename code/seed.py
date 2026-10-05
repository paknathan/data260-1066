# seed.py
import os
import random
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import your parent model (e.g., CongestionIndexModel) alongside IncidentModel
from main import Base, IncidentModel, CongestionIndexModel, IncidentLogModel, DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("Seeding database...")

# Clear existing records in reverse child -> parent order
try:
    db.query(IncidentLogModel).delete()
    db.query(IncidentModel).delete()
    db.query(CongestionIndexModel).delete()
    db.commit()
except Exception as e:
    db.rollback()

# 1. Seed Parent Records (Congestion Indexes)
congestion_indexes = [
    CongestionIndexModel(
        id=1,
        index_code="CONG-001",
        level_name="Low Congestion",
        description="Minor delays during off-peak hours"
    ),
    CongestionIndexModel(
        id=2,
        index_code="CONG-002",
        level_name="Heavy Congestion",
        description="Major bottlenecks along main transit routes"
    )
]
db.add_all(congestion_indexes)
db.commit()

# 2. Seed Child Records (Incidents matching current schema)
incidents = []
routes = ["CA-85 N Collision", "Light Rail Blue Line Signal Failure", "Route 22 Mechanical Breakdown", "Rapid 500 Delay"]

for i in range(1, 501):  # Seeding 500 for fast execution
    incidents.append(
        IncidentModel(
            title=random.choice(routes),
            incident_code=f"INC-2026-{i:04d}",
            delay_minutes=random.randint(5, 60),
            congestion_index_id=random.choice([1, 2])
        )
    )

db.bulk_save_objects(incidents)
db.commit()

# Fetch inserted incident IDs for logs
all_incidents = db.query(IncidentModel.id).all()
incident_ids = [item.id for item in all_incidents]

# 3. Seed Incident Logs
logs = []
for i in range(1, 101):
    logs.append(
        IncidentLogModel(
            incident_id=random.choice(incident_ids),
            notes=f"Log entry detail update #{i}",
            created_at=datetime.utcnow()
        )
    )

db.bulk_save_objects(logs)
db.commit()

print("Seeding complete! Congestion indexes, incidents, and logs successfully added.")
db.close()