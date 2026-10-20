from datetime import datetime, date, time
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, Medicine, DoseLog
from app.schemas import MedicineIn, MedicineOut, DoseOut, DoseAction

router = APIRouter(tags=["Medicines"])

def _own_medicine(db: Session, user: User, medicine_id: int) -> Medicine:
    med = (db.query(Medicine)
           .filter(Medicine.medicine_id == medicine_id, Medicine.user_id == user.user_id)
           .first())
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return med

@router.post("/medicines", response_model=MedicineOut, status_code=201)
def add_medicine(data: MedicineIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    med = Medicine(user_id=user.user_id, **data.model_dump())
    db.add(med)
    db.commit()
    db.refresh(med)
    return med

@router.get("/medicines", response_model=List[MedicineOut])
def list_medicines(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Medicine).filter(Medicine.user_id == user.user_id).all()

@router.delete("/medicines/{medicine_id}", status_code=204)
def deactivate_medicine(medicine_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    med = _own_medicine(db, user, medicine_id)
    med.active = False   # keep history of past doses
    db.commit()

def create_todays_doses(db: Session, user_id: int):
    today = date.today()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    meds = db.query(Medicine).filter(Medicine.user_id == user_id, Medicine.active == True).all()
    for med in meds:
        for t in med.schedule_times.split(","):
            hh, mm = map(int, t.split(":"))
            when = datetime.combine(today, time(hh, mm))
            exists = (db.query(DoseLog)
                      .filter(DoseLog.medicine_id == med.medicine_id,
                              DoseLog.scheduled_time == when)
                      .first())
            if not exists:
                db.add(DoseLog(medicine_id=med.medicine_id, scheduled_time=when))
    db.commit()

@router.get("/medicines/today", response_model=List[DoseOut])
def todays_doses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    create_todays_doses(db, user.user_id)
    today = date.today()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    rows = (db.query(DoseLog, Medicine)
            .join(Medicine, DoseLog.medicine_id == Medicine.medicine_id)
            .filter(Medicine.user_id == user.user_id,
                    DoseLog.scheduled_time >= start,
                    DoseLog.scheduled_time <= end)
            .order_by(DoseLog.scheduled_time)
            .all())
    return [DoseOut(dose_log_id=d.dose_log_id, medicine_id=m.medicine_id,
                    medicine_name=m.medicine_name, scheduled_time=d.scheduled_time,
                    status=d.status, action_time=d.action_time)
            for d, m in rows]

@router.post("/doses/{dose_log_id}/status", response_model=DoseOut)
def update_dose(dose_log_id: int, action: DoseAction,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = (db.query(DoseLog, Medicine)
           .join(Medicine, DoseLog.medicine_id == Medicine.medicine_id)
           .filter(DoseLog.dose_log_id == dose_log_id, Medicine.user_id == user.user_id)
           .first())
    if not row:
        raise HTTPException(status_code=404, detail="Dose not found")
    dose, med = row
    dose.status = action.status
    dose.action_time = datetime.now()
    db.commit()
    db.refresh(dose)
    return DoseOut(dose_log_id=dose.dose_log_id, medicine_id=med.medicine_id,
                   medicine_name=med.medicine_name, scheduled_time=dose.scheduled_time,
                   status=dose.status, action_time=dose.action_time)