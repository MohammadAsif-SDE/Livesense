"""
audio_ingestion.py
──────────────────
Captures live microphone audio using sounddevice and pushes fixed-size
512 ms float32 chunks (at 16 kHz, mono) into an asyncio.Queue for the
pipeline orchestrator to consume.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd

from config.settings import get_settings

logger = logging.getLogger(__name__)


class AudioIngestion:
    """Streams microphone audio as fixed-size numpy chunks into a queue."""

    def __init__(self, queue: asyncio.Queue, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._settings = get_settings()
        self._queue = queue
        self._loop = loop or asyncio.get_event_loop()
        self._stream: Optional[sd.InputStream] = None
        self._buffer: deque[np.ndarray] = deque()
        self._buffer_samples = 0
        self._chunk_samples = self._settings.chunk_samples
        self._running = False

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Open the sounddevice stream and begin capturing."""
        if self._running:
            return
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self._settings.sample_rate,
            channels=self._settings.audio_channels,
            dtype="float32",
            blocksize=int(self._settings.sample_rate * 0.032),  # 32 ms hardware block
            callback=self._sd_callback,
        )
        self._stream.start()
        logger.info(
            "Audio ingestion started — sample_rate=%d  chunk_ms=%d",
            self._settings.sample_rate,
            self._settings.chunk_ms,
        )

    def stop(self) -> None:
        """Stop and close the audio stream."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Audio ingestion stopped.")

    # ------------------------------------------------------------------ #
    #  Private                                                             #
    # ------------------------------------------------------------------ #

    def _sd_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time,  # noqa: ANN001
        status: sd.CallbackFlags,
    ) -> None:
        """Called by sounddevice on every hardware block (32 ms)."""
        if status:
            logger.warning("sounddevice status: %s", status)

        # Flatten to 1-D mono
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()

        self._buffer.append(mono)
        self._buffer_samples += len(mono)

        # Emit chunks whenever we have accumulated enough samples
        while self._buffer_samples >= self._chunk_samples:
            chunk = self._drain_chunk()
            # Thread-safe enqueue into the asyncio event loop
            asyncio.run_coroutine_threadsafe(self._enqueue(chunk), self._loop)

    async def _enqueue(self, chunk: np.ndarray) -> None:
        await self._queue.put(chunk)

    def _drain_chunk(self) -> np.ndarray:
        """Drain exactly chunk_samples from the internal buffer."""
        collected: list[np.ndarray] = []
        needed = self._chunk_samples

        while needed > 0 and self._buffer:
            piece = self._buffer[0]
            if len(piece) <= needed:
                collected.append(piece)
                needed -= len(piece)
                self._buffer_samples -= len(piece)
                self._buffer.popleft()
            else:
                collected.append(piece[:needed])
                self._buffer[0] = piece[needed:]
                self._buffer_samples -= needed
                needed = 0

        return np.concatenate(collected)
