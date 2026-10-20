import re
from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    user_id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProfileIn(BaseModel):
    date_of_birth: Optional[date] = None
    height_cm: Optional[float] = Field(default=None, ge=50, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=10, le=400)
    profile_notes: Optional[str] = Field(default=None, max_length=1000)

class ProfileOut(ProfileIn):
    class Config:
        from_attributes = True

class GlucoseIn(BaseModel):
    reading_value: float = Field(ge=20, le=600)
    reading_time: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=255)

class GlucoseOut(BaseModel):
    record_id: int
    reading_value: float
    reading_time: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class TestIn(BaseModel):
    test_name: str = Field(min_length=1, max_length=100)
    result: float
    unit: Optional[str] = Field(default=None, max_length=30)
    test_date: date
    notes: Optional[str] = Field(default=None, max_length=255)
    report_reference: Optional[str] = Field(default=None, max_length=255)

class TestOut(TestIn):
    test_id: int

    class Config:
        from_attributes = True

class MedicineIn(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=100)
    instructions: Optional[str] = Field(default=None, max_length=255)
    schedule_times: str = Field(max_length=100)  # "08:00,20:00"

    @field_validator("schedule_times")
    @classmethod
    def check_times(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if not parts:
            raise ValueError("Give at least one time, like 08:00")
        for p in parts:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", p):
                raise ValueError("Times must look like 08:00 or 20:30")
        return ",".join(parts)

class MedicineOut(MedicineIn):
    medicine_id: int
    active: bool

    class Config:
        from_attributes = True

class DoseOut(BaseModel):
    dose_log_id: int
    medicine_id: int
    medicine_name: str
    scheduled_time: datetime
    status: str
    action_time: Optional[datetime] = None

class DoseAction(BaseModel):
    status: Literal["taken", "snoozed", "skipped"]