"""
Authentication endpoints and JWT utilities.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from hashlib import sha256

from app.models.database import get_db, User, UserRole
from app.config import DEMO_MODE

import os

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "video-nuggets-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


class LoginRequest(BaseModel):
    username: str
    password: str


def _hash_password(password: str) -> str:
    return sha256(password.encode()).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return sha256(plain.encode()).hexdigest() == hashed


def _create_token(data: dict, expires_delta: timedelta) -> str:
    import json, base64, hmac as hmac_mod, hashlib, time
    payload = {**data, "exp": int(time.time()) + int(expires_delta.total_seconds())}
    payload_bytes = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=")
    signing_input = header + b"." + payload_bytes
    signature = base64.urlsafe_b64encode(
        hmac_mod.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (signing_input + b"." + signature).decode()


def _decode_token(token: str) -> Optional[dict]:
    import json, base64, hmac as hmac_mod, hashlib, time
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_payload = parts[0] + "." + parts[1]
        signature = parts[2]
        expected_sig = base64.urlsafe_b64encode(
            hmac_mod.new(SECRET_KEY.encode(), header_payload.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        if not hmac_mod.compare_digest(signature, expected_sig):
            return None
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Optional[User]:
    """Get current user from JWT token. Returns None for unauthenticated requests."""
    if not token:
        return None
    payload = _decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    return user


def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require a valid authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: User = Depends(require_auth)) -> User:
    """Require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_admin_or_demo(user: Optional[User] = Depends(get_current_user)) -> Optional[User]:
    """In demo mode, allow anyone to trigger generation; otherwise require admin."""
    if DEMO_MODE:
        return user
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not _verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(
        {"sub": user.username, "role": user.role.value},
        timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
            "email": user.email,
        },
    )


@router.get("/me")
def get_me(user: User = Depends(require_auth)):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role.value,
        "email": user.email,
    }
