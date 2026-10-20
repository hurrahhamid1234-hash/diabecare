from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db, engine, Base
from app import models
from app.routers import auth, profile, glucose, tests, medicines, dashboard, risk, appointments, chat

Base.metadata.create_all(bind=engine)

# MySQL view: one row per user per day
with engine.begin() as conn:
    conn.execute(text("""
        CREATE OR REPLACE VIEW daily_glucose AS
        SELECT user_id,
               DATE(reading_time) AS day,
               ROUND(AVG(reading_value), 1) AS avg_glucose,
               MIN(reading_value) AS min_glucose,
               MAX(reading_value) AS max_glucose,
               COUNT(*) AS readings
        FROM glucose_records
        GROUP BY user_id, DATE(reading_time)
    """))

app = FastAPI(title="DiabeCare API")
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(glucose.router)
app.include_router(tests.router)
app.include_router(medicines.router)
app.include_router(dashboard.router)
app.include_router(risk.router)
app.include_router(appointments.router)
app.include_router(chat.router)

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND, html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}