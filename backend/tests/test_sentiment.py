"""
tests/test_sentiment.py
────────────────────────
Unit tests for text sentiment and fusion engine using mock data.
No models are loaded — all ML dependencies are mocked.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Stub out heavy dependencies before any imports ──────────────────── #

def _make_stub(name: str) -> ModuleType:
    m = ModuleType(name)
    sys.modules[name] = m
    return m


for pkg in [
    "torch", "whisper", "pyannote", "pyannote.audio",
    "sounddevice", "librosa", "transformers",
]:
    if pkg not in sys.modules:
        _make_stub(pkg)


# Patch settings to use CPU and no HF token
@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("HF_TOKEN", "test_token")
    monkeypatch.setenv("FUSION_ALPHA", "0.6")
    monkeypatch.setenv("TRANSLATE_ENABLED", "false")
    # Reset lru_cache so env vars take effect
    from config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── TextSentimentAnalyser ─────────────────────────────────────────────── #

class TestTextSentimentAnalyser:
    def _make_analyser_with_mock_pipeline(self, fake_output):
        from core.text_sentiment import TextSentimentAnalyser
        analyser = TextSentimentAnalyser()
        mock_pipe = MagicMock(return_value=[fake_output])
        analyser._pipeline = mock_pipe
        return analyser

    def test_analyse_positive(self):
        fake_output = [
            {"label": "joy", "score": 0.80},
            {"label": "neutral", "score": 0.10},
            {"label": "anger", "score": 0.05},
            {"label": "sadness", "score": 0.02},
            {"label": "fear", "score": 0.01},
            {"label": "disgust", "score": 0.01},
            {"label": "surprise", "score": 0.01},
        ]
        analyser = self._make_analyser_with_mock_pipeline(fake_output)
        result = analyser.analyse("I am so happy today!")
        assert result is not None
        assert result.label == "joy"
        assert result.polarity == "positive"
        assert result.normalised_score > 0.5

    def test_analyse_negative(self):
        fake_output = [
            {"label": "anger", "score": 0.75},
            {"label": "neutral", "score": 0.10},
            {"label": "joy", "score": 0.05},
            {"label": "sadness", "score": 0.05},
            {"label": "fear", "score": 0.03},
            {"label": "disgust", "score": 0.01},
            {"label": "surprise", "score": 0.01},
        ]
        analyser = self._make_analyser_with_mock_pipeline(fake_output)
        result = analyser.analyse("I am furious!")
        assert result is not None
        assert result.polarity == "negative"
        assert result.normalised_score < 0.5

    def test_analyse_empty_text_returns_none(self):
        from core.text_sentiment import TextSentimentAnalyser
        analyser = TextSentimentAnalyser()
        analyser._pipeline = MagicMock()
        assert analyser.analyse("   ") is None
        analyser._pipeline.assert_not_called()

    def test_not_loaded_raises(self):
        from core.text_sentiment import TextSentimentAnalyser
        analyser = TextSentimentAnalyser()
        with pytest.raises(RuntimeError, match="not loaded"):
            analyser.analyse("hello")


# ── FusionEngine ─────────────────────────────────────────────────────── #

class TestFusionEngine:
    def setup_method(self):
        from core.fusion import FusionEngine
        self.engine = FusionEngine()

    def test_both_channels_positive(self):
        from core.text_sentiment import EmotionResult
        from core.acoustic_sentiment import AcousticResult

        text = EmotionResult(
            label="joy", polarity="positive", score=0.85,
            normalised_score=0.85,
            emotions={"joy": 0.85, "neutral": 0.10, "anger": 0.05},
        )
        acoustic = AcousticResult(
            prosodic_score=0.75, f0_mean=220.0, f0_std=10.0,
            energy_rms=0.05, speech_rate=0.12,
            mfcc_mean=[0.0] * 13,
        )
        result = self.engine.fuse(text, acoustic)
        assert result.polarity == "positive"
        assert result.final_score > 0.65

    def test_text_only(self):
        from core.text_sentiment import EmotionResult

        text = EmotionResult(
            label="sadness", polarity="negative", score=0.70,
            normalised_score=0.20,
            emotions={"sadness": 0.70, "neutral": 0.20, "joy": 0.10},
        )
        result = self.engine.fuse(text, None)
        assert result.polarity == "negative"
        assert result.acoustic_score is None

    def test_no_signal_returns_neutral_midpoint(self):
        result = self.engine.fuse(None, None)
        assert result.final_score == 0.5
        assert result.confidence == 0.0
        assert result.polarity == "neutral"

    def test_alpha_weighting(self):
        """With α=0.6, text should dominate the final score."""
        from config.settings import get_settings
        from core.text_sentiment import EmotionResult
        from core.acoustic_sentiment import AcousticResult

        alpha = get_settings().fusion_alpha  # 0.6 from env

        text_score = 0.9
        acoustic_score = 0.2

        text = EmotionResult(
            label="joy", polarity="positive", score=0.9,
            normalised_score=text_score,
            emotions={"joy": 0.9},
        )
        acoustic = AcousticResult(
            prosodic_score=acoustic_score, f0_mean=200.0, f0_std=5.0,
            energy_rms=0.04, speech_rate=0.10, mfcc_mean=[0.0] * 13,
        )
        result = self.engine.fuse(text, acoustic)
        expected = alpha * text_score + (1 - alpha) * acoustic_score
        assert abs(result.final_score - expected) < 0.001


# ── AcousticSentimentAnalyser ─────────────────────────────────────────── #

class TestAcousticSentimentAnalyser:
    def test_silent_chunk_returns_none(self):
        with patch("librosa.feature.mfcc"), patch("librosa.yin"), \
             patch("librosa.feature.zero_crossing_rate"):
            from core.acoustic_sentiment import AcousticSentimentAnalyser
            analyser = AcousticSentimentAnalyser()
            silent = np.zeros(8000, dtype=np.float32)
            assert analyser.analyse(silent) is None

    def test_too_short_returns_none(self):
        from core.acoustic_sentiment import AcousticSentimentAnalyser
        analyser = AcousticSentimentAnalyser()
        assert analyser.analyse(np.zeros(100, dtype=np.float32)) is None

    def test_score_in_valid_range(self):
        import librosa as _librosa

        dummy_audio = np.random.randn(16000).astype(np.float32) * 0.1

        with patch.object(_librosa.feature, "mfcc", return_value=np.zeros((13, 50))), \
             patch.object(_librosa, "yin", return_value=np.full(50, 150.0)), \
             patch.object(_librosa.feature, "zero_crossing_rate", return_value=np.full((1, 50), 0.08)):
            from core.acoustic_sentiment import AcousticSentimentAnalyser
            analyser = AcousticSentimentAnalyser()
            result = analyser.analyse(dummy_audio)
            assert result is not None
            assert 0.0 <= result.prosodic_score <= 1.0
