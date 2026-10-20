"""
transcription.py
────────────────
Wraps faster-whisper for offline ASR.  faster-whisper is thread-safe,
4× faster than openai-whisper on CPU, and uses the same model weights.

Buffering: Whisper works on ~30s windows. We accumulate audio in a
rolling buffer (TARGET_BUFFER_SEC) and transcribe the full buffer
each call, returning only the new text since the last call.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

import numpy as np

from config.settings import get_settings

logger = logging.getLogger(__name__)

# Minimum audio before first Whisper inference.
# 1.2s gives near-instant first word on known languages.
TARGET_BUFFER_SEC = 1.2


@dataclass
class TranscriptSegment:
    text: str
    language: str
    start_ms: float
    end_ms: float
    words: List[dict] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    full_text: str
    language: str
    segments: List[TranscriptSegment]


# Segments whose end is within this many ms of the buffer tail are
# still "in flight" (being spoken) — don't emit yet.
_STABILITY_MS = 100.0

# Grace margin for Whisper timestamp jitter across consecutive calls.
_COMMIT_TOLERANCE_MS = 300.0

# Maximum recently-emitted texts kept for exact-text deduplication.
_DEDUP_HISTORY = 20


def _norm(text: str) -> str:
    """Normalise text for deduplication: lowercase, strip punctuation, collapse whitespace."""
    text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text.strip().lower())


def _norm_words(text: str) -> list[str]:
    """Return a list of normalised words (no punctuation)."""
    return _norm(text).split()


class Transcriber:
    """faster-whisper ASR with a rolling audio buffer for stability."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None
        self._lock = threading.Lock()
        self._buffer: List[np.ndarray] = []
        self._buffer_samples = 0
        self._min_samples = int(TARGET_BUFFER_SEC * self._settings.sample_rate)
        # Total samples ever appended (monotonically increasing).
        # Used to convert buffer-relative Whisper timestamps → absolute
        # session timestamps so we never re-emit the same speech.
        self._total_samples_appended: int = 0
        self._committed_end_ms: float = 0.0  # absolute ms emitted so far
        # Ring-buffer of normalized texts we've already emitted.  Exact-text
        # duplicates are rejected even if their timestamps differ (Whisper jitter).
        self._recent_texts: Deque[str] = deque(maxlen=_DEDUP_HISTORY)

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Clear rolling buffer and committed cursor — call before a new live session."""
        self._buffer.clear()
        self._buffer_samples = 0
        self._total_samples_appended = 0
        self._committed_end_ms = 0.0
        self._recent_texts.clear()

    def load(self) -> None:
        """Load faster-whisper model. Call once at startup."""
        from faster_whisper import WhisperModel

        device = self._settings.resolved_device
        # faster-whisper uses "cpu" or "cuda"; MPS falls back to cpu
        fw_device = "cuda" if device == "cuda" else "cpu"
        compute_type = "int8"  # best for CPU; float16 for GPU

        model_name = self._settings.whisper_model
        logger.info("Loading faster-whisper '%s' on %s …", model_name, fw_device)
        self._model = WhisperModel(
            model_name,
            device=fw_device,
            compute_type=compute_type,
        )
        logger.info("Whisper model ready.")

    # ------------------------------------------------------------------ #
    #  Processing                                                          #
    # ------------------------------------------------------------------ #

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe a float32 audio chunk (16 kHz, mono).

        Internally buffers audio into a rolling window.  Crucially, segment
        timestamps are converted to *absolute* session time so that each
        speech segment is emitted exactly once, regardless of how many times
        the same audio appears in the rolling buffer.
        """
        if self._model is None:
            raise RuntimeError("Transcriber not loaded. Call load() first.")

        sr = self._settings.sample_rate
        max_samples = int(8.0 * sr)

        # Accumulate total samples (monotonic — never decremented).
        self._total_samples_appended += len(audio)

        # Rolling buffer: keep the last 8 seconds.
        self._buffer.append(audio)
        self._buffer_samples += len(audio)
        while self._buffer_samples > max_samples:
            oldest = self._buffer.pop(0)
            self._buffer_samples -= len(oldest)

        # Don't transcribe until we have enough audio.
        if self._buffer_samples < self._min_samples:
            return TranscriptionResult(full_text="", language="en", segments=[])

        # Absolute start/end of the current buffer (in ms).
        buffer_start_ms = (self._total_samples_appended - self._buffer_samples) / sr * 1000.0
        buffer_end_ms   = self._total_samples_appended / sr * 1000.0

        audio_buf = np.concatenate(self._buffer).astype(np.float32)
        peak = np.abs(audio_buf).max()
        if peak > 1.0:
            audio_buf /= peak

        # ── Background noise suppression ──────────────────────────────
        # Use non-stationary mode so retroflex consonants in Tamil/Indian languages
        # are not misclassified as stationary noise and scrubbed out.
        # Only apply if the audio is noisy (peak after normalisation is high-variance).
        try:
            import noisereduce as nr
            if np.std(audio_buf) > 0.02:  # skip on near-silent or clean audio
                audio_buf = nr.reduce_noise(
                    y=audio_buf,
                    sr=sr,
                    stationary=False,    # non-stationary: safe for Tamil phonemes
                    prop_decrease=0.4,   # light reduction — preserve consonants
                )
        except Exception:  # noqa: BLE001
            pass  # noisereduce unavailable or failed — proceed with raw audio

        lang_hint = language if language and language != "auto" else None

        with self._lock:
            segments_iter, info = self._model.transcribe(
                audio_buf,
                language=lang_hint,
                beam_size=3,
                temperature=0,                  # deterministic first pass
                vad_filter=False,               # disabled — VAD was destroying Tamil speech
                condition_on_previous_text=True,   # Tamil needs inter-word context
                no_speech_threshold=0.3,           # very permissive — keep Tamil words
                compression_ratio_threshold=2.4,
            )
            raw_segments = list(segments_iter)

        if not raw_segments:
            return TranscriptionResult(full_text="", language=info.language, segments=[])

        # Convert buffer-relative timestamps → absolute session timestamps
        # and filter to only NEW, STABLE segments.
        new_segments: List[TranscriptSegment] = []
        for seg in raw_segments:
            if not seg.text.strip():
                continue
            abs_start = buffer_start_ms + seg.start * 1000.0
            abs_end   = buffer_start_ms + seg.end   * 1000.0

            # Skip segments we've already committed (with tolerance for
            # Whisper's timestamp jitter across consecutive calls).
            if abs_end <= self._committed_end_ms + _COMMIT_TOLERANCE_MS:
                continue

            # Skip segments whose end is still inside the "in-flight" tail —
            # Whisper may not have finalised them yet.
            if abs_end > buffer_end_ms - _STABILITY_MS:
                continue

            # Text-based deduplication: exact match → skip entirely.
            normalized = _norm(seg.text)
            if normalized in self._recent_texts:
                continue

            # Prefix-extension deduplication: Whisper sometimes expands a
            # previously committed chunk into a longer segment that STARTS with
            # the old text followed by new words (e.g. a speaker continued
            # without a pause).  Strip the already-emitted prefix so we only
            # emit the genuinely new tail.
            # Use word-by-word comparison so punctuation differences don't matter.
            emit_text = seg.text.strip()
            new_words_norm = _norm_words(seg.text)
            for prev_norm in self._recent_texts:
                prev_words_norm = prev_norm.split()
                n = len(prev_words_norm)
                if (len(new_words_norm) > n and
                        new_words_norm[:n] == prev_words_norm):
                    # Skip the matched prefix words in the *original* text
                    tail_words = seg.text.split()[n:]
                    emit_text = ' '.join(tail_words)
                    break  # apply at most one prefix strip

            if not emit_text.strip():
                continue

            new_segments.append(TranscriptSegment(
                text=emit_text.strip(),
                language=info.language,
                start_ms=round(abs_start, 1),
                end_ms=round(abs_end, 1),
            ))

        if not new_segments:
            return TranscriptionResult(full_text="", language=info.language, segments=[])

        # Advance committed cursor to the end of the last new segment.
        self._committed_end_ms = max(s.end_ms for s in new_segments)

        # Register the full original normalized text of each raw segment so
        # future calls can detect both exact duplicates and prefix extensions.
        for seg in raw_segments:
            n = _norm(seg.text)
            if n and n not in self._recent_texts:
                self._recent_texts.append(n)

        full_text = " ".join(s.text for s in new_segments)
        return TranscriptionResult(
            full_text=full_text,
            language=info.language,
            segments=new_segments,
        )

    def transcribe_full(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe an entire audio array in one shot WITH word-level timestamps.
        Use this for file uploads — bypasses the rolling buffer completely.
        Each returned segment has a `words` list with per-word (start, end, text).
        """
        if self._model is None:
            raise RuntimeError("Transcriber not loaded. Call load() first.")

        audio_f32 = audio.astype(np.float32)
        peak = np.abs(audio_f32).max()
        if peak > 1.0:
            audio_f32 /= peak

        lang_hint = language if language and language != "auto" else None

        with self._lock:
            segments_iter, info = self._model.transcribe(
                audio_f32,
                language=lang_hint,
                beam_size=3,
                word_timestamps=True,     # critical for alignment
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 200},
            )
            raw_segments = list(segments_iter)

        if not raw_segments:
            return TranscriptionResult(full_text="", language="en", segments=[])

        segments = []
        for seg in raw_segments:
            words = []
            if seg.words:
                words = [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in seg.words
                ]
            if seg.text.strip():
                segments.append(TranscriptSegment(
                    text=seg.text.strip(),
                    language=info.language,
                    start_ms=round(seg.start * 1000, 1),
                    end_ms=round(seg.end * 1000, 1),
                    words=words,
                ))

        return TranscriptionResult(
            full_text=" ".join(s.text for s in segments),
            language=info.language,
            segments=segments,
        )

