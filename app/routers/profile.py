from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, PatientProfile
from app.schemas import ProfileIn, ProfileOut

router = APIRouter(tags=["Profile"])

@router.get("/profile", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.user_id).first()
    return profile or ProfileOut()

@router.put("/profile", response_model=ProfileOut)
def save_profile(data: ProfileIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.user_id).first()
    if not profile:
        profile = PatientProfile(user_id=user.user_id)
        db.add(profile)
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile