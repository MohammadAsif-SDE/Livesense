"""
text_sentiment.py
─────────────────
Fine-grained emotion classification from transcript text using
j-hartmann/emotion-english-distilroberta-base (7 classes):
  anger, disgust, fear, joy, neutral, sadness, surprise

Returns a normalised SentimentScore with a coarse polarity label
(positive / negative / neutral) alongside per-emotion probabilities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)

MODEL_ID = "j-hartmann/emotion-english-distilroberta-base"

# Emotion → polarity mapping
_POSITIVE_EMOTIONS = {"joy", "surprise"}
_NEGATIVE_EMOTIONS = {"anger", "disgust", "fear", "sadness"}


@dataclass
class EmotionResult:
    label: str                          # dominant emotion
    polarity: str                       # positive | negative | neutral
    score: float                        # confidence of dominant emotion [0,1]
    normalised_score: float             # sentiment score mapped to [0,1]
    emotions: Dict[str, float]          # all 7 emotion probabilities


class TextSentimentAnalyser:
    """Wraps the distilroberta emotion classifier."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pipeline = None

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """Load the classifier.  Call once at startup."""
        from transformers import pipeline as hf_pipeline

        device_id = 0 if self._settings.resolved_device == "cuda" else -1
        logger.info("Loading text sentiment model %s …", MODEL_ID)
        self._pipeline = hf_pipeline(
            "text-classification",
            model=MODEL_ID,
            top_k=None,          # return all 7 emotion scores
            device=device_id,
            truncation=True,
            max_length=512,
        )
        logger.info("Text sentiment model ready.")

    # ------------------------------------------------------------------ #
    #  Processing                                                          #
    # ------------------------------------------------------------------ #

    def analyse(self, text: str) -> Optional[EmotionResult]:
        """
        Classify emotions in text.

        Args:
            text: Transcript string (any length; truncated to 512 tokens).

        Returns:
            EmotionResult or None if text is empty.
        """
        if self._pipeline is None:
            raise RuntimeError("TextSentimentAnalyser not loaded. Call load() first.")

        text = text.strip()
        if not text:
            return None

        raw: list[list[dict]] = self._pipeline(text)
        # top_k=None returns [[{label, score}, …]]
        scores_list: list[dict] = raw[0] if isinstance(raw[0], list) else raw

        emotions: Dict[str, float] = {
            item["label"].lower(): round(item["score"], 4) for item in scores_list
        }

        dominant = max(emotions, key=lambda k: emotions[k])
        dominant_score = emotions[dominant]

        polarity = self._polarity(dominant)
        normalised = self._to_normalised(emotions)

        return EmotionResult(
            label=dominant,
            polarity=polarity,
            score=dominant_score,
            normalised_score=normalised,
            emotions=emotions,
        )

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _polarity(dominant: str) -> str:
        if dominant in _POSITIVE_EMOTIONS:
            return "positive"
        if dominant in _NEGATIVE_EMOTIONS:
            return "negative"
        return "neutral"

    @staticmethod
    def _to_normalised(emotions: Dict[str, float]) -> float:
        """
        Map emotion probabilities to a [0, 1] sentiment score where:
          1.0 = purely positive  |  0.5 = neutral  |  0.0 = purely negative
        """
        positive = sum(emotions.get(e, 0.0) for e in _POSITIVE_EMOTIONS)
        negative = sum(emotions.get(e, 0.0) for e in _NEGATIVE_EMOTIONS)
        neutral = emotions.get("neutral", 0.0)
        total = positive + negative + neutral or 1.0
        # Weighted centre: pos→1, neutral→0.5, neg→0
        score = (positive * 1.0 + neutral * 0.5 + negative * 0.0) / total
        return round(score, 4)
