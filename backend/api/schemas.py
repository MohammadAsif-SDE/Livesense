"""
schemas.py
──────────
Pydantic models for API request/response and WebSocket event payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    """Body for POST /start."""
    source_lang: str = Field(
        default="en",
        description="ISO-639-1 language code for Deepgram (e.g. 'en', 'es'). 'auto' enables language detection.",
    )
    deepgram_model: str = Field(
        default="nova-3",
        description="Deepgram model: nova-3 | nova-2 | nova | enhanced | base",
    )
    diarize: bool = Field(default=True, description="Enable speaker diarization")
    endpointing: int = Field(
        default=300, ge=0, le=2000,
        description="Silence (ms) before Deepgram finalises a segment. 0 = disabled.",
    )
    punctuate: bool = Field(default=True, description="Add punctuation to transcripts")
    use_deepgram: bool = Field(default=True, description="Use Deepgram API for live transcription. False = local faster-whisper + speaker tracker.")


class SpeakerEvent(BaseModel):
    """
    Emitted once per transcribed chunk.  Streamed to the React dashboard
    over the WebSocket connection.
    """

    event_type: str = "speaker_event"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Diarization
    speaker_id: str

    # ASR
    transcript: str
    language: str

    # Translation (optional)
    translation: Optional[str] = None

    # Sentiment
    polarity: str                           # positive | negative | neutral
    final_score: float                      # [0, 1]
    text_score: Optional[float] = None
    acoustic_score: Optional[float] = None
    dominant_emotion: Optional[str] = None
    emotions: Dict[str, float] = Field(default_factory=dict)
    confidence: float


class PipelineStatus(BaseModel):
    """Response for /status endpoint."""
    running: bool
    device: str
    whisper_model: str
    source_lang: str | None = None


class ErrorResponse(BaseModel):
    detail: str
