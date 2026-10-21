import hashlib
import hmac
import os
import secrets
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db
from app.mailer import mail_configured, send_mail
from app.models import User
from app.security import create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

_SECRET = os.environ.get("SECRET_KEY", "dev-only-secret")
CODE_MINUTES = 15            # a code works for 15 minutes
MAX_ATTEMPTS = 5             # wrong guesses allowed per code
RESEND_SECONDS = 60          # minimum gap between two codes for the same person
LOGIN_FAILS = 10             # failed log-ins allowed per e-mail ...
LOGIN_WINDOW = 15 * 60       # ... in this many seconds


# ---------- tables (new; the existing users table is not changed) ----------
class UnverifiedUser(Base):
    """A row here means: registered but the e-mail is not verified yet. Older accounts have no row, so they stay valid."""
    __tablename__ = "unverified_users"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)


class EmailCode(Base):
    __tablename__ = "email_codes"
    code_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(10), nullable=False)          # "verify" or "reset"
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ---------- schemas ----------
def _password_ok(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password is too long (72 bytes at most)")
    return v


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def check_password(cls, v):
        return _password_ok(v)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("email")
    @classmethod
    def lower_email(cls, v):
        return str(v).lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v):
        return str(v).lower()


class EmailOnly(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower_email(cls, v):
        return str(v).lower()


class VerifyIn(EmailOnly):
    code: str = Field(pattern=r"^\d{6}$")


class ResetIn(VerifyIn):
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v):
        return _password_ok(v)


# ---------- helpers ----------
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)      # naive UTC, used only for code expiry


def _password_matches(password: str, password_hash: str) -> bool:
    try:
        return verify_password(password, password_hash)
    except Exception:                       # e.g. a password longer than bcrypt's 72-byte limit
        return False


def _find_user(db: Session, email: str):
    return db.scalars(select(User).where(func.lower(User.email) == email)).first()


def _is_unverified(db: Session, user_id: int) -> bool:
    return mail_configured() and db.get(UnverifiedUser, user_id) is not None


def _hash_code(user_id: int, purpose: str, code: str) -> str:
    return hmac.new(_SECRET.encode(), f"{user_id}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def _issue_code(db: Session, user, purpose: str) -> str:
    """Create and e-mail a 6-digit code. Returns "sent", "failed" (mail service problem) or "wait" (asked too soon)."""
    now = _now()
    last = db.scalars(select(EmailCode).where(EmailCode.user_id == user.user_id, EmailCode.purpose == purpose)
                      .order_by(EmailCode.created_at.desc()).limit(1)).first()
    if last and (now - last.created_at).total_seconds() < RESEND_SECONDS:
        return "wait"
    db.execute(delete(EmailCode).where(EmailCode.user_id == user.user_id, EmailCode.purpose == purpose))
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(EmailCode(user_id=user.user_id, purpose=purpose, code_hash=_hash_code(user.user_id, purpose, code),
                     expires_at=now + timedelta(minutes=CODE_MINUTES), attempts=0, created_at=now))
    db.commit()
    if purpose == "verify":
        subject, what = "Your DiabeCare verification code", "verify your e-mail address"
    else:
        subject, what = "Your DiabeCare password reset code", "reset your password"
    text = (f"Hello {user.name},\n\nYour DiabeCare code to {what} is: {code}\n\n"
            f"It works for {CODE_MINUTES} minutes. If you did not ask for it, you can ignore this e-mail.\n\n"
            "DiabeCare is a student project and not a medical service.")
    return "sent" if send_mail(user.email, subject, text) else "failed"


def _check_code(db: Session, user, purpose: str, code: str) -> bool:
    row = db.scalars(select(EmailCode).where(EmailCode.user_id == user.user_id, EmailCode.purpose == purpose)
                     .order_by(EmailCode.created_at.desc()).limit(1)).first()
    if not row or row.expires_at < _now():
        return False
    if row.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many wrong codes. Please ask for a new code")
    if not hmac.compare_digest(row.code_hash, _hash_code(user.user_id, purpose, code)):
        row.attempts += 1
        db.commit()
        return False
    db.execute(delete(EmailCode).where(EmailCode.user_id == user.user_id))      # one-time use
    db.commit()
    return True


_fails: dict[str, deque] = defaultdict(deque)


def _login_throttle(email: str) -> None:
    q, now = _fails[email], _time.time()
    while q and now - q[0] > LOGIN_WINDOW:
        q.popleft()
    if len(q) >= LOGIN_FAILS:
        raise HTTPException(status_code=429, detail="Too many failed log-ins. Please try again in 15 minutes")


def _token(user) -> dict:
    return {"access_token": create_token(user.user_id), "token_type": "bearer"}


GENERIC = "If that e-mail is registered, we have sent a code to it. Check your inbox and spam folder."


# ---------- routes ----------
@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    user = _find_user(db, data.email)
    if user is not None:
        if not _is_unverified(db, user.user_id):
            raise HTTPException(status_code=409, detail="That e-mail is already registered. Please log in")
        # registered earlier but never verified: the newest registration wins (fixes typos, stops e-mail squatting)
        user.name, user.password_hash = data.name, hash_password(data.password)
        db.commit()
    else:
        user = User(name=data.name, email=data.email, password_hash=hash_password(data.password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="That e-mail is already registered. Please log in")
        db.refresh(user)
    if not mail_configured():
        return {"verify_required": False, "email_sent": False, "message": "Account created"}
    if db.get(UnverifiedUser, user.user_id) is None:
        db.add(UnverifiedUser(user_id=user.user_id))
        db.commit()
    result = _issue_code(db, user, "verify")
    return {"verify_required": True, "email_sent": result != "failed",
            "message": "We could not send the e-mail. Use Resend code in a minute." if result == "failed"
            else "We sent a 6-digit code to your e-mail. Enter it to finish."}


@router.post("/verify-email")
def verify_email(data: VerifyIn, db: Session = Depends(get_db)):
    user = _find_user(db, data.email)
    if not user or not _check_code(db, user, "verify", data.code):
        raise HTTPException(status_code=400, detail="That code is wrong or has expired")
    db.execute(delete(UnverifiedUser).where(UnverifiedUser.user_id == user.user_id))
    db.commit()
    return _token(user)


@router.post("/resend-code")
def resend_code(data: EmailOnly, db: Session = Depends(get_db)):
    user = _find_user(db, data.email)
    if user and _is_unverified(db, user.user_id):
        _issue_code(db, user, "verify")
    return {"message": GENERIC}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    _login_throttle(data.email)
    user = _find_user(db, data.email)
    if not user or not _password_matches(data.password, user.password_hash):
        _fails[data.email].append(_time.time())
        raise HTTPException(status_code=401, detail="Wrong email or password")
    _fails.pop(data.email, None)
    if _is_unverified(db, user.user_id):
        raise HTTPException(status_code=403, detail="Email not verified. Enter the code we sent you")
    return _token(user)


@router.post("/forgot-password")
def forgot_password(data: EmailOnly, db: Session = Depends(get_db)):
    user = _find_user(db, data.email)
    if user:
        _issue_code(db, user, "reset")
    return {"message": GENERIC}


@router.post("/reset-password")
def reset_password(data: ResetIn, db: Session = Depends(get_db)):
    user = _find_user(db, data.email)
    if not user or not _check_code(db, user, "reset", data.code):
        raise HTTPException(status_code=400, detail="That code is wrong or has expired")
    user.password_hash = hash_password(data.new_password)
    db.execute(delete(UnverifiedUser).where(UnverifiedUser.user_id == user.user_id))   # the code proved the e-mail is theirs
    db.commit()
    _fails.pop(data.email, None)
    return {"message": "Password changed. Please log in"}