from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func, select
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, Session, defer, mapped_column

from app.database import Base, get_db
from app.deps import get_current_user
from app.filetypes import clean_name, decode_upload
from app.models import MedicalTest

router = APIRouter(tags=["files"])

MAX_BYTES = 5 * 1024 * 1024        # one file
MAX_PER_TEST = 5                   # files per lab result
MAX_PER_USER = 30 * 1024 * 1024    # all files of one user


class ReportFile(Base):
    """A photo or PDF of a lab report, stored in the database (Render's disk is erased on every restart)."""
    __tablename__ = "test_files"
    file_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    test_id: Mapped[int] = mapped_column(ForeignKey("medical_tests.test_id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(150), nullable=False)
    mime: Mapped[str] = mapped_column(String(30), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary().with_variant(LONGBLOB(), "mysql"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=4, max_length=MAX_BYTES * 4 // 3 + 100)       # base64 text


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    file_id: int
    test_id: int
    filename: str
    mime: str
    size: int


def _own_file(db: Session, file_id: int, user_id: int, with_data: bool) -> ReportFile:
    q = select(ReportFile).where(ReportFile.file_id == file_id, ReportFile.user_id == user_id)
    if not with_data:
        q = q.options(defer(ReportFile.data))
    row = db.scalars(q).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return row


@router.get("/files", response_model=list[FileOut])
def list_files(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(ReportFile).options(defer(ReportFile.data)).where(ReportFile.user_id == user.user_id)
                      .order_by(ReportFile.file_id)).all()


@router.post("/tests/{test_id}/files", response_model=FileOut, status_code=201)
def upload(test_id: int, body: FileIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    test = db.scalars(select(MedicalTest).where(MedicalTest.test_id == test_id, MedicalTest.user_id == user.user_id)).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test result not found")
    data, mime = decode_upload(body.data, MAX_BYTES)
    count = db.scalar(select(func.count()).select_from(ReportFile).where(ReportFile.test_id == test_id, ReportFile.user_id == user.user_id))
    if count >= MAX_PER_TEST:
        raise HTTPException(status_code=409, detail=f"You can attach {MAX_PER_TEST} files to one result")
    used = db.scalar(select(func.coalesce(func.sum(ReportFile.size), 0)).where(ReportFile.user_id == user.user_id))
    if used + len(data) > MAX_PER_USER:
        raise HTTPException(status_code=409, detail="Your file storage is full. Delete some files first")
    row = ReportFile(user_id=user.user_id, test_id=test_id, filename=clean_name(body.filename), mime=mime, size=len(data), data=data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/files/{file_id}")
def download(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = _own_file(db, file_id, user.user_id, with_data=True)
    return Response(content=row.data, media_type=row.mime, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
    })


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.delete(_own_file(db, file_id, user.user_id, with_data=False))
    db.commit()