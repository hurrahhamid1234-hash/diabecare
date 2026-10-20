from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Float, Text, ForeignKey, Index, Boolean
from app.database import Base

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    profile_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    profile_notes = Column(Text, nullable=True)

class GlucoseRecord(Base):
    __tablename__ = "glucose_records"

    record_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    reading_value = Column(Float, nullable=False)
    reading_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    notes = Column(String(255), nullable=True)

    __table_args__ = (Index("ix_glucose_user_time", "user_id", "reading_time"),)

class MedicalTest(Base):
    __tablename__ = "medical_tests"

    test_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    test_name = Column(String(100), nullable=False)
    result = Column(Float, nullable=False)
    unit = Column(String(30), nullable=True)
    test_date = Column(Date, nullable=False)
    notes = Column(String(255), nullable=True)
    report_reference = Column(String(255), nullable=True)

class Medicine(Base):
    __tablename__ = "medicines"

    medicine_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    medicine_name = Column(String(100), nullable=False)
    instructions = Column(String(255), nullable=True)
    schedule_times = Column(String(100), nullable=False)  # e.g. "08:00,20:00"
    active = Column(Boolean, nullable=False, default=True)

class DoseLog(Base):
    __tablename__ = "dose_logs"

    dose_log_id = Column(Integer, primary_key=True, autoincrement=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String(10), nullable=False, default="pending")
    action_time = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_dose_med_time", "medicine_id", "scheduled_time"),)