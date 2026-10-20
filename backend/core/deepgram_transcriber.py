"""
deepgram_transcriber.py
───────────────────────
Real-time transcription + diarization via deepgram-sdk v7.x.

Uses AsyncDeepgramClient.listen.v1.connect() — the generated async client
whose API matches the official Python examples exactly.

Audio format sent to Deepgram: PCM signed int16, mono, 16 kHz.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# callback(transcript: str, speaker_id: str, language: str)
TranscriptCallback = Callable[[str, str, str], Awaitable[None]]


class DeepgramTranscriber:
    """Streams PCM audio to Deepgram and fires an async callback per final transcript."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._conn = None
        self._connect_task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._running = False
        self._callback: Optional[TranscriptCallback] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._language: str = "en"

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    async def start(
        self,
        callback: TranscriptCallback,
        language: str = "en",
        model: str = "nova-3",
        diarize: bool = True,
        endpointing: int = 300,
        punctuate: bool = True,
        smart_format: bool = True,
    ) -> None:
        """Open the Deepgram WebSocket using deepgram-sdk v7 async client."""
        try:
            from deepgram import AsyncDeepgramClient
            from deepgram.core.events import EventType
        except ImportError:
            raise RuntimeError(
                "deepgram-sdk not installed. Run: pip install deepgram-sdk"
            )

        self._callback = callback
        self._running = True
        self._language = language if language and language.lower() not in ("auto", "") else "en"
        self._loop = asyncio.get_running_loop()
        self._ready.clear()

        # Build keyword args — only pass what we need; the SDK is strict
        connect_kwargs: dict = {
            "model": model,
            "encoding": "linear16",
            "sample_rate": 16000,
            "channels": 1,
            "diarize": diarize,
            "punctuate": punctuate,
            "smart_format": smart_format,
            "interim_results": False,
        }
        if language and language.lower() not in ("auto", ""):
            connect_kwargs["language"] = language
        else:
            connect_kwargs["language"] = "en"  # Deepgram v7 requires a language value

        if endpointing > 0:
            connect_kwargs["endpointing"] = endpointing

        client = AsyncDeepgramClient(api_key=self._api_key)

        async def _connect_loop() -> None:
            try:
                async with client.listen.v1.connect(**connect_kwargs) as connection:
                    from deepgram.core.events import EventType as ET
                    connection.on(ET.MESSAGE, self._on_message_sync)
                    connection.on(ET.ERROR,   self._on_error_sync)
                    self._conn = connection
                    self._ready.set()
                    logger.info(
                        "Deepgram v7 connected — model=%s lang=%s diarize=%s endpointing=%s",
                        model, language, diarize, endpointing,
                    )
                    await connection.start_listening()
            except Exception as exc:
                if self._running:
                    logger.error("Deepgram connection dropped: %s", exc)
            finally:
                self._conn = None
                self._ready.clear()

        self._connect_task = asyncio.create_task(_connect_loop())

        # Wait up to 10 s for the WebSocket to open before returning
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            self._running = False
            if self._connect_task:
                self._connect_task.cancel()
            raise RuntimeError("Timed out waiting for Deepgram WebSocket to open")

    async def send_audio(self, chunk: np.ndarray) -> None:
        """Send a float32 audio chunk (16 kHz mono) to Deepgram as int16 PCM."""
        if not self._running or self._conn is None:
            return
        pcm = (np.clip(chunk.astype(np.float32), -1.0, 1.0) * 32767).astype(np.int16)
        try:
            await self._conn.send_media(pcm.tobytes())
        except Exception:
            pass

    async def stop(self) -> None:
        """Close the Deepgram connection."""
        self._running = False
        if self._conn:
            try:
                await self._conn.send_close_stream()
            except Exception:
                pass
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except (asyncio.CancelledError, Exception):
                pass
            self._connect_task = None
        self._conn = None
        logger.info("Deepgram connection closed.")

    # ------------------------------------------------------------------ #
    #  SDK event handlers (sync — called from SDK's internal thread)      #
    # ------------------------------------------------------------------ #

    def _on_message_sync(self, result, **kwargs) -> None:
        """Sync callback registered with the SDK; bridges to async handler.

        Splits each utterance into per-speaker runs so that a speaker
        transition mid-utterance creates two separate transcript entries
        instead of lumping everything under one dominant speaker.
        """
        if not self._running or self._callback is None or self._loop is None:
            return
        try:
            # result is a ListenV1Results pydantic model
            if result.type != "Results":
                return
            if not result.is_final:
                return

            channel = result.channel
            if not channel or not channel.alternatives:
                return

            best = channel.alternatives[0]
            if not (best.transcript or "").strip():
                return

            words = best.words or []

            # Split words into consecutive runs of the same speaker
            for speaker_id, run_words in _speaker_runs(words):
                text = " ".join(
                    getattr(w, "punctuated_word", None) or getattr(w, "word", "") or ""
                    for w in run_words
                ).strip()
                if not text:
                    continue
                asyncio.run_coroutine_threadsafe(
                    self._callback(text, speaker_id, self._language),
                    self._loop,
                )
        except Exception as exc:
            logger.warning("Error processing Deepgram message: %s", exc)

    def _on_error_sync(self, error, **kwargs) -> None:
        if self._running:
            logger.error("Deepgram error: %s", error)


# ── Helpers ────────────────────────────────────────────────────────────── #

def _speaker_runs(words: list) -> list[tuple[str, list]]:
    """Group consecutive words by speaker, returning [(speaker_id, words), ...]."""
    if not words:
        return [("SPEAKER_00", [])]
    runs: list[tuple[str, list]] = []
    current_spk: int = getattr(words[0], "speaker", None) or 0
    current_run: list = []
    for w in words:
        spk = getattr(w, "speaker", None)
        if spk is None:
            spk = current_spk
        if spk != current_spk:
            if current_run:
                runs.append((f"SPEAKER_{current_spk:02d}", current_run))
            current_spk = spk
            current_run = []
        current_run.append(w)
    if current_run:
        runs.append((f"SPEAKER_{current_spk:02d}", current_run))
    return runs


def _dominant_speaker(words: list) -> str:
    """Return the SPEAKER_XX label for the speaker with the most words."""
    if not words:
        return "SPEAKER_00"
    counts: dict[int, int] = {}
    for w in words:
        spk = getattr(w, "speaker", None)
        if spk is None:
            spk = 0
        counts[spk] = counts.get(spk, 0) + 1
    dominant = max(counts, key=lambda k: counts[k])
    return f"SPEAKER_{dominant:02d}"
