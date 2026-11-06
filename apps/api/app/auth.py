import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import session_dep
from .models import User

bearer = HTTPBearer(auto_error=False)

def make_password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()

def verify_password(password: str, saved: str) -> bool:
    try:
        scheme, salt, digest = saved.split("$")
        if scheme != "scrypt":
            return False
        computed = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(computed, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False

def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=24), "iss": "nextphase-shorts"}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")

def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(session_dep)) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"], issuer="nextphase-shorts")
        user = db.scalar(select(User).where(User.id == claims["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError):
        user = None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user
