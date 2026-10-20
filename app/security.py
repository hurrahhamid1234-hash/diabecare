import os
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt

# The secret key comes from the server's settings (set it on Render). The fallback is only for your own laptop.
SECRET_KEY = os.environ.get("SECRET_KEY", "local-development-key-not-for-public-use")
if os.environ.get("RENDER") and SECRET_KEY.startswith("local-development"):
    raise RuntimeError("Set the SECRET_KEY environment variable on the server")
ALGORITHM = "HS256"
TOKEN_MINUTES = 60

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)