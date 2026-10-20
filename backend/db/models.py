"""
db/models.py
────────────
Pydantic document models for all MongoDB collections.

Collection → Document model mapping:
  sessions  → SessionDocument
  events    → EventDocument
  speakers  → SpeakerDocument
  uploads   → UploadDocument

Design principles:
  - session_id (UUID string) is the universal join key across all collections.
    Use it as the shard key when scaling horizontally via MongoDB Atlas.
  - _id is always ObjectId; never expose it over the API — use session_id.
  - Nested sub-models keep documents self-contained and fast to read back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────── #

class SessionType(str, Enum):
    LIVE = "live"
    UPLOAD = "upload"


class SessionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Sub-models ────────────────────────────────────────────────────────── #

class FileMetadata(BaseModel):
    """Embedded in SessionDocument for upload sessions."""
    original_name: str
    stored_name: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    format: Optional[str] = None
    content_type: str


class SessionSummary(BaseModel):
    """Embedded in SessionDocument, populated when processing completes."""
    event_count: int = 0
    speaker_count: int = 0
    total_duration_seconds: float = 0.0
    dominant_emotion: Optional[str] = None
    avg_sentiment_score: float = 0.0
    polarity_distribution: Dict[str, int] = Field(default_factory=lambda: {"positive": 0, "negative": 0, "neutral": 0})
    languages: List[str] = Field(default_factory=list)


class SentimentTimelinePoint(BaseModel):
    """Sampled sentiment score at a moment in time — used for chart data."""
    offset_seconds: float
    score: float
    speaker_id: str


# ── Collection documents ──────────────────────────────────────────────── #

class SessionDocument(BaseModel):
    """
    sessions collection.

    One document per recording session (live or file upload).
    Acts as the root entity — all other collections reference session_id.

    Indexes:
      - session_id (unique)
      - (type, status)
      - created_at DESC
    """
    session_id: str                           # UUID string, shard key
    type: SessionType
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None          # username of the user who started this session
    audio_path: Optional[str] = None           # absolute path to the recorded/uploaded audio file

    # Populated for upload sessions
    file: Optional[FileMetadata] = None

    # Populated when processing completes
    summary: Optional[SessionSummary] = None

    # Error message if status == failed
    error: Optional[str] = None

    # Tags / labels for search (e.g. "meeting", "interview")
    tags: List[str] = Field(default_factory=list)

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=False)


class EventDocument(BaseModel):
    """
    events collection.

    One document per transcribed audio chunk.  This is the hot-write
    collection — every 512ms–3s of speech produces a new document.

    Indexes:
      - (session_id, event_index) unique — primary query path
      - (session_id, speaker_id)
      - timestamp_utc DESC
      - [optional] TTL on timestamp_utc

    At scale: shard on {session_id: "hashed"} to distribute write load.
    """
    session_id: str
    event_index: int                          # monotonic counter per session
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    offset_seconds: float = 0.0              # position in original audio

    # Diarization
    speaker_id: str

    # ASR
    transcript: str
    language: str
    translation: Optional[str] = None

    # Sentiment
    polarity: str                             # positive | negative | neutral
    final_score: float                        # [0, 1]
    text_score: Optional[float] = None
    acoustic_score: Optional[float] = None
    dominant_emotion: Optional[str] = None
    emotions: Dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=False)


class SpeakerDocument(BaseModel):
    """
    speakers collection.

    One document per (session, speaker) pair.
    Incrementally updated via $inc / $set upserts as events arrive.
    Provides fast per-speaker analytics without aggregation pipelines.

    Indexes:
      - (session_id, speaker_id) unique
    """
    session_id: str
    speaker_id: str                           # SPEAKER_00, SPEAKER_01, …

    # Speaking time metrics
    total_utterances: int = 0
    total_words: int = 0
    total_speaking_seconds: float = 0.0

    # Sentiment aggregates
    avg_sentiment_score: float = 0.0
    sentiment_score_sum: float = 0.0          # used to recompute avg incrementally
    dominant_emotion: Optional[str] = None

    # Emotion distribution (raw counts — normalise on read)
    emotion_counts: Dict[str, int] = Field(default_factory=dict)

    # Polarity breakdown
    polarity_counts: Dict[str, int] = Field(
        default_factory=lambda: {"positive": 0, "negative": 0, "neutral": 0}
    )

    # Sampled timeline for charting (max 500 points per speaker)
    sentiment_timeline: List[SentimentTimelinePoint] = Field(default_factory=list)

    # Languages observed
    languages: List[str] = Field(default_factory=list)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=False)


class UploadDocument(BaseModel):
    """
    uploads collection.

    Tracks file upload state separately from sessions so the upload
    lifecycle (multipart receive, virus scan, format conversion) is
    decoupled from ML processing.

    Indexes:
      - session_id unique
      - status
      - uploaded_at DESC
    """
    session_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    storage_path: str                         # absolute local path or S3 key
    status: UploadStatus = UploadStatus.UPLOADED

    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None

    # Detailed error for debugging
    error: Optional[str] = None

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=False)


# ── Users ─────────────────────────────────────────────────────────────── #

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserDocument(BaseModel):
    """
    users collection.

    Stores application users for authentication.

    Indexes:
      - username (unique)
    """
    username: str
    hashed_password: str
    role: UserRole = UserRole.USER
    full_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None       # username of the admin who created this user
    is_active: bool = True

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=False)
