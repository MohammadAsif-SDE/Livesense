"""
api/auth.py
───────────
Authentication endpoints:
  POST /auth/login   — exchange username+password for JWT
  GET  /auth/me      — return the currently authenticated user
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from core.auth_utils import create_access_token, decode_token, verify_password
from db.connection import get_db
from db.repositories import get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Response schemas ──────────────────────────────────────────────────── #

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserInfo(BaseModel):
    username: str
    role: str
    full_name: str | None = None


# ── Dependency: current authenticated user ────────────────────────────── #

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        username: str | None = payload.get("sub")
        if not username:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    db = get_db()
    user = await get_user_by_username(db, username)
    if user is None or not user.get("is_active", True):
        raise credentials_exc
    return user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_user(request: Request) -> Optional[dict]:
    """Returns the current user if a valid Bearer token is present, otherwise None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    try:
        payload = decode_token(token)
        username: str | None = payload.get("sub")
        if not username:
            return None
        db = get_db()
        user = await get_user_by_username(db, username)
        return user if user and user.get("is_active", True) else None
    except JWTError:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────── #

@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    logger.info("Login attempt — username=%r  password_len=%d", form.username, len(form.password))
    db = get_db()
    user = await get_user_by_username(db, form.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User doesn't exist",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password doesn't match",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled. Contact an admin.",
        )

    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/me", response_model=UserInfo)
async def me(current_user: dict = Depends(get_current_user)) -> UserInfo:
    return UserInfo(
        username=current_user["username"],
        role=current_user["role"],
        full_name=current_user.get("full_name"),
    )
