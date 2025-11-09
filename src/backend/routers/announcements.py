"""
Endpoints to manage and fetch announcements
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..database import announcements_collection, teachers_collection
from bson import ObjectId

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return {}
    result = {k: v for k, v in doc.items() if k != "_id"}
    result["id"] = str(doc.get("_id"))
    return result


@router.get("", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    """Return all announcements (management UI will decide viewability)."""
    out = []
    for a in announcements_collection.find().sort([("expiration_date", 1)]):
        out.append(_to_dict(a))
    return out


@router.get("/active", response_model=List[Dict[str, Any]])
def active_announcements() -> List[Dict[str, Any]]:
    """Return only currently active announcements (start_date <= now <= expiration_date).

    start_date is optional; if absent treat as immediately active.
    Dates are stored as ISO date strings (YYYY-MM-DD).
    """
    now = datetime.utcnow().date()
    out = []
    for a in announcements_collection.find():
        exp = a.get("expiration_date")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(exp).date()
        except Exception:
            # Skip malformed dates
            continue

        start = a.get("start_date")
        if start:
            try:
                start_date = datetime.fromisoformat(start).date()
            except Exception:
                start_date = None
        else:
            start_date = None

        if start_date and now < start_date:
            continue

        if now <= exp_date:
            out.append(_to_dict(a))

    # sort by expiration date asc
    out.sort(key=lambda x: x.get("expiration_date", ""))
    return out


def _require_teacher(username: Optional[str]):
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


@router.post("", response_model=Dict[str, Any])
def create_announcement(message: str, expiration_date: str, teacher_username: Optional[str] = Query(None), start_date: Optional[str] = None):
    """Create a new announcement. expiration_date is required (ISO date string)."""
    _require_teacher(teacher_username)

    # validate dates
    try:
        exp_date = datetime.fromisoformat(expiration_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid expiration_date format. Use YYYY-MM-DD")

    if start_date:
        try:
            start_d = datetime.fromisoformat(start_date).date()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
        if start_d > exp_date:
            raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    doc = {
        "message": message,
        "start_date": start_date,
        "expiration_date": exp_date.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "created_by": teacher_username or "unknown"
    }
    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return doc


@router.put("/{ann_id}", response_model=Dict[str, Any])
def update_announcement(ann_id: str, message: Optional[str] = None, expiration_date: Optional[str] = None, teacher_username: Optional[str] = Query(None), start_date: Optional[str] = None):
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(ann_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    update = {}
    if message is not None:
        update["message"] = message
    if expiration_date is not None:
        try:
            exp_date = datetime.fromisoformat(expiration_date).date()
            update["expiration_date"] = exp_date.isoformat()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid expiration_date format. Use YYYY-MM-DD")
    if start_date is not None:
        try:
            _ = datetime.fromisoformat(start_date).date()
            update["start_date"] = start_date
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = announcements_collection.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    ann = announcements_collection.find_one({"_id": oid})
    return _to_dict(ann)


@router.delete("/{ann_id}")
def delete_announcement(ann_id: str, teacher_username: Optional[str] = Query(None)):
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(ann_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    result = announcements_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
