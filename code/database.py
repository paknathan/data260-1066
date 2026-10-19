"""PyMongo connection + collection setup (HW6 Parts 1 & 2).

SQL for HW5 lives in main.py (it builds its own engine from DATABASE_URL).
`Base` is kept here only so the legacy models.py SQL classes still import.
"""
import os
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid, PyMongoError
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# ---- Personal configuration (Section 0) -------------------------------------
SID4 = 1066
PORT_BASE = 8000 + (SID4 % 900)          # 8166
PREFIX = f"s{SID4}"                      # s1066
SEED = SID4                              # 1066
VERIFY_SEED = 260000 + SID4              # 261066
DOMAIN_ID = SID4 % 8                     # 2

# ---- MongoDB ------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = f"{PREFIX}_doc"          # s1066_doc
DOC_COLLECTION_NAME = os.getenv("DOC_COLLECTION", "transit_incidents")

mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
mongo_db = mongo_client[MONGO_DB_NAME]

# Part 1 collection (document view of the domain)
doc_collection = mongo_db[DOC_COLLECTION_NAME]
# Part 2 collections (same DB, new collections)
messages_col = mongo_db["messages"]
summaries_col = mongo_db["summaries"]
episodes_col = mongo_db["episodes"]

# Server-side schema validation (mirrors the Pydantic model in models.py)
TRANSIT_INCIDENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["title", "status", "category", "event_time", "created_at", "updated_at"],
        "properties": {
            "title": {"bsonType": "string", "minLength": 1, "maxLength": 100},
            "description": {"bsonType": ["string", "null"], "maxLength": 2000},
            "status": {"enum": ["reported", "investigating", "resolved"]},
            "category": {"enum": ["bus", "light_rail", "subway"]},
            "event_time": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

MESSAGES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "session_id", "role", "content", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "role": {"enum": ["user", "assistant"]},
            "content": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

SUMMARIES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "scope", "text", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": ["string", "null"]},
            "scope": {"enum": ["session", "user"]},
            "text": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

EPISODES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "fact": {"bsonType": "string", "maxLength": 300},
            "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
            "embedding": {"bsonType": "array", "items": {"bsonType": ["double", "int"]}},
            "created_at": {"bsonType": "date"},
        },
    }
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_collection(name: str, validator: dict) -> None:
    try:
        mongo_db.create_collection(name, validator=validator)
    except CollectionInvalid:  # already exists -> update its validator
        mongo_db.command({"collMod": name, "validator": validator, "validationLevel": "moderate"})


def init_mongo() -> bool:
    """Create collections, validators and indexes. Returns False if Mongo is down."""
    try:
        _ensure_collection(DOC_COLLECTION_NAME, TRANSIT_INCIDENT_VALIDATOR)
        _ensure_collection("messages", MESSAGES_VALIDATOR)
        _ensure_collection("summaries", SUMMARIES_VALIDATOR)
        _ensure_collection("episodes", EPISODES_VALIDATOR)
        doc_collection.create_index([("created_at", DESCENDING)])
        messages_col.create_index([("session_id", ASCENDING), ("created_at", DESCENDING)])
        messages_col.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        summaries_col.create_index([("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)])
        episodes_col.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        return True
    except PyMongoError as exc:
        print(f"[database] MongoDB init failed: {exc}")
        return False
