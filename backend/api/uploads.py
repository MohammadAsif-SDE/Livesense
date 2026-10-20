"""
api/uploads.py
──────────────
File upload and session query endpoints.

Endpoints:
  POST /uploads                        — upload audio file, start processing
  GET  /uploads                        — list all upload sessions
  GET  /uploads/{session_id}           — upload + session status
  GET  /sessions                       — list all sessions (live + upload)
  GET  /sessions/{session_id}          — session detail + summary
  GET  /sessions/{session_id}/events   — paginated events
  GET  /sessions/{session_id}/speakers — per-speaker analytics
  DELETE /sessions/{session_id}        — delete session data
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from api.auth import get_current_user, get_optional_user

from config.settings import get_settings
from db.connection import get_db
from db.models import (
    FileMetadata,
    SessionDocument,
    SessionStatus,
    SessionType,
    UploadDocument,
    UploadStatus,
)
from db import repositories as repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["uploads"])

# Allowed audio MIME types
_ALLOWED_TYPES = {
    "audio/wav", "audio/wave", "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
    "audio/ogg", "audio/vorbis",
    "audio/mp4", "audio/m4a", "audio/x-m4a",
    "audio/aac",
    "video/mp4",  # many recorders save m4a as mp4
}


def _get_orchestrator():
    """Injected at runtime by main.py after models load."""
    from api.main import _orchestrator
    return _orchestrator


# ─────────────────────────────────────────────────────────────────────── #
#  Upload endpoint                                                         #
# ─────────────────────────────────────────────────────────────────────── #

@router.post("/uploads", status_code=202)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    """
    Upload an audio file for batch processing.
    Returns session_id immediately; processing runs in the background.
    Poll GET /api/sessions/{session_id} to track progress.
    """
    settings = get_settings()
    db = get_db()

    # ── Validate ───────────────────────────────────────────────────────
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: wav, mp3, flac, ogg, m4a",
        )

    # ── Check size limit (stream-safe: read in chunks) ─────────────────
    max_bytes = settings.max_upload_mb * 1024 * 1024
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    ext = Path(file.filename or "audio").suffix or ".bin"
    stored_name = f"{session_id}{ext}"
    dest_path = upload_dir / stored_name

    size_bytes = 0
    async with aiofiles.open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            size_bytes += len(chunk)
            if size_bytes > max_bytes:
                await out.close()
                os.unlink(dest_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {settings.max_upload_mb} MB",
                )
            await out.write(chunk)

    # ── Persist upload record ──────────────────────────────────────────
    upload_doc = UploadDocument(
        session_id=session_id,
        original_filename=file.filename or stored_name,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=str(dest_path),
    )
    await repo.create_upload(db, upload_doc)

    # ── Persist session record ─────────────────────────────────────────
    session_doc = SessionDocument(
        session_id=session_id,
        type=SessionType.UPLOAD,
        status=SessionStatus.PENDING,
        created_by=current_user["username"] if current_user else None,
        audio_path=str(dest_path),
        file=FileMetadata(
            original_name=file.filename or stored_name,
            stored_name=stored_name,
            size_bytes=size_bytes,
            content_type=content_type,
        ),
    )
    await repo.create_session(db, session_doc)

    # ── Queue background processing ────────────────────────────────────
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="ML models not loaded yet")

    from core.file_processor import FileProcessor
    processor = FileProcessor(orchestrator)

    background_tasks.add_task(processor.process, session_id, str(dest_path))

    logger.info("Upload accepted: session=%s file=%s size=%dB", session_id, file.filename, size_bytes)
    return {
        "session_id": session_id,
        "status": "accepted",
        "message": "Processing started. Poll /api/sessions/{session_id} for status.",
    }


# ─────────────────────────────────────────────────────────────────────── #
#  Upload listing                                                          #
# ─────────────────────────────────────────────────────────────────────── #

@router.get("/uploads")
async def list_uploads(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> List[dict]:
    db = get_db()
    return await repo.list_uploads(db, status_filter=status, limit=limit, skip=skip)


@router.get("/uploads/{session_id}")
async def get_upload(session_id: str) -> dict:
    db = get_db()
    upload = await repo.get_upload(db, session_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


# ─────────────────────────────────────────────────────────────────────── #
#  Sessions                                                               #
# ─────────────────────────────────────────────────────────────────────── #

@router.get("/sessions")
async def list_sessions(
    type: Optional[str] = Query(None, description="live | upload"),
    status: Optional[str] = Query(None, description="pending | processing | completed | failed"),
    user: Optional[str] = Query(None, description="Filter by username (admins only)"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    db = get_db()
    is_admin = current_user.get("role") == "admin"

    # Admins see all sessions; regular users see only their own
    if is_admin:
        created_by_filter = user or None       # optional user filter from query param
    else:
        created_by_filter = current_user["username"]

    return await repo.list_sessions(
        db,
        type_filter=type,
        status_filter=status,
        created_by=created_by_filter,
        limit=limit,
        skip=skip,
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    db = get_db()
    session = await repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/audio")
async def get_session_audio(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    """Stream the audio file for a session."""
    db = get_db()
    session = await repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_path: Optional[str] = session.get("audio_path")
    if not audio_path:
        raise HTTPException(status_code=404, detail="No audio file for this session")

    from pathlib import Path as _Path
    p = _Path(audio_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    suffix = p.suffix.lower()
    media_types = {
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
        ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
        ".aac": "audio/aac",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    filename = f"session_{session_id}{suffix}"
    return FileResponse(path=str(p), media_type=media_type, filename=filename)


@router.get("/sessions/{session_id}/events")
async def get_session_events(
    session_id: str,
    speaker_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    skip: int = Query(0, ge=0),
) -> dict:
    db = get_db()
    events = await repo.get_events(db, session_id, speaker_id=speaker_id, limit=limit, skip=skip)
    total = await repo.count_events(db, session_id)
    return {"session_id": session_id, "total": total, "skip": skip, "limit": limit, "events": events}


@router.get("/sessions/{session_id}/speakers")
async def get_session_speakers(session_id: str) -> List[dict]:
    db = get_db()
    speakers = await repo.get_speakers(db, session_id)
    if not speakers:
        raise HTTPException(status_code=404, detail="No speaker data found for this session")
    return speakers


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """Delete all data for a session (events, speakers, upload record, session doc, file on disk)."""
    db = get_db()
    session = await repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete stored file if upload session
    upload = await repo.get_upload(db, session_id)
    if upload and upload.get("storage_path"):
        try:
            os.unlink(upload["storage_path"])
        except FileNotFoundError:
            pass

    # Delete all collections
    await db.events.delete_many({"session_id": session_id})
    await db.speakers.delete_many({"session_id": session_id})
    await db.uploads.delete_one({"session_id": session_id})
    await db.sessions.delete_one({"session_id": session_id})
    logger.info("Deleted session %s", session_id)
