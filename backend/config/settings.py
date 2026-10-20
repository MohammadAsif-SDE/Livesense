from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to this file's directory (backend/)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # HuggingFace
    hf_token: str = Field(default="", description="HuggingFace access token for pyannote")

    # Deepgram
    deepgram_api_key: str = Field(default="", description="Deepgram API key for live transcription")

    # Audio
    chunk_ms: int = Field(default=512, ge=128, le=2000)
    sample_rate: int = Field(default=16_000)
    audio_channels: int = Field(default=1)

    # ASR
    whisper_model: Literal["tiny", "base", "small", "medium", "large"] = "small"

    # Compute device
    device: Literal["auto", "cpu", "mps", "cuda"] = "auto"

    # Sentiment fusion
    fusion_alpha: float = Field(default=0.6, ge=0.0, le=1.0)

    # Translation
    translate_enabled: bool = False
    source_lang: str = "auto"
    target_lang: str = "en"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    mongodb_db: str = Field(default="livesense", description="Database name")

    # Auth / JWT
    jwt_secret: str = Field(default="change-me-in-production-super-secret-key-32chars", description="JWT signing secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=480)  # 8 hours

    # Default admin credentials (seeded on first start)
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="admin123")

    # File uploads
    upload_dir: str = Field(default="/tmp/livesense_uploads", description="Directory for uploaded audio files")
    max_upload_mb: int = Field(default=500, description="Max upload file size in MB")

    @property
    def chunk_samples(self) -> int:
        """Number of audio samples per chunk."""
        return int(self.sample_rate * self.chunk_ms / 1000)

    @property
    def resolved_device(self) -> str:
        """Resolve 'auto' to the best available device."""
        if self.device != "auto":
            return self.device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
