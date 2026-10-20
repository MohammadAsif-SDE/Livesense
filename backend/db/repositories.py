"""
db/repositories.py
──────────────────
Data-access layer.  All MongoDB operations go through these functions.
No business logic here — only read/write/upsert.

Each function accepts a `db` (AsyncIOMotorDatabase) so it's trivially
testable by injecting a mock or a test database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from db.models import (
    EventDocument,
    SessionDocument,
    SessionStatus,
    SessionSummary,
    SpeakerDocument,
    SentimentTimelinePoint,
    UploadDocument,
    UploadStatus,
    UserDocument,
    UserRole,
)

logger = logging.getLogger(__name__)

# Max timeline points stored per speaker (keeps document size bounded)
_MAX_TIMELINE_POINTS = 500


# ═══════════════════════════════════════════════════════════════════════ #
#  Sessions                                                               #
# ═══════════════════════════════════════════════════════════════════════ #

async def create_session(db: AsyncIOMotorDatabase, doc: SessionDocument) -> None:
    await db.sessions.insert_one(doc.to_mongo())


async def get_session(db: AsyncIOMotorDatabase, session_id: str) -> Optional[dict]:
    return await db.sessions.find_one({"session_id": session_id}, {"_id": 0})


async def list_sessions(
    db: AsyncIOMotorDatabase,
    *,
    type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    created_by: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[dict]:
    query: dict = {}
    if type_filter:
        query["type"] = type_filter
    if status_filter:
        query["status"] = status_filter
    if created_by is not None:
        query["created_by"] = created_by
    cursor = db.sessions.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def update_session_status(
    db: AsyncIOMotorDatabase,
    session_id: str,
    status: SessionStatus,
    *,
    error: Optional[str] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    update: dict = {
        "$set": {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
    }
    if error:
        update["$set"]["error"] = error
    if completed_at:
        update["$set"]["completed_at"] = completed_at
    await db.sessions.update_one({"session_id": session_id}, update)


async def finalize_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
    summary: SessionSummary,
    audio_path: Optional[str] = None,
) -> None:
    """Mark session completed and store the summary."""
    fields: dict = {
        "status": SessionStatus.COMPLETED.value,
        "summary": summary.model_dump(),
        "completed_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if audio_path:
        fields["audio_path"] = audio_path
    await db.sessions.update_one({"session_id": session_id}, {"$set": fields})


async def set_session_audio_path(
    db: AsyncIOMotorDatabase,
    session_id: str,
    audio_path: str,
) -> None:
    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"audio_path": audio_path, "updated_at": datetime.now(timezone.utc)}},
    )


# ═══════════════════════════════════════════════════════════════════════ #
#  Events                                                                 #
# ═══════════════════════════════════════════════════════════════════════ #

async def insert_event(db: AsyncIOMotorDatabase, doc: EventDocument) -> None:
    try:
        await db.events.insert_one(doc.to_mongo())
    except DuplicateKeyError:
        logger.warning("Duplicate event ignored: session=%s index=%s", doc.session_id, doc.event_index)


async def get_events(
    db: AsyncIOMotorDatabase,
    session_id: str,
    *,
    speaker_id: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
) -> List[dict]:
    query: dict = {"session_id": session_id}
    if speaker_id:
        query["speaker_id"] = speaker_id
    cursor = (
        db.events.find(query, {"_id": 0})
        .sort("event_index", 1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def count_events(db: AsyncIOMotorDatabase, session_id: str) -> int:
    return await db.events.count_documents({"session_id": session_id})


# ═══════════════════════════════════════════════════════════════════════ #
#  Speakers                                                               #
# ═══════════════════════════════════════════════════════════════════════ #

async def upsert_speaker_stats(
    db: AsyncIOMotorDatabase,
    session_id: str,
    speaker_id: str,
    *,
    transcript: str,
    polarity: str,
    final_score: float,
    dominant_emotion: Optional[str],
    emotions: dict,
    language: str,
    offset_seconds: float,
    chunk_duration: float = 0.0,
) -> None:
    """
    Incrementally update speaker stats using MongoDB's atomic $inc / $set.
    Avoids read-modify-write races in concurrent pipelines.
    """
    word_count = len(transcript.split())

    # Build the $inc increments
    inc_update: dict = {
        "total_utterances": 1,
        "total_words": word_count,
        "sentiment_score_sum": final_score,
        "total_speaking_seconds": chunk_duration,
        f"polarity_counts.{polarity}": 1,
    }
    for emotion, score in emotions.items():
        # Store raw counts (rounded scores * 100 to avoid float key issues)
        inc_update[f"emotion_counts.{emotion}"] = round(score * 100)

    # Timeline point (only kept if under limit)
    timeline_point = SentimentTimelinePoint(
        offset_seconds=offset_seconds,
        score=final_score,
        speaker_id=speaker_id,
    ).model_dump()

    now = datetime.now(timezone.utc)

    # Use findOneAndUpdate to compute new avg atomically
    result = await db.speakers.find_one_and_update(
        {"session_id": session_id, "speaker_id": speaker_id},
        [
            {
                "$set": {
                    **{k: {"$add": [f"${k}", v]} for k, v in {
                        "total_utterances": 1,
                        "total_words": word_count,
                        "sentiment_score_sum": final_score,
                        "total_speaking_seconds": chunk_duration,
                    }.items()},
                    "updated_at": now,
                }
            }
        ],
        upsert=False,
        return_document=ReturnDocument.AFTER,
    )

    # Fall back to simpler upsert (aggregation pipeline upsert requires Mongo 4.2+)
    if result is None:
        # First time we see this speaker — create doc
        doc = SpeakerDocument(
            session_id=session_id,
            speaker_id=speaker_id,
            total_utterances=1,
            total_words=word_count,
            total_speaking_seconds=chunk_duration,
            avg_sentiment_score=final_score,
            sentiment_score_sum=final_score,
            dominant_emotion=dominant_emotion,
            polarity_counts={polarity: 1},
            sentiment_timeline=[SentimentTimelinePoint(
                offset_seconds=offset_seconds,
                score=final_score,
                speaker_id=speaker_id,
            )],
            languages=[language] if language else [],
        )
        # Set emotion counts
        for emotion, score in emotions.items():
            doc.emotion_counts[emotion] = round(score * 100)

        try:
            await db.speakers.insert_one(doc.to_mongo())
        except DuplicateKeyError:
            pass  # race condition — another coroutine inserted first, update below
    else:
        # Incremental update on existing doc
        total = result.get("total_utterances", 1)
        new_avg = result.get("sentiment_score_sum", final_score) / max(total, 1)
        set_ops: dict = {
            "avg_sentiment_score": new_avg,
            "updated_at": now,
        }
        if dominant_emotion:
            set_ops["dominant_emotion"] = dominant_emotion

        push_ops: dict = {}
        if result.get("sentiment_timeline") is not None:
            tl_len = len(result["sentiment_timeline"])
            if tl_len < _MAX_TIMELINE_POINTS:
                push_ops["sentiment_timeline"] = timeline_point

        update: dict = {"$inc": inc_update, "$set": set_ops}
        if push_ops:
            update["$push"] = push_ops
        if language and language not in result.get("languages", []):
            update["$addToSet"] = {"languages": language}

        await db.speakers.update_one(
            {"session_id": session_id, "speaker_id": speaker_id},
            update,
        )


async def get_speakers(db: AsyncIOMotorDatabase, session_id: str) -> List[dict]:
    cursor = db.speakers.find({"session_id": session_id}, {"_id": 0})
    return await cursor.to_list(length=100)


# ═══════════════════════════════════════════════════════════════════════ #
#  Uploads                                                                #
# ═══════════════════════════════════════════════════════════════════════ #

async def create_upload(db: AsyncIOMotorDatabase, doc: UploadDocument) -> None:
    await db.uploads.insert_one(doc.to_mongo())


async def get_upload(db: AsyncIOMotorDatabase, session_id: str) -> Optional[dict]:
    return await db.uploads.find_one({"session_id": session_id}, {"_id": 0})


async def update_upload_status(
    db: AsyncIOMotorDatabase,
    session_id: str,
    status: UploadStatus,
    *,
    error: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc)
    update: dict = {"$set": {"status": status.value}}
    if status == UploadStatus.PROCESSING:
        update["$set"]["processing_started_at"] = now
    if status in (UploadStatus.COMPLETED, UploadStatus.FAILED):
        update["$set"]["processing_completed_at"] = now
    if error:
        update["$set"]["error"] = error
    await db.uploads.update_one({"session_id": session_id}, update)


async def list_uploads(
    db: AsyncIOMotorDatabase,
    *,
    status_filter: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[dict]:
    query = {}
    if status_filter:
        query["status"] = status_filter
    cursor = (
        db.uploads.find(query, {"_id": 0})
        .sort("uploaded_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


# ═══════════════════════════════════════════════════════════════════════ #
#  Analytics helpers                                                      #
# ═══════════════════════════════════════════════════════════════════════ #

async def build_session_summary(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> SessionSummary:
    """
    Aggregate a SessionSummary from the speakers and events collections.
    Called once when processing completes.
    """
    speakers = await get_speakers(db, session_id)
    event_count = await count_events(db, session_id)

    if not speakers:
        return SessionSummary(event_count=event_count)

    total_words = sum(s.get("total_words", 0) for s in speakers)
    total_seconds = sum(s.get("total_speaking_seconds", 0.0) for s in speakers)
    avg_score = (
        sum(s.get("sentiment_score_sum", 0.0) for s in speakers)
        / max(sum(s.get("total_utterances", 0) for s in speakers), 1)
    )

    # Dominant emotion across all speakers
    combined_emotions: dict = {}
    for s in speakers:
        for emotion, count in s.get("emotion_counts", {}).items():
            combined_emotions[emotion] = combined_emotions.get(emotion, 0) + count
    dominant_emotion = max(combined_emotions, key=combined_emotions.get) if combined_emotions else None

    # Combined polarity counts
    polarity_dist = {"positive": 0, "negative": 0, "neutral": 0}
    for s in speakers:
        for k, v in s.get("polarity_counts", {}).items():
            polarity_dist[k] = polarity_dist.get(k, 0) + v

    # All languages seen
    languages: list = []
    for s in speakers:
        for lang in s.get("languages", []):
            if lang not in languages:
                languages.append(lang)

    return SessionSummary(
        event_count=event_count,
        speaker_count=len(speakers),
        total_duration_seconds=round(total_seconds, 2),
        dominant_emotion=dominant_emotion,
        avg_sentiment_score=round(avg_score, 4),
        polarity_distribution=polarity_dist,
        languages=languages,
    )


# ═══════════════════════════════════════════════════════════════════════ #
#  Users                                                                  #
# ═══════════════════════════════════════════════════════════════════════ #

async def get_user_by_username(db: AsyncIOMotorDatabase, username: str) -> Optional[dict]:
    return await db.users.find_one({"username": username}, {"_id": 0})


async def create_user(db: AsyncIOMotorDatabase, doc: UserDocument) -> None:
    await db.users.insert_one(doc.to_mongo())


async def list_users(db: AsyncIOMotorDatabase) -> List[dict]:
    cursor = db.users.find({}, {"_id": 0, "hashed_password": 0})
    return await cursor.to_list(length=500)


async def ensure_admin_user(db: AsyncIOMotorDatabase, username: str, hashed_password: str) -> None:
    """Seed the default admin user if it doesn't already exist."""
    existing = await get_user_by_username(db, username)
    if existing is None:
        doc = UserDocument(
            username=username,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            full_name="Administrator",
        )
        await create_user(db, doc)
        logger.info("Default admin user '%s' created.", username)
    else:
        logger.info("Admin user '%s' already exists — skipping seed.", username)
