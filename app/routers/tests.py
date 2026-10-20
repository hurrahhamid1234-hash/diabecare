from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, MedicalTest
from app.schemas import TestIn, TestOut

router = APIRouter(prefix="/tests", tags=["Medical tests"])

def _get_own(db: Session, user: User, test_id: int) -> MedicalTest:
    test = (db.query(MedicalTest)
            .filter(MedicalTest.test_id == test_id, MedicalTest.user_id == user.user_id)
            .first())
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return test

@router.post("", response_model=TestOut, status_code=201)
def add_test(data: TestIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    test = MedicalTest(user_id=user.user_id, **data.model_dump())
    db.add(test)
    db.commit()
    db.refresh(test)
    return test

@router.get("", response_model=List[TestOut])
def list_tests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(MedicalTest)
            .filter(MedicalTest.user_id == user.user_id)
            .order_by(MedicalTest.test_date.desc())
            .all())

@router.put("/{test_id}", response_model=TestOut)
def update_test(test_id: int, data: TestIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    test = _get_own(db, user, test_id)
    for field, value in data.model_dump().items():
        setattr(test, field, value)
    db.commit()
    db.refresh(test)
    return test

@router.delete("/{test_id}", status_code=204)
def delete_test(test_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    test = _get_own(db, user, test_id)
    db.delete(test)
    db.commit()