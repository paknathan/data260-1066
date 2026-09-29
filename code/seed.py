# seed.py
import os
import random
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, IncidentModel, IncidentLogModel, DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("Seeding database...")

# Clear existing records
db.query(IncidentLogModel).delete()
db.query(IncidentModel).delete()
db.commit()

# Seed 5,000 incidents
incidents = []
types = ["Collision", "Medical Emergency", "Signal Failure", "Mechanical Breakdown", "Delay"]
routes = ["CA-85 N", "Light Rail Blue Line", "Route 22", "Rapid 500", "BART Orange Line"]

for i in range(1, 5001):
    incidents.append(
        IncidentModel(
            route_or_line=random.choice(routes),
            incident_type=random.choice(types),
            description=f"Automated test incident seed record #{i}"
        )
    )

db.bulk_save_objects(incidents)
db.commit()

# Fetch inserted incident IDs
all_incidents = db.query(IncidentModel.id).all()
incident_ids = [item.id for item in all_incidents]

# Seed 200 related logs randomly distributed among incidents
logs = []
for i in range(1, 201):
    logs.append(
        IncidentLogModel(
            incident_id=random.choice(incident_ids),
            notes=f"Log entry detail update #{i}",
            created_at=datetime.utcnow()
        )
    )

db.bulk_save_objects(logs)
db.commit()

print("Seeding complete! 5,000 incidents and 200 logs added.")
db.close()