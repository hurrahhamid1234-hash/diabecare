from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

import joblib
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.deps import get_current_user
from app.models import User

ML_DIR = Path(__file__).resolve().parents[2] / "ml"
DISCLAIMER = ("Educational estimate from a statistical model, not a medical "
              "diagnosis. Please consult a doctor for health decisions.")

router = APIRouter(prefix="/risk", tags=["Risk estimate"])


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)
    risk_category = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


Flag = Annotated[int, Field(ge=0, le=1)]


class RiskIn(BaseModel):
    age_years: int = Field(ge=18, le=120)
    BMI: float = Field(ge=12, le=98)
    Sex: Flag                      # 0 = female, 1 = male
    HighBP: Flag                   # told you have high blood pressure
    HighChol: Flag                 # told you have high cholesterol
    GenHlth: int = Field(ge=1, le=5)   # 1 excellent ... 5 poor
    CholCheck: Flag = 1
    Smoker: Flag = 0
    Stroke: Flag = 0
    HeartDiseaseorAttack: Flag = 0
    PhysActivity: Flag = 1
    Fruits: Flag = 1
    Veggies: Flag = 1
    HvyAlcoholConsump: Flag = 0
    AnyHealthcare: Flag = 1
    NoDocbcCost: Flag = 0
    MentHlth: int = Field(default=0, ge=0, le=30)   # bad mental-health days in last 30
    PhysHlth: int = Field(default=0, ge=0, le=30)   # bad physical-health days in last 30
    DiffWalk: Flag = 0
    Education: int = Field(default=4, ge=1, le=6)
    Income: int = Field(default=5, ge=1, le=8)


class RiskOut(BaseModel):
    risk_score: float
    risk_category: str
    top_factors: List[str]
    disclaimer: str


class HistoryOut(BaseModel):
    assessment_id: int
    risk_score: float
    risk_category: str
    created_at: datetime

    class Config:
        from_attributes = True


@lru_cache(maxsize=1)
def load_model():
    try:
        return joblib.load(ML_DIR / "model.pkl"), joblib.load(ML_DIR / "features.pkl")
    except FileNotFoundError:
        raise HTTPException(status_code=503,
                            detail="Model files not found in the ml folder")


def age_group(years: int) -> int:
    """Convert age in years to the dataset's 13 age groups (1 = 18-24 ... 13 = 80+)."""
    return 1 if years < 25 else min(13, (years - 25) // 5 + 2)


def to_category(score: float) -> str:
    if score < 0.35:
        return "low"
    if score < 0.65:
        return "moderate"
    return "high"


@router.post("/estimate", response_model=RiskOut)
def estimate(data: RiskIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    model, features = load_model()

    row = data.model_dump()
    row["Age"] = age_group(row.pop("age_years"))
    frame = pd.DataFrame([row])[features]          # same column order as training

    score = float(model.predict_proba(frame)[0][1])
    category = to_category(score)

    # Which inputs pushed this person's score up the most
    factors: List[str] = []
    if category != "low":
        z = (frame.to_numpy(dtype=float) - model[0].mean_) / model[0].scale_
        contrib = z[0] * model[-1].coef_[0]
        ranked = sorted(zip(features, contrib), key=lambda t: t[1], reverse=True)
        factors = [name for name, c in ranked[:3] if c > 0.1]

    db.add(RiskAssessment(user_id=user.user_id, risk_score=round(score, 3),
                          risk_category=category))
    db.commit()

    return RiskOut(risk_score=round(score, 3), risk_category=category,
                   top_factors=factors, disclaimer=DISCLAIMER)


@router.get("/history", response_model=List[HistoryOut])
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(RiskAssessment)
            .filter(RiskAssessment.user_id == user.user_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(20)
            .all())


@router.delete("/history/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    row = (db.query(RiskAssessment)
           .filter(RiskAssessment.assessment_id == assessment_id,
                   RiskAssessment.user_id == user.user_id)
           .first())
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    db.delete(row)
    db.commit()