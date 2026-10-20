"""
fusion.py
─────────
Late-fusion engine that combines text-based and acoustic-based sentiment
scores into a single authoritative sentiment result.

Formula:
    final_score = α * text_score + (1 - α) * acoustic_score

where α (FUSION_ALPHA) defaults to 0.6 and is configurable via .env.

final_score ∈ [0, 1]:
    ≥ 0.65 → positive
    ≤ 0.40 → negative
    else   → neutral
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from config.settings import get_settings
from core.acoustic_sentiment import AcousticResult
from core.text_sentiment import EmotionResult


@dataclass
class FusedSentiment:
    polarity: str                       # positive | negative | neutral
    final_score: float                  # blended [0, 1]
    text_score: Optional[float]         # text channel contribution
    acoustic_score: Optional[float]     # acoustic channel contribution
    dominant_emotion: Optional[str]     # from text channel
    emotions: Optional[Dict[str, float]] # per-emotion probabilities
    confidence: float                   # certainty estimate [0, 1]


# Polarity thresholds
_POSITIVE_THRESHOLD = 0.65
_NEGATIVE_THRESHOLD = 0.40


class FusionEngine:
    """Weighted late-fusion of text and acoustic sentiment channels."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def fuse(
        self,
        text_result: Optional[EmotionResult],
        acoustic_result: Optional[AcousticResult],
    ) -> FusedSentiment:
        """
        Combine text and acoustic sentiment into a single output.

        Falls back gracefully when one channel is unavailable.
        """
        alpha = self._settings.fusion_alpha

        text_score: Optional[float] = None
        acoustic_score: Optional[float] = None
        dominant_emotion: Optional[str] = None
        emotions: Optional[Dict[str, float]] = None

        if text_result is not None:
            text_score = text_result.normalised_score
            dominant_emotion = text_result.label
            emotions = text_result.emotions

        if acoustic_result is not None:
            acoustic_score = acoustic_result.prosodic_score

        # Blend according to what is available
        if text_score is not None and acoustic_score is not None:
            final_score = alpha * text_score + (1.0 - alpha) * acoustic_score
            confidence = 0.7 + 0.3 * min(text_result.score if text_result else 0.5, 1.0)
        elif text_score is not None:
            final_score = text_score
            confidence = 0.6 * (text_result.score if text_result else 0.5)
        elif acoustic_score is not None:
            final_score = acoustic_score
            confidence = 0.4  # acoustic-only is less reliable
        else:
            # No signal — default to neutral midpoint
            final_score = 0.5
            confidence = 0.0

        polarity = self._score_to_polarity(final_score)

        return FusedSentiment(
            polarity=polarity,
            final_score=round(final_score, 4),
            text_score=round(text_score, 4) if text_score is not None else None,
            acoustic_score=round(acoustic_score, 4) if acoustic_score is not None else None,
            dominant_emotion=dominant_emotion,
            emotions=emotions,
            confidence=round(confidence, 4),
        )

    @staticmethod
    def _score_to_polarity(score: float) -> str:
        if score >= _POSITIVE_THRESHOLD:
            return "positive"
        if score <= _NEGATIVE_THRESHOLD:
            return "negative"
        return "neutral"
