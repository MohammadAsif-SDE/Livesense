"""
db/connection.py
────────────────
Motor (async MongoDB) client lifecycle.

Usage:
    await init_db()          # call once at startup
    db = get_db()            # get the database handle anywhere
    await close_db()         # call on shutdown
"""

from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def init_db() -> None:
    """Create Motor client and ensure all indexes exist."""
    global _client, _db
    settings = get_settings()

    logger.info("Connecting to MongoDB: %s / %s", settings.mongodb_url, settings.mongodb_db)
    _client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
    )
    _db = _client[settings.mongodb_db]

    # Verify connectivity
    await _client.admin.command("ping")
    logger.info("MongoDB connected.")

    await _ensure_indexes(_db)


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _db


# ── Index definitions ─────────────────────────────────────────────────── #

async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all indexes idempotently.
    Designed for horizontal scalability:
      - All high-cardinality collections use session_id as leading shard key
      - event_index gives deterministic ordering within a session
      - TTL index on events lets you auto-expire old data
    """

    # ── sessions ─────────────────────────────────────────────────────────
    await db.sessions.create_indexes([
        IndexModel([("session_id", ASCENDING)], unique=True, name="session_id_unique"),
        IndexModel([("type", ASCENDING), ("status", ASCENDING)], name="type_status"),
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
    ])

    # ── events (hot path — every transcribed chunk lands here) ───────────
    await db.events.create_indexes([
        # Primary lookup: all events for a session in order
        IndexModel(
            [("session_id", ASCENDING), ("event_index", ASCENDING)],
            unique=True,
            name="session_event_unique",
        ),
        # Per-speaker queries within a session
        IndexModel(
            [("session_id", ASCENDING), ("speaker_id", ASCENDING)],
            name="session_speaker",
        ),
        # Time-range queries
        IndexModel([("timestamp_utc", DESCENDING)], name="timestamp_desc"),
        # Optional TTL — expire events older than 90 days
        # Set expireAfterSeconds=0 and use timestamp_utc as TTL field
        # Uncomment to enable auto-expiry:
        # IndexModel(
        #     [("timestamp_utc", ASCENDING)],
        #     expireAfterSeconds=90 * 86_400,
        #     name="events_ttl",
        # ),
    ])

    # ── speakers (per-session aggregated speaker stats) ──────────────────
    await db.speakers.create_indexes([
        IndexModel(
            [("session_id", ASCENDING), ("speaker_id", ASCENDING)],
            unique=True,
            name="session_speaker_unique",
        ),
    ])

    # ── uploads ──────────────────────────────────────────────────────────
    await db.uploads.create_indexes([
        IndexModel([("session_id", ASCENDING)], unique=True, name="upload_session_unique"),
        IndexModel([("status", ASCENDING)], name="upload_status"),
        IndexModel([("uploaded_at", DESCENDING)], name="upload_time_desc"),
    ])

    # ── users ─────────────────────────────────────────────────────────────
    await db.users.create_indexes([
        IndexModel([("username", ASCENDING)], unique=True, name="username_unique"),
    ])

    logger.info("MongoDB indexes ensured.")
