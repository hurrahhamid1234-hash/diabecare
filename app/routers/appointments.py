from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Time, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db
from app.deps import get_current_user

router = APIRouter(tags=["appointments"])

# ----------------------------------------------------------------------------
# ADMIN: whoever logs in with one of these emails gets the Admin tab.
# Register this email yourself FIRST (emails are not verified in this prototype).
# ----------------------------------------------------------------------------
ADMIN_EMAILS = ["hurrahhamid1234@gmail.com"]

SLOT_MINUTES = 30
MAX_DAYS_AHEAD = 90
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------- tables ----------
class Doctor(Base):
    __tablename__ = "doctors"
    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    specialty: Mapped[str] = mapped_column(String(100), nullable=False)
    qualification: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class DoctorAvailability(Base):
    """Weekly repeating working hours: e.g. doctor 1, weekday 0 (Mon), 09:00 to 13:00."""
    __tablename__ = "doctor_availability"
    availability_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.doctor_id", ondelete="CASCADE"), index=True, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (Index("ix_appt_doctor_time", "doctor_id", "appointment_time"),)
    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.doctor_id"), nullable=False)
    appointment_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")  # booked / cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------- schemas ----------
class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    doctor_id: int
    name: str
    specialty: str
    qualification: Optional[str] = None


class DoctorIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    specialty: str = Field(min_length=2, max_length=100)
    qualification: Optional[str] = Field(default=None, max_length=100)

    @field_validator("name", "specialty")
    @classmethod
    def strip_required(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("must have at least 2 characters")
        return v

    @field_validator("qualification")
    @classmethod
    def strip_optional(cls, v):
        v = (v or "").strip()
        return v or None


class AvailabilityIn(BaseModel):
    weekdays: list[int] = Field(min_length=1, max_length=7)  # 0 = Mon ... 6 = Sun
    start_time: time
    end_time: time

    @field_validator("weekdays")
    @classmethod
    def check_days(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekday must be 0 (Mon) to 6 (Sun)")
        return sorted(set(v))

    @model_validator(mode="after")
    def check_times(self):
        self.start_time = self.start_time.replace(second=0, microsecond=0)
        self.end_time = self.end_time.replace(second=0, microsecond=0)
        if self.end_time <= self.start_time:
            raise ValueError("end time must be after start time")
        if self.start_time.minute not in (0, 30) or self.end_time.minute not in (0, 30):
            raise ValueError("times must be on the hour or half hour")
        return self


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    availability_id: int
    doctor_id: int
    weekday: int
    start_time: time
    end_time: time


class AppointmentIn(BaseModel):
    doctor_id: int
    appointment_time: datetime
    reason: Optional[str] = Field(default=None, max_length=255)

    @field_validator("appointment_time")
    @classmethod
    def clean_time(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            v = v.replace(tzinfo=None)
        return v.replace(second=0, microsecond=0)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v):
        v = (v or "").strip()
        return v or None


class AppointmentOut(BaseModel):
    appointment_id: int
    doctor_id: int
    doctor_name: str
    specialty: str
    appointment_time: datetime
    reason: Optional[str] = None
    status: str
    patient_name: Optional[str] = None   # only filled for admin


# ---------- helpers ----------
SAMPLE_DOCTORS = [
    ("Dr. Asha Verma", "Diabetologist", "MBBS, MD (Medicine)"),
    ("Dr. Rohan Mehta", "Endocrinologist", "MBBS, DM (Endocrinology)"),
    ("Dr. Neha Iyer", "General Physician", "MBBS"),
    ("Dr. Sameer Khan", "Dietitian", "MSc (Clinical Nutrition)"),
]
# Made-up sample entries for the prototype. The admin can add or remove doctors in the Admin tab.


def ensure_doctors(db: Session) -> None:
    """First run only: add sample doctors, available Monday to Saturday 09:00 to 17:00."""
    if db.scalar(select(func.count(Doctor.doctor_id))) == 0:
        for n, s, q in SAMPLE_DOCTORS:
            d = Doctor(name=n, specialty=s, qualification=q)
            db.add(d)
            db.flush()
            for wd in range(0, 6):
                db.add(DoctorAvailability(doctor_id=d.doctor_id, weekday=wd, start_time=time(9, 0), end_time=time(17, 0)))
        db.commit()


def is_admin(user) -> bool:
    return (getattr(user, "email", "") or "").strip().lower() in [e.lower() for e in ADMIN_EMAILS]


def require_admin(user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def free_slots(db: Session, doctor_id: int, day: date) -> list[datetime]:
    """All open 30-minute slots of a doctor on a given date."""
    windows = db.scalars(select(DoctorAvailability).where(
        DoctorAvailability.doctor_id == doctor_id, DoctorAvailability.weekday == day.weekday())).all()
    day_start = datetime.combine(day, time(0, 0))
    taken = set(db.scalars(select(Appointment.appointment_time).where(
        Appointment.doctor_id == doctor_id, Appointment.status == "booked",
        Appointment.appointment_time >= day_start, Appointment.appointment_time < day_start + timedelta(days=1))).all())
    now = datetime.now()
    out = []
    for w in windows:
        cur = datetime.combine(day, w.start_time)
        end = datetime.combine(day, w.end_time)
        while cur + timedelta(minutes=SLOT_MINUTES) <= end:
            if cur > now and cur not in taken:
                out.append(cur)
            cur += timedelta(minutes=SLOT_MINUTES)
    return sorted(set(out))


def to_out(a: Appointment, d: Doctor, patient_name: Optional[str] = None) -> AppointmentOut:
    return AppointmentOut(
        appointment_id=a.appointment_id, doctor_id=a.doctor_id, doctor_name=d.name, specialty=d.specialty,
        appointment_time=a.appointment_time, reason=a.reason, status=a.status, patient_name=patient_name,
    )


# ---------- patient endpoints ----------
@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_doctors(db)
    return db.scalars(select(Doctor).order_by(Doctor.name)).all()


@router.get("/doctors/{doctor_id}/availability", response_model=list[AvailabilityOut])
def doctor_availability(doctor_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_id)
                      .order_by(DoctorAvailability.weekday, DoctorAvailability.start_time)).all()


@router.get("/doctors/{doctor_id}/slots")
def doctor_slots(doctor_id: int, day: date = Query(..., alias="date"),
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    if db.get(Doctor, doctor_id) is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if day > date.today() + timedelta(days=MAX_DAYS_AHEAD):
        return {"date": day.isoformat(), "slots": []}
    return {"date": day.isoformat(), "slots": [s.strftime("%H:%M") for s in free_slots(db, doctor_id, day)]}


@router.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book(body: AppointmentIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doctor = db.get(Doctor, body.doctor_id)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    t = body.appointment_time
    if t <= datetime.now():
        raise HTTPException(status_code=422, detail="Choose a time in the future")
    if t > datetime.now() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=422, detail=f"Appointments can be booked up to {MAX_DAYS_AHEAD} days ahead")

    if t not in free_slots(db, body.doctor_id, t.date()):
        # either outside the doctor's working hours or already booked
        taken = db.scalar(select(Appointment.appointment_id).where(
            Appointment.doctor_id == body.doctor_id, Appointment.status == "booked", Appointment.appointment_time == t))
        if taken is not None:
            raise HTTPException(status_code=409, detail="That slot is already taken. Please choose another time")
        raise HTTPException(status_code=422, detail="The doctor is not available at that time")

    mine = db.scalar(select(Appointment.appointment_id).where(
        Appointment.user_id == user.user_id, Appointment.status == "booked", Appointment.appointment_time == t))
    if mine is not None:
        raise HTTPException(status_code=409, detail="You already have an appointment at that time")

    a = Appointment(user_id=user.user_id, doctor_id=body.doctor_id, appointment_time=t,
                    reason=body.reason, status="booked")
    db.add(a)
    db.commit()
    db.refresh(a)
    return to_out(a, doctor)


@router.get("/appointments", response_model=list[AppointmentOut])
def my_appointments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        select(Appointment, Doctor).join(Doctor, Doctor.doctor_id == Appointment.doctor_id)
        .where(Appointment.user_id == user.user_id)
        .order_by(Appointment.appointment_time.desc())).all()
    return [to_out(a, d) for a, d in rows]


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(appointment_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = db.scalar(select(Appointment).where(
        Appointment.appointment_id == appointment_id, Appointment.user_id == user.user_id))
    if a is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if a.status == "booked":
        a.status = "cancelled"
        db.commit()
        db.refresh(a)
    return to_out(a, db.get(Doctor, a.doctor_id))


# ---------- admin endpoints ----------
@router.get("/admin/check")
def admin_check(user=Depends(get_current_user)):
    return {"is_admin": is_admin(user)}


@router.post("/admin/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def admin_add_doctor(body: DoctorIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    d = Doctor(name=body.name, specialty=body.specialty, qualification=body.qualification)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/admin/doctors/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_doctor(doctor_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    d = db.get(Doctor, doctor_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    used = db.scalar(select(func.count(Appointment.appointment_id)).where(Appointment.doctor_id == doctor_id))
    if used:
        raise HTTPException(status_code=409, detail="This doctor has appointments, so cannot be deleted. Remove their availability instead")
    for av in db.scalars(select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_id)).all():
        db.delete(av)
    db.delete(d)
    db.commit()


@router.post("/admin/doctors/{doctor_id}/availability", response_model=list[AvailabilityOut],
             status_code=status.HTTP_201_CREATED)
def admin_add_availability(doctor_id: int, body: AvailabilityIn, db: Session = Depends(get_db),
                           admin=Depends(require_admin)):
    if db.get(Doctor, doctor_id) is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    existing = db.scalars(select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_id)).all()
    created = []
    for wd in body.weekdays:
        for e in existing:
            if e.weekday == wd and body.start_time < e.end_time and e.start_time < body.end_time:
                raise HTTPException(status_code=409, detail=f"{WEEKDAYS[wd]} already has hours that overlap with these")
        created.append(DoctorAvailability(doctor_id=doctor_id, weekday=wd,
                                          start_time=body.start_time, end_time=body.end_time))
    db.add_all(created)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


@router.delete("/admin/availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_availability(availability_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    av = db.get(DoctorAvailability, availability_id)
    if av is None:
        raise HTTPException(status_code=404, detail="Availability not found")
    db.delete(av)
    db.commit()


@router.get("/admin/appointments", response_model=list[AppointmentOut])
def admin_all_appointments(db: Session = Depends(get_db), admin=Depends(require_admin)):
    from app.models import User
    rows = db.execute(
        select(Appointment, Doctor, User.name)
        .join(Doctor, Doctor.doctor_id == Appointment.doctor_id)
        .join(User, User.user_id == Appointment.user_id)
        .order_by(Appointment.appointment_time.desc()).limit(200)).all()
    return [to_out(a, d, n) for a, d, n in rows]