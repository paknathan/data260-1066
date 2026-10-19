"""Part 1 - CRUD route handlers for the MongoDB document collection."""
from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError, WriteError

from database import doc_collection, utcnow
from models import TransitIncidentDoc

router = APIRouter(prefix="/api/items", tags=["Municipal Transit Documents"])


def serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


def _object_id(item_id: str) -> ObjectId:
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail=f"Invalid ID format: '{item_id}' is not a 24-char hex ObjectId")
    return ObjectId(item_id)


def _db_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ServerSelectionTimeoutError):
        return HTTPException(status_code=503, detail="MongoDB is unavailable")
    if isinstance(exc, WriteError):  # rejected by the server-side $jsonSchema validator
        return HTTPException(status_code=422, detail=f"Document failed MongoDB validation: {exc.details}")
    return HTTPException(status_code=500, detail=f"Database error: {exc}")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_incident(item: TransitIncidentDoc):
    now = utcnow()
    data = item.model_dump()
    data["created_at"] = now
    data["updated_at"] = now
    try:
        result = doc_collection.insert_one(data)
        return serialize(doc_collection.find_one({"_id": result.inserted_id}))
    except PyMongoError as exc:
        raise _db_error(exc)


@router.get("")
def list_incidents():
    try:
        return [serialize(d) for d in doc_collection.find().sort("created_at", DESCENDING)]
    except PyMongoError as exc:
        raise _db_error(exc)


@router.get("/{item_id}")
def get_incident(item_id: str):
    oid = _object_id(item_id)
    try:
        doc = doc_collection.find_one({"_id": oid})
    except PyMongoError as exc:
        raise _db_error(exc)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Incident {item_id} not found")
    return serialize(doc)


@router.put("/{item_id}")
def update_incident(item_id: str, item: TransitIncidentDoc):
    oid = _object_id(item_id)
    data = item.model_dump()
    data["updated_at"] = utcnow()
    try:
        doc = doc_collection.find_one_and_update(
            {"_id": oid}, {"$set": data}, return_document=ReturnDocument.AFTER
        )
    except PyMongoError as exc:
        raise _db_error(exc)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Incident {item_id} not found")
    return serialize(doc)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(item_id: str):
    oid = _object_id(item_id)
    try:
        result = doc_collection.delete_one({"_id": oid})
    except PyMongoError as exc:
        raise _db_error(exc)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Incident {item_id} not found")
    return None
