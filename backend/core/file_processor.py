"""
core/file_processor.py
──────────────────────
Processes uploaded audio files through the full LiveSense pipeline and
saves all results to MongoDB.

Strategy for files (vs live streaming):
  1. Load full audio into memory.
  2. Run pyannote diarization on the ENTIRE file → globally consistent
     SPEAKER_00 / SPEAKER_01 labels across the whole recording.
  3. Run faster-whisper on the ENTIRE file with word_timestamps=True.
  4. Align each word to the speaker who was speaking at that moment.
  5. Group consecutive words by speaker into utterance events.
  6. Run text + acoustic sentiment on each utterance.
  7. Persist to MongoDB.

This avoids the per-window speaker-ID reassignment problem of the live
rolling-buffer approach.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import numpy as np

from config.settings import get_settings
from db.connection import get_db
from db.models import EventDocument, SessionStatus, UploadStatus
from db import repositories as repo
from core.diarization import Diarizer, DiarizationSegment

logger = logging.getLogger(__name__)

_EXECUTOR_WORKERS = 2
# Merge utterance fragments shorter than this into neighbours
_MIN_UTTERANCE_SEC = 0.5


def _load_audio(path: str, target_sr: int = 16_000) -> np.ndarray:
    """
    Load any audio file and resample to mono float32 at target_sr.
    Uses soundfile for wav/flac/ogg; pydub for mp3/m4a (needs ffmpeg).
    """
    suffix = Path(path).suffix.lower()

    if suffix in (".mp3", ".m4a", ".aac", ".mp4"):
        from pydub import AudioSegment
        audio = AudioSegment.from_file(path)
        audio = audio.set_channels(1).set_frame_rate(target_sr)
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        # pydub returns int16-range values
        samples /= 2 ** 15
        return samples

    import soundfile as sf
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != target_sr:
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
    return data


# ──────────────────────────────────────────────────────────────────────────────
# Alignment helpers
# ──────────────────────────────────────────────────────────────────────────────

def _speaker_at(diar_segments: List[DiarizationSegment], t: float) -> Optional[str]:
    """Return the speaker who was speaking at time t (seconds), or None if silence."""
    for seg in diar_segments:
        if seg.start_ms / 1000.0 <= t <= seg.end_ms / 1000.0:
            return seg.speaker_id
    return None


def _align_words_to_speakers(
    diar_segments: List[DiarizationSegment],
    transcript_segments,
) -> List[dict]:
    """
    For every word in the transcript, find which speaker was speaking
    at the word's midpoint.  Returns a flat list of:
        {"word": str, "start": float, "end": float, "speaker": str}
    """
    aligned = []
    for seg in transcript_segments:
        words = getattr(seg, "words", None) or []
        if not words:
            # No word timestamps — fall back to segment midpoint
            mid = (seg.start_ms / 1000.0 + seg.end_ms / 1000.0) / 2.0
            speaker = _speaker_at(diar_segments, mid) or "SPEAKER_00"
            aligned.append({
                "word": seg.text,
                "start": seg.start_ms / 1000.0,
                "end": seg.end_ms / 1000.0,
                "speaker": speaker,
            })
        else:
            for w in words:
                mid = (w["start"] + w["end"]) / 2.0
                speaker = _speaker_at(diar_segments, mid) or "SPEAKER_00"
                aligned.append({
                    "word": w["word"],
                    "start": w["start"],
                    "end": w["end"],
                    "speaker": speaker,
                })
    return aligned


def _group_words_into_utterances(
    aligned_words: List[dict],
    min_utterance_sec: float = _MIN_UTTERANCE_SEC,
) -> List[dict]:
    """
    Merge consecutive words with the same speaker into utterances.
    Returns list of:
        {"speaker": str, "text": str, "start": float, "end": float}
    """
    if not aligned_words:
        return []

    utterances = []
    cur_speaker = aligned_words[0]["speaker"]
    cur_words = [aligned_words[0]]

    for w in aligned_words[1:]:
        if w["speaker"] == cur_speaker:
            cur_words.append(w)
        else:
            # flush
            text = " ".join(x["word"].strip() for x in cur_words).strip()
            duration = cur_words[-1]["end"] - cur_words[0]["start"]
            if text and duration >= min_utterance_sec:
                utterances.append({
                    "speaker": cur_speaker,
                    "text": text,
                    "start": cur_words[0]["start"],
                    "end": cur_words[-1]["end"],
                })
            cur_speaker = w["speaker"]
            cur_words = [w]

    # flush last group
    if cur_words:
        text = " ".join(x["word"].strip() for x in cur_words).strip()
        duration = cur_words[-1]["end"] - cur_words[0]["start"]
        if text and duration >= min_utterance_sec:
            utterances.append({
                "speaker": cur_speaker,
                "text": text,
                "start": cur_words[0]["start"],
                "end": cur_words[-1]["end"],
            })

    return utterances


# ──────────────────────────────────────────────────────────────────────────────
# FileProcessor
# ──────────────────────────────────────────────────────────────────────────────

class FileProcessor:
    """
    Processes an uploaded audio file through the ML pipeline and persists
    all results to MongoDB.

    Usage:
        processor = FileProcessor(orchestrator)
        await processor.process(session_id, file_path)
    """

    def __init__(self, orchestrator) -> None:
        self._orc = orchestrator
        self._settings = get_settings()
        self._executor = ThreadPoolExecutor(max_workers=_EXECUTOR_WORKERS)
        self._diarizer = Diarizer()   # pyannote — loaded lazily on first use

    async def process(self, session_id: str, file_path: str) -> None:
        """
        Full-file processing pipeline.

        Step 1 — Load audio (full file in memory).
        Step 2 — Diarize entire file → globally consistent speaker timeline.
        Step 3 — Transcribe entire file with word timestamps.
        Step 4 — Align words to speakers, group into utterances.
        Step 5 — Run sentiment on each utterance, persist to MongoDB.
        """
        db = get_db()
        loop = asyncio.get_running_loop()

        try:
            await repo.update_session_status(db, session_id, SessionStatus.PROCESSING)
            await repo.update_upload_status(db, session_id, UploadStatus.PROCESSING)

            # ── Step 1: Load ───────────────────────────────────────────
            logger.info("[%s] Loading audio from %s …", session_id, file_path)
            audio = await loop.run_in_executor(
                self._executor, _load_audio, file_path, self._settings.sample_rate
            )
            total_seconds = len(audio) / self._settings.sample_rate
            logger.info("[%s] Audio loaded: %.1fs", session_id, total_seconds)

            # ── Step 2 & 3: Diarize + Transcribe full file in parallel ─
            logger.info("[%s] Diarizing and transcribing full file …", session_id)
            # Lazy-load pyannote on first use (not loaded at server startup)
            if self._diarizer._pipeline is None:
                logger.info("[%s] Loading pyannote diarizer …", session_id)
                await loop.run_in_executor(self._executor, self._diarizer.load)
            diar_future = loop.run_in_executor(
                self._executor,
                self._diarizer.diarize_full,
                audio,
            )
            trans_future = loop.run_in_executor(
                self._executor, self._orc._transcriber.transcribe_full, audio, None
            )
            diar_segments, transcript = await asyncio.gather(diar_future, trans_future)

            logger.info(
                "[%s] Diarization: %d turns. Transcript: %d segments.",
                session_id, len(diar_segments), len(transcript.segments)
            )

            if not transcript.segments:
                raise ValueError("No speech detected in audio file.")

            # ── Step 4: Align words → speakers → utterances ────────────
            aligned = _align_words_to_speakers(diar_segments, transcript.segments)
            utterances = _group_words_into_utterances(aligned)
            logger.info("[%s] Grouped into %d utterances.", session_id, len(utterances))

            if not utterances:
                raise ValueError("No utterances produced after alignment.")

            # ── Step 5: Sentiment + persist ────────────────────────────
            for idx, utt in enumerate(utterances):
                text = utt["text"]
                speaker_id = utt["speaker"]
                start_sec = utt["start"]
                end_sec = utt["end"]
                chunk_dur = end_sec - start_sec

                # Slice the audio chunk for acoustic analysis
                start_sample = int(start_sec * self._settings.sample_rate)
                end_sample = int(end_sec * self._settings.sample_rate)
                chunk = audio[start_sample:end_sample]
                if len(chunk) == 0:
                    continue

                text_future = loop.run_in_executor(
                    self._executor, self._orc._text_analyser.analyse, text
                )
                acoustic_future = loop.run_in_executor(
                    self._executor, self._orc._acoustic_analyser.analyse, chunk
                )
                text_result, acoustic_result = await asyncio.gather(text_future, acoustic_future)

                fused = self._orc._fusion.fuse(text_result, acoustic_result)

                event = EventDocument(
                    session_id=session_id,
                    event_index=idx,
                    offset_seconds=round(start_sec, 3),
                    speaker_id=speaker_id,
                    transcript=text,
                    language=transcript.language,
                    polarity=fused.polarity,
                    final_score=fused.final_score,
                    text_score=fused.text_score,
                    acoustic_score=fused.acoustic_score,
                    dominant_emotion=fused.dominant_emotion,
                    emotions=fused.emotions or {},
                    confidence=fused.confidence,
                )
                await repo.insert_event(db, event)

                await repo.upsert_speaker_stats(
                    db,
                    session_id=session_id,
                    speaker_id=speaker_id,
                    transcript=text,
                    polarity=fused.polarity,
                    final_score=fused.final_score,
                    dominant_emotion=fused.dominant_emotion,
                    emotions=fused.emotions or {},
                    language=transcript.language,
                    offset_seconds=round(start_sec, 3),
                    chunk_duration=chunk_dur,
                )

                logger.debug("[%s] Utterance %d saved (speaker=%s, %.1fs–%.1fs)", session_id, idx, speaker_id, start_sec, end_sec)

            # ── Finalize ───────────────────────────────────────────────
            summary = await repo.build_session_summary(db, session_id)
            summary.total_duration_seconds = round(total_seconds, 2)
            await repo.finalize_session(db, session_id, summary)
            await repo.update_upload_status(db, session_id, UploadStatus.COMPLETED)
            logger.info(
                "[%s] Processing complete — %d utterances, %d speakers",
                session_id, len(utterances), summary.speaker_count
            )

        except Exception as exc:
            logger.exception("[%s] Processing failed: %s", session_id, exc)
            await repo.update_session_status(db, session_id, SessionStatus.FAILED, error=str(exc))
            await repo.update_upload_status(db, session_id, UploadStatus.FAILED, error=str(exc))

