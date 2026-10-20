"""
acoustic_sentiment.py
─────────────────────
Extracts prosodic / acoustic features from raw audio using librosa and
combines them into a normalised sentiment score [0, 1].

Features extracted:
  • MFCC (13 coefficients) — speaker style / vocal quality
  • Fundamental frequency / F0 (via librosa.yin) — pitch contour
  • RMS energy — loudness / arousal
  • Speech rate — syllable density proxy (zero-crossing rate)

The features are normalised against empirically derived population
statistics and combined into a final prosodic score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from config.settings import get_settings

logger = logging.getLogger(__name__)

# Population normalisation constants (rough empirical values for 16 kHz speech)
_F0_MIN = 75.0
_F0_MAX = 400.0
_ENERGY_FLOOR = 1e-6


@dataclass
class AcousticResult:
    prosodic_score: float           # normalised [0,1]; higher = more aroused/positive
    f0_mean: float                  # mean fundamental frequency (Hz)
    f0_std: float                   # F0 standard deviation
    energy_rms: float               # RMS energy
    speech_rate: float              # zero-crossing rate (normalised)
    mfcc_mean: list[float]          # 13-dim MFCC mean vector


class AcousticSentimentAnalyser:
    """Librosa-based acoustic feature extraction and prosodic scoring."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def analyse(self, audio: np.ndarray) -> Optional[AcousticResult]:
        """
        Extract acoustic features and compute a prosodic sentiment score.

        Args:
            audio: 1-D float32 numpy array at 16 kHz.

        Returns:
            AcousticResult or None if the chunk is silent / too short.
        """
        import librosa

        if len(audio) < 512:
            return None

        sr = self._settings.sample_rate

        # ── RMS energy ──────────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < _ENERGY_FLOOR:
            return None  # silence

        # ── MFCC ────────────────────────────────────────────────────────
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        mfcc_mean = mfcc.mean(axis=1).tolist()

        # ── Fundamental Frequency (F0) ───────────────────────────────────
        f0 = librosa.yin(
            audio,
            fmin=_F0_MIN,
            fmax=_F0_MAX,
            sr=sr,
            frame_length=512,
            hop_length=128,
        )
        # Remove unvoiced frames (librosa.yin returns _F0_MIN for unvoiced)
        voiced_f0 = f0[f0 > _F0_MIN + 1]
        f0_mean = float(voiced_f0.mean()) if len(voiced_f0) > 0 else 0.0
        f0_std = float(voiced_f0.std()) if len(voiced_f0) > 0 else 0.0

        # ── Speech rate proxy (zero-crossing rate) ───────────────────────
        zcr = librosa.feature.zero_crossing_rate(audio, hop_length=128)
        speech_rate = float(zcr.mean())

        # ── Prosodic sentiment score ─────────────────────────────────────
        prosodic_score = self._compute_prosodic_score(
            f0_mean=f0_mean,
            rms=rms,
            speech_rate=speech_rate,
        )

        return AcousticResult(
            prosodic_score=prosodic_score,
            f0_mean=round(f0_mean, 2),
            f0_std=round(f0_std, 2),
            energy_rms=round(rms, 6),
            speech_rate=round(speech_rate, 4),
            mfcc_mean=[round(v, 3) for v in mfcc_mean],
        )

    # ------------------------------------------------------------------ #
    #  Scoring                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_prosodic_score(
        f0_mean: float,
        rms: float,
        speech_rate: float,
    ) -> float:
        """
        Combine prosodic features into a single [0, 1] sentiment score.

        Higher pitch + higher energy + faster rate → more aroused (→ closer to 1).
        Very low energy, flat pitch → neutral/negative (→ closer to 0.5 or below).

        This is intentionally a lightweight heuristic; the fusion engine
        combines it with the text-based score.
        """
        # Normalise F0: map [_F0_MIN, _F0_MAX] → [0, 1]
        f0_norm = np.clip((f0_mean - _F0_MIN) / (_F0_MAX - _F0_MIN), 0.0, 1.0)

        # Normalise energy (log scale, approximate range)
        energy_norm = np.clip(np.log1p(rms * 1000) / np.log1p(1000), 0.0, 1.0)

        # Normalise speech rate (typical ZCR range 0.01–0.25)
        rate_norm = np.clip(speech_rate / 0.25, 0.0, 1.0)

        # Weighted combination: F0 most indicative, then energy, then rate
        score = 0.45 * f0_norm + 0.35 * energy_norm + 0.20 * rate_norm

        # Map [0,1] arousal to [0.2, 0.85] — avoid extreme ends from acoustics alone
        score = 0.2 + score * 0.65

        return round(float(score), 4)
