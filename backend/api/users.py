"""
api/users.py
────────────
User management endpoints (admin only):
  GET  /users          — list all users
  POST /users          — register a new user
  DELETE /users/{username} — deactivate a user
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_admin
from core.auth_utils import hash_password
from db.connection import get_db
from db.models import UserDocument, UserRole
from db.repositories import create_user, get_user_by_username, list_users

router = APIRouter(prefix="/users", tags=["users"])


# ── Request / Response schemas ────────────────────────────────────────── #

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(..., min_length=6)
    full_name: str | None = None
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    username: str
    role: str
    full_name: str | None = None
    is_active: bool
    created_at: str
    created_by: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────── #

@router.get("", response_model=list[UserResponse])
async def get_users(_admin: dict = Depends(require_admin)) -> list[UserResponse]:
    db = get_db()
    users = await list_users(db)
    return [
        UserResponse(
            username=u["username"],
            role=u["role"],
            full_name=u.get("full_name"),
            is_active=u.get("is_active", True),
            created_at=str(u.get("created_at", "")),
            created_by=u.get("created_by"),
        )
        for u in users
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    body: CreateUserRequest,
    admin: dict = Depends(require_admin),
) -> UserResponse:
    db = get_db()
    existing = await get_user_by_username(db, body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already taken",
        )

    doc = UserDocument(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        full_name=body.full_name,
        created_by=admin["username"],
    )
    await create_user(db, doc)
    return UserResponse(
        username=doc.username,
        role=doc.role.value,
        full_name=doc.full_name,
        is_active=doc.is_active,
        created_at=str(doc.created_at),
        created_by=doc.created_by,
    )


@router.patch("/{username}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    username: str,
    admin: dict = Depends(require_admin),
) -> None:
    if username == admin["username"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    db = get_db()
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.users.update_one({"username": username}, {"$set": {"is_active": False}})


@router.patch("/{username}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
async def reactivate_user(
    username: str,
    _admin: dict = Depends(require_admin),
) -> None:
    db = get_db()
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.users.update_one({"username": username}, {"$set": {"is_active": True}})


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    username: str,
    admin: dict = Depends(require_admin),
) -> None:
    if username == admin["username"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    db = get_db()
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.users.delete_one({"username": username})
