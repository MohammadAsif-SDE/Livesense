"""
tests/test_pipeline.py
──────────────────────
Integration-level test: feeds a synthetic 512 ms audio buffer through
the full orchestrator pipeline using mocked ML components.  Validates
that a SpeakerEvent is emitted to the broadcast queue.
"""

import asyncio
import sys
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock, patch

import numpy as np
import pytest


def _make_stub(name: str) -> ModuleType:
    m = ModuleType(name)
    sys.modules.setdefault(name, m)
    return m


for pkg in [
    "torch", "whisper", "pyannote", "pyannote.audio",
    "sounddevice", "librosa", "transformers",
]:
    if pkg not in sys.modules:
        _make_stub(pkg)


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("HF_TOKEN", "tok")
    monkeypatch.setenv("FUSION_ALPHA", "0.6")
    monkeypatch.setenv("TRANSLATE_ENABLED", "false")
    from config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pipeline_emits_speaker_event():
    """Verify the orchestrator emits a SpeakerEvent for a non-silent chunk."""
    from core.diarization import DiarizationSegment
    from core.transcription import TranscriptionResult, TranscriptSegment
    from core.text_sentiment import EmotionResult
    from core.acoustic_sentiment import AcousticResult

    broadcast_q: asyncio.Queue = asyncio.Queue()

    with patch("pipeline.orchestrator.Diarizer") as MockDiarizer, \
         patch("pipeline.orchestrator.Transcriber") as MockTranscriber, \
         patch("pipeline.orchestrator.TextSentimentAnalyser") as MockText, \
         patch("pipeline.orchestrator.AcousticSentimentAnalyser") as MockAcoustic, \
         patch("pipeline.orchestrator.AudioIngestion"):

        # Configure mock returns
        mock_diarizer = MockDiarizer.return_value
        mock_diarizer.process.return_value = [
            DiarizationSegment("SPEAKER_00", 0.0, 500.0)
        ]

        mock_transcriber = MockTranscriber.return_value
        mock_transcriber.transcribe.return_value = TranscriptionResult(
            full_text="Hello world",
            language="en",
            segments=[TranscriptSegment("Hello world", "en", 0.0, 500.0)],
        )

        mock_text = MockText.return_value
        mock_text.analyse.return_value = EmotionResult(
            label="neutral", polarity="neutral", score=0.6,
            normalised_score=0.5, emotions={"neutral": 0.6},
        )

        mock_acoustic = MockAcoustic.return_value
        mock_acoustic.analyse.return_value = AcousticResult(
            prosodic_score=0.55, f0_mean=180.0, f0_std=8.0,
            energy_rms=0.03, speech_rate=0.10, mfcc_mean=[0.0] * 13,
        )

        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator(broadcast_q)
        orch._diarizer = mock_diarizer
        orch._transcriber = mock_transcriber
        orch._text_analyser = mock_text
        orch._acoustic_analyser = mock_acoustic

        loop = asyncio.get_running_loop()
        dummy_chunk = np.random.randn(8192).astype(np.float32) * 0.05

        await orch._process_chunk(dummy_chunk, loop)

        assert not broadcast_q.empty(), "Expected a SpeakerEvent in the broadcast queue"
        event = broadcast_q.get_nowait()
        assert event.speaker_id == "SPEAKER_00"
        assert event.transcript == "Hello world"
        assert event.polarity in ("positive", "negative", "neutral")
