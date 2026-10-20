from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, GlucoseRecord
from app.schemas import GlucoseIn, GlucoseOut

router = APIRouter(prefix="/glucose", tags=["Glucose"])

@router.post("", response_model=GlucoseOut, status_code=201)
def add_reading(data: GlucoseIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    record = GlucoseRecord(
        user_id=user.user_id,
        reading_value=data.reading_value,
        reading_time=data.reading_time or datetime.now(),
        notes=data.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

@router.get("", response_model=List[GlucoseOut])
def list_readings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(GlucoseRecord)
            .filter(GlucoseRecord.user_id == user.user_id)
            .order_by(GlucoseRecord.reading_time.desc())
            .all())

@router.delete("/{record_id}", status_code=204)
def delete_reading(record_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    record = (db.query(GlucoseRecord)
              .filter(GlucoseRecord.record_id == record_id,
                      GlucoseRecord.user_id == user.user_id)
              .first())
    if not record:
        raise HTTPException(status_code=404, detail="Reading not found")
    db.delete(record)
    db.commit()