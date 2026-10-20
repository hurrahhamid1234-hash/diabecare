import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Settings come from environment variables when they exist (online), otherwise the local defaults below.
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "diabecare")
DB_TIMEZONE = os.environ.get("DB_TIMEZONE", "+05:30")        # India time, so dates match what users see

connect_args = {"init_command": f"SET time_zone='{DB_TIMEZONE}'"}
# An online MySQL needs an encrypted connection. Put its CA file in the project folder as ca.pem.
# Your local MySQL (localhost) does not use it.
_ca = Path(__file__).resolve().parents[1] / "ca.pem"
if os.environ.get("DB_SSL", "").lower() in ("1", "true", "yes") or (_ca.exists() and DB_HOST not in ("localhost", "127.0.0.1")):
    connect_args["ssl"] = {"ca": str(_ca)}

DATABASE_URL = URL.create(
    "mysql+pymysql", username=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_NAME,
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()