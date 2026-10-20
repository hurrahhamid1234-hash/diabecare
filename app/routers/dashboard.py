from datetime import date, datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class DayAvg(BaseModel):
    day: date
    avg_glucose: float
    min_glucose: float
    max_glucose: float
    readings: int


class DashboardOut(BaseModel):
    days: int
    latest_glucose: Optional[float] = None
    latest_glucose_time: Optional[datetime] = None
    average_glucose: Optional[float] = None
    daily_glucose: List[DayAvg] = []
    doses_total: int = 0
    doses_taken: int = 0
    adherence_percent: Optional[float] = None
    latest_hba1c: Optional[float] = None
    latest_hba1c_date: Optional[date] = None


@router.get("", response_model=DashboardOut)
def dashboard(days: int = Query(7, ge=1, le=90),
              user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    uid = user.user_id
    now = datetime.now()
    since = now - timedelta(days=days)

    # 1. Daily averages from the MySQL view
    rows = db.execute(text(
        "SELECT day, avg_glucose, min_glucose, max_glucose, readings "
        "FROM daily_glucose WHERE user_id = :uid AND day >= :since ORDER BY day"
    ), {"uid": uid, "since": since.date()}).all()
    daily = [DayAvg(day=r[0], avg_glucose=float(r[1]), min_glucose=float(r[2]),
                    max_glucose=float(r[3]), readings=int(r[4])) for r in rows]

    # 2. Latest reading and period average
    latest = db.execute(text(
        "SELECT reading_value, reading_time FROM glucose_records "
        "WHERE user_id = :uid ORDER BY reading_time DESC LIMIT 1"
    ), {"uid": uid}).first()
    avg = db.execute(text(
        "SELECT AVG(reading_value) FROM glucose_records "
        "WHERE user_id = :uid AND reading_time >= :since"
    ), {"uid": uid, "since": since}).scalar()

    # 3. Medicine adherence (JOIN dose_logs + medicines)
    adh = db.execute(text(
        "SELECT COUNT(*), COALESCE(SUM(d.status = 'taken'), 0) "
        "FROM dose_logs d JOIN medicines m ON d.medicine_id = m.medicine_id "
        "WHERE m.user_id = :uid AND d.scheduled_time >= :since "
        "AND d.scheduled_time <= :now"
    ), {"uid": uid, "since": since, "now": now}).first()
    total, taken = int(adh[0]), int(adh[1])

    # 4. Latest HbA1c
    hba = db.execute(text(
        "SELECT result, test_date FROM medical_tests "
        "WHERE user_id = :uid AND test_name = 'HbA1c' "
        "ORDER BY test_date DESC LIMIT 1"
    ), {"uid": uid}).first()

    return DashboardOut(
        days=days,
        latest_glucose=float(latest[0]) if latest else None,
        latest_glucose_time=latest[1] if latest else None,
        average_glucose=round(float(avg), 1) if avg is not None else None,
        daily_glucose=daily,
        doses_total=total,
        doses_taken=taken,
        adherence_percent=round(100 * taken / total, 1) if total else None,
        latest_hba1c=float(hba[0]) if hba else None,
        latest_hba1c_date=hba[1] if hba else None,
    )