"""
diarization.py
──────────────
Maintains a rolling audio buffer (5 seconds) and runs pyannote speaker
diarization on each new chunk.  Returns a list of speaker-labelled
segments aligned to the chunk timestamps.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import List

import numpy as np
import torch

from config.settings import get_settings

logger = logging.getLogger(__name__)

BUFFER_SECONDS = 5  # sliding window fed to pyannote


@dataclass
class DiarizationSegment:
    speaker_id: str
    start_ms: float
    end_ms: float


class Diarizer:
    """Wraps pyannote speaker-diarization-3.1 with a sliding audio buffer."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pipeline = None
        self._buffer: deque[np.ndarray] = deque()
        self._buffer_samples = 0
        self._buffer_capacity = self._settings.sample_rate * BUFFER_SECONDS

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Clear rolling buffer state — call before starting a new live session."""
        self._buffer.clear()
        self._buffer_samples = 0

    def load(self) -> None:
        """Download / load pyannote pipeline.  Call once at startup."""
        import core.torchaudio_compat  # noqa: F401 — must run before pyannote import
        from pyannote.audio import Pipeline

        token = self._settings.hf_token
        if not token:
            raise ValueError(
                "HF_TOKEN is not set.  Get a free token at https://hf.co/settings/tokens "
                "and accept pyannote model terms at "
                "https://hf.co/pyannote/speaker-diarization-3.1"
            )

        logger.info("Loading pyannote/speaker-diarization-3.1 …")
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )

        device = torch.device(self._settings.resolved_device)
        if device.type in ("cuda", "mps"):
            self._pipeline = self._pipeline.to(device)

        logger.info("Diarization pipeline ready on %s", device)

    # ------------------------------------------------------------------ #
    #  Processing                                                          #
    # ------------------------------------------------------------------ #

    def process(self, chunk: np.ndarray) -> List[DiarizationSegment]:
        """
        Append chunk to the rolling buffer and diarize the full window.
        Returns segments with timestamps relative to the buffer start.
        """
        if self._pipeline is None:
            raise RuntimeError("Diarizer not loaded. Call load() first.")

        # Maintain a sliding window.
        # Guard: never empty the buffer — if the combined chunk alone exceeds
        # capacity (can happen after drain-coalesce), keep only the last chunk.
        self._buffer.append(chunk)
        self._buffer_samples += len(chunk)
        while len(self._buffer) > 1 and self._buffer_samples > self._buffer_capacity:
            oldest = self._buffer.popleft()
            self._buffer_samples -= len(oldest)

        audio_np = np.concatenate(list(self._buffer)).astype(np.float32)

        # pyannote expects a waveform dict
        waveform = torch.from_numpy(audio_np).unsqueeze(0)  # (1, samples)
        input_dict = {
            "waveform": waveform,
            "sample_rate": self._settings.sample_rate,
        }

        diarization = self._pipeline(input_dict)

        segments: List[DiarizationSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizationSegment(
                    speaker_id=speaker,
                    start_ms=round(turn.start * 1000, 1),
                    end_ms=round(turn.end * 1000, 1),
                )
            )

        return segments

    def diarize_full(self, audio: np.ndarray) -> List[DiarizationSegment]:
        """
        Run diarization on the ENTIRE audio array at once.
        Use this for file uploads — gives globally consistent speaker labels
        across the whole recording (e.g. SPEAKER_00 always refers to the
        same person throughout).

        Do NOT use for live streaming (too slow / blocks).
        """
        if self._pipeline is None:
            raise RuntimeError("Diarizer not loaded. Call load() first.")

        audio_f32 = audio.astype(np.float32)
        waveform = torch.from_numpy(audio_f32).unsqueeze(0)  # (1, T)
        diarization = self._pipeline(
            {"waveform": waveform, "sample_rate": self._settings.sample_rate}
        )

        segments: List[DiarizationSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizationSegment(
                    speaker_id=speaker,
                    start_ms=round(turn.start * 1000, 1),
                    end_ms=round(turn.end * 1000, 1),
                )
            )

        return segments
