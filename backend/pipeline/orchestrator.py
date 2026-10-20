"""
orchestrator.py
───────────────
asyncio pipeline coordinator.

Two live modes — chosen per-session via `use_deepgram` flag:

  Deepgram mode (default):
    Audio → Deepgram WS → transcript + speaker callback
    → sentiment → broadcast  (~300-500 ms latency)

  Local mode (faster-whisper + FastSpeakerTracker):
    Audio → drain queue → Whisper transcription (executor)
    → FastSpeakerTracker → sentiment → broadcast  (~1-2 s latency)

File uploads always use the local path via FileProcessor.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np

from config.settings import get_settings
from core.acoustic_sentiment import AcousticSentimentAnalyser
from core.audio_ingestion import AudioIngestion
from core.deepgram_transcriber import DeepgramTranscriber
from core.fusion import FusionEngine
from core.speaker_tracker import FastSpeakerTracker
from core.text_sentiment import TextSentimentAnalyser
from core.transcription import Transcriber
from api.schemas import SpeakerEvent

logger = logging.getLogger(__name__)

_EXECUTOR_WORKERS = 2


class PipelineOrchestrator:
    def __init__(self, broadcast_queue: asyncio.Queue) -> None:
        self._settings = get_settings()
        self._broadcast_queue = broadcast_queue
        self._audio_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=128)

        self._deepgram: Optional[DeepgramTranscriber] = None
        self._last_chunk: Optional[np.ndarray] = None

        self._text_analyser = TextSentimentAnalyser()
        self._acoustic_analyser = AcousticSentimentAnalyser()
        self._fusion = FusionEngine()
        self._transcriber = Transcriber()        # local Whisper (also used for file uploads)
        self._speaker_tracker = FastSpeakerTracker()  # local speaker ID

        self._ingestion = AudioIngestion(self._audio_queue)

        self._executor: Optional[ThreadPoolExecutor] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._session_id: Optional[str] = None
        self._event_counter: int = 0
        self._session_gen: int = 0

        self._dg_language: str = "en"
        self._dg_model: str = "nova-3"
        self._dg_diarize: bool = True
        self._dg_endpointing: int = 300
        self._dg_punctuate: bool = True
        self._use_deepgram: bool = True   # False = local Whisper path

        # Live audio recording
        self._audio_chunks: list[np.ndarray] = []
        self._audio_file_path: Optional[str] = None

    def load_models(self) -> None:
        logger.info("Loading ML models …")
        self._transcriber.load()   # faster-whisper
        self._text_analyser.load()
        logger.info("All models loaded.")

    async def start(
        self,
        source_lang: str = "en",
        deepgram_model: str = "nova-3",
        diarize: bool = True,
        endpointing: int = 300,
        punctuate: bool = True,
        use_deepgram: bool = True,
        created_by: Optional[str] = None,
    ) -> None:
        if self._running:
            return

        self._executor = ThreadPoolExecutor(max_workers=_EXECUTOR_WORKERS)
        self._running = True
        self._event_counter = 0
        self._session_gen += 1
        self._last_chunk = None
        self._audio_chunks = []
        self._audio_file_path = None

        self._dg_language = source_lang or "en"
        self._dg_model = deepgram_model
        self._dg_diarize = diarize
        self._dg_endpointing = endpointing
        self._dg_punctuate = punctuate
        self._use_deepgram = use_deepgram

        my_gen = self._session_gen

        # ── Reset local-mode components (used even in Deepgram mode as fallback) ─
        self._transcriber.reset()
        self._speaker_tracker.reset(8)

        if use_deepgram:
            async def _on_transcript(transcript: str, speaker_id: str, language: str) -> None:
                if self._session_gen != my_gen or not self._running:
                    return
                await self._handle_transcript(transcript, speaker_id, language)

            api_key = self._settings.deepgram_api_key
            if not api_key:
                logger.error("DEEPGRAM_API_KEY not set — falling back to local Whisper.")
                self._use_deepgram = False
            else:
                self._deepgram = DeepgramTranscriber(api_key)
                try:
                    await self._deepgram.start(
                        callback=_on_transcript,
                        language=self._dg_language,
                        model=self._dg_model,
                        diarize=self._dg_diarize,
                        endpointing=self._dg_endpointing,
                        punctuate=self._dg_punctuate,
                    )
                except Exception as exc:
                    logger.error("Failed to connect to Deepgram: %s — falling back to local.", exc)
                    self._deepgram = None
                    self._use_deepgram = False

        if not self._use_deepgram:
            logger.info("Pipeline starting in LOCAL mode (faster-whisper + FastSpeakerTracker)")

        try:
            import uuid as _uuid
            from db.connection import get_db
            from db.models import SessionDocument, SessionType, SessionStatus
            from db import repositories as repo
            self._session_id = str(_uuid.uuid4())
            db = get_db()
            await repo.create_session(db, SessionDocument(
                session_id=self._session_id,
                type=SessionType.LIVE,
                status=SessionStatus.PROCESSING,
                created_by=created_by,
            ))
        except Exception:
            self._session_id = None

        loop = asyncio.get_running_loop()
        self._ingestion._loop = loop
        self._ingestion.start()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Pipeline started — mode=%s model=%s lang=%s diarize=%s",
            "deepgram" if self._use_deepgram else "local",
            deepgram_model if self._use_deepgram else self._settings.whisper_model,
            source_lang, diarize,
        )

    async def stop(self) -> None:
        self._running = False
        self._ingestion.stop()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._deepgram:
            await self._deepgram.stop()
            self._deepgram = None

        if self._executor:
            self._executor.shutdown(wait=False)
        self._executor = None

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._session_id:
            try:
                from db.connection import get_db
                from db import repositories as repo
                db = get_db()

                # ── Save recorded audio to WAV ─────────────────────────
                saved_path: Optional[str] = None
                if self._audio_chunks:
                    try:
                        import scipy.io.wavfile as wavfile
                        from pathlib import Path
                        audio_np = np.concatenate(self._audio_chunks, axis=0)
                        if audio_np.ndim > 1:
                            audio_np = audio_np[:, 0]  # take first channel
                        pcm16 = (audio_np * 32767).clip(-32768, 32767).astype(np.int16)
                        upload_dir = Path(self._settings.upload_dir)
                        upload_dir.mkdir(parents=True, exist_ok=True)
                        wav_path = upload_dir / f"{self._session_id}_live.wav"
                        wavfile.write(str(wav_path), self._settings.sample_rate, pcm16)
                        saved_path = str(wav_path)
                        logger.info("Live audio saved: %s", wav_path)
                    except Exception as exc:
                        logger.warning("Failed to save live audio: %s", exc)

                summary = await repo.build_session_summary(db, self._session_id)
                await repo.finalize_session(db, self._session_id, summary, audio_path=saved_path)
            except Exception:
                pass
            self._audio_chunks = []
            self._audio_file_path = None
            self._session_id = None

        logger.info("Pipeline stopped.")

    async def _run_loop(self) -> None:
        """Route audio to Deepgram or process locally, depending on mode."""
        if self._use_deepgram:
            await self._run_loop_deepgram()
        else:
            await self._run_loop_local()

    async def _run_loop_deepgram(self) -> None:
        """Stream raw PCM chunks to Deepgram; results arrive via callback."""
        while self._running:
            try:
                chunk: np.ndarray = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            self._last_chunk = chunk
            self._audio_chunks.append(chunk.copy())
            if self._deepgram and self._running:
                await self._deepgram.send_audio(chunk)

    async def _run_loop_local(self) -> None:
        """Drain audio, transcribe with Whisper, identify speaker, broadcast."""
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                chunk: np.ndarray = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            # Drain up to 1s of additional chunks for better context
            chunks = [chunk]
            drained = len(chunk)
            max_samples = int(1.0 * self._settings.sample_rate)
            while not self._audio_queue.empty() and drained < max_samples:
                try:
                    c = self._audio_queue.get_nowait()
                    chunks.append(c)
                    drained += len(c)
                except asyncio.QueueEmpty:
                    break

            combined = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
            self._last_chunk = combined
            self._audio_chunks.append(combined.copy())
            my_gen = self._session_gen

            if not self._running or self._executor is None:
                return

            try:
                transcript = await loop.run_in_executor(
                    self._executor,
                    self._transcriber.transcribe,
                    combined,
                    self._dg_language if self._dg_language != "auto" else None,
                )

                if self._session_gen != my_gen or not self._running:
                    return
                if not transcript.full_text:
                    continue

                speaker_id = self._speaker_tracker.identify(
                    combined, self._settings.sample_rate
                )

                await self._handle_transcript(
                    transcript.full_text, speaker_id, transcript.language or self._dg_language
                )
            except Exception as exc:
                logger.exception("Local pipeline error: %s", exc)

    async def _handle_transcript(self, transcript: str, speaker_id: str, language: str) -> None:
        if not self._running or self._executor is None:
            return

        loop = asyncio.get_running_loop()
        chunk = self._last_chunk if self._last_chunk is not None else np.zeros(512, dtype=np.float32)

        try:
            text_future = loop.run_in_executor(self._executor, self._text_analyser.analyse, transcript)
            acoustic_future = loop.run_in_executor(self._executor, self._acoustic_analyser.analyse, chunk)
            text_result, acoustic_result = await asyncio.gather(text_future, acoustic_future)

            if not self._running:
                return

            fused = self._fusion.fuse(text_result, acoustic_result)

            event = SpeakerEvent(
                speaker_id=speaker_id,
                transcript=transcript,
                language=language,
                polarity=fused.polarity,
                final_score=fused.final_score,
                text_score=fused.text_score,
                acoustic_score=fused.acoustic_score,
                dominant_emotion=fused.dominant_emotion,
                emotions=fused.emotions or {},
                confidence=fused.confidence,
            )
            await self._broadcast_queue.put(event)

            if self._session_id:
                try:
                    from db.connection import get_db
                    from db.models import EventDocument
                    from db import repositories as repo
                    db = get_db()
                    ev_doc = EventDocument(
                        session_id=self._session_id,
                        event_index=self._event_counter,
                        speaker_id=speaker_id,
                        transcript=transcript,
                        language=language,
                        polarity=fused.polarity,
                        final_score=fused.final_score,
                        text_score=fused.text_score,
                        acoustic_score=fused.acoustic_score,
                        dominant_emotion=fused.dominant_emotion,
                        emotions=fused.emotions or {},
                        confidence=fused.confidence,
                    )
                    await repo.insert_event(db, ev_doc)
                    await repo.upsert_speaker_stats(
                        db,
                        session_id=self._session_id,
                        speaker_id=speaker_id,
                        transcript=transcript,
                        polarity=fused.polarity,
                        final_score=fused.final_score,
                        dominant_emotion=fused.dominant_emotion,
                        emotions=fused.emotions or {},
                        language=language,
                        offset_seconds=0.0,
                    )
                    self._event_counter += 1
                except Exception:
                    pass

        except Exception as exc:
            logger.exception("Error in transcript handler: %s", exc)
