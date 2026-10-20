"""
speaker_tracker.py
──────────────────
Lightweight, zero-latency speaker identification.

Replaces pyannote diarization for real-time use.  Instead of running a
full neural diarization pipeline (slow), we:

  1. Extract a 40-dim log-mel feature vector from each audio chunk in ~2ms.
  2. Compare it against known speaker centroids using cosine similarity.
  3. If a new voice is detected AND we haven't seen all N speakers yet,
     register it as a new speaker.
  4. Update the centroid using an online exponential moving average.

The user tells us how many speakers to expect (num_speakers).  This lets
us avoid false "new speaker" detections once all voices are registered.

No external ML dependencies — pure numpy.
"""

from __future__ import annotations

import threading
from typing import List

import numpy as np


class FastSpeakerTracker:
    """CPU-fast speaker tracking via log-mel cosine similarity."""

    # Similarity below which a chunk is treated as a new speaker.
    # Lower = more sensitive to speaker changes (good for single mic).
    _NEW_SPEAKER_THRESHOLD = 0.62

    # After this many samples a centroid is frozen — stops it drifting
    # into a "mixed voice" average that everything matches.
    _FREEZE_AFTER = 8

    # Sub-window size for selecting the clearest single-speaker segment (200ms)
    _SUBWIN_SAMPLES = 3200  # 200ms @ 16kHz

    # Minimum RMS to bother running speaker ID (skip silence/noise)
    _MIN_RMS = 0.005

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._num_speakers: int = 2
        self._centroids: List[np.ndarray] = []
        self._counts: List[int] = []
        self._frozen: List[bool] = []
        self._mel_cache: np.ndarray | None = None  # cached filterbank

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def reset(self, num_speakers: int = 2) -> None:
        with self._lock:
            self._num_speakers = max(1, min(8, num_speakers))
            self._centroids = []
            self._counts = []
            self._frozen = []

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def identify(self, audio: np.ndarray, sample_rate: int) -> str:
        """Return 'SPEAKER_00', 'SPEAKER_01', … for the given audio chunk."""
        # Skip near-silent chunks — they contaminate centroids
        rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        if rms < self._MIN_RMS:
            # Return last known speaker or SPEAKER_00 if none yet
            with self._lock:
                return f"SPEAKER_{len(self._centroids) - 1:02d}" if self._centroids else "SPEAKER_00"

        features = self._best_subwindow_features(audio, sample_rate)

        with self._lock:
            # No speakers registered yet → first speaker
            if not self._centroids:
                self._centroids.append(features.copy())
                self._counts.append(1)
                self._frozen.append(False)
                return "SPEAKER_00"

            # Cosine similarity to each known centroid
            sims = [self._cosine(features, c) for c in self._centroids]
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])

            # Looks like a new voice AND we still have room for more speakers
            if (best_sim < self._NEW_SPEAKER_THRESHOLD and
                    len(self._centroids) < self._num_speakers):
                idx = len(self._centroids)
                self._centroids.append(features.copy())
                self._counts.append(1)
                self._frozen.append(False)
                return f"SPEAKER_{idx:02d}"

            # Update centroid only while not frozen.
            # Freezing prevents centroid drift from mixed-voice chunks.
            if not self._frozen[best_idx]:
                n = self._counts[best_idx]
                self._centroids[best_idx] = (
                    (self._centroids[best_idx] * n + features) / (n + 1)
                )
                self._counts[best_idx] += 1
                if self._counts[best_idx] >= self._FREEZE_AFTER:
                    self._frozen[best_idx] = True
            return f"SPEAKER_{best_idx:02d}"

    def _best_subwindow_features(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Split audio into 200ms windows, return features of the highest-RMS one.

        The highest-RMS window is most likely dominated by a single voice,
        reducing the mixed-voice contamination problem on a single mic.
        """
        hop = self._SUBWIN_SAMPLES
        windows = [
            audio[i: i + hop]
            for i in range(0, len(audio) - hop // 2, hop)
            if len(audio[i: i + hop]) >= hop // 2
        ]
        if not windows:
            return self._extract(audio, sample_rate)

        # Pick the window with the highest RMS energy
        rms_values = [float(np.sqrt(np.mean(w.astype(np.float32) ** 2))) for w in windows]
        best_win = windows[int(np.argmax(rms_values))]
        return self._extract(best_win, sample_rate)

    # ------------------------------------------------------------------ #
    #  Feature extraction — MFCC + delta (39-dim)                        #
    # ------------------------------------------------------------------ #

    def _extract(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """39-dim MFCC + Δ + ΔΔ feature vector, L2-normalised.

        MFCC decorrelates log-mel via DCT and captures vocal tract shape.
        Deltas add temporal dynamics.  Together they separate speakers much
        better than raw log-mel alone (~0.4-0.7 between speakers vs 0.83+ for
        raw mel).
        """
        n_fft = 512
        hop = 160        # 10ms @ 16kHz
        n_mels = 40
        n_mfcc = 13      # keep C1-C13; drop C0 (energy, speaker-neutral)
        win = np.hanning(n_fft)

        audio = audio.astype(np.float32)
        if len(audio) < n_fft:
            audio = np.pad(audio, (0, n_fft - len(audio)))

        # STFT → magnitude spectrum per frame
        frames = []
        for start in range(0, len(audio) - n_fft, hop):
            frame = audio[start: start + n_fft] * win
            frames.append(np.abs(np.fft.rfft(frame)))

        if not frames:
            return np.zeros(n_mfcc * 3, dtype=np.float32)

        mag = np.array(frames, dtype=np.float32)  # (T, n_fft//2+1)

        # Mel filterbank
        fb = self._mel_filterbank(sr, n_fft, n_mels)
        log_mel = np.log(mag @ fb.T + 1e-8)  # (T, n_mels)

        # DCT → MFCCs  (keep C1..C13, skip C0)
        N = log_mel.shape[1]
        dct_matrix = np.cos(
            np.pi / N * np.outer(np.arange(1, n_mfcc + 1), np.arange(0.5, N))
        ).astype(np.float32)
        mfcc = log_mel @ dct_matrix.T  # (T, n_mfcc)

        # Mean over time → static features
        static = mfcc.mean(axis=0)  # (n_mfcc,)

        # Delta (first derivative via regression)
        delta = self._delta(mfcc).mean(axis=0)       # (n_mfcc,)
        delta2 = self._delta(self._delta(mfcc)).mean(axis=0)  # (n_mfcc,)

        feat = np.concatenate([static, delta, delta2]).astype(np.float32)

        # L2-normalise
        norm = float(np.linalg.norm(feat))
        return feat / (norm + 1e-8)

    @staticmethod
    def _delta(x: np.ndarray, width: int = 2) -> np.ndarray:
        """Compute delta (first derivative) features using regression."""
        T = x.shape[0]
        if T < 3:
            return np.zeros_like(x)
        denom = 2.0 * sum(k * k for k in range(1, width + 1))
        out = np.zeros_like(x)
        for t in range(T):
            for k in range(1, width + 1):
                t_plus = min(t + k, T - 1)
                t_minus = max(t - k, 0)
                out[t] += k * (x[t_plus] - x[t_minus])
        return out / denom

    def _mel_filterbank(self, sr: int, n_fft: int, n_mels: int) -> np.ndarray:
        """Build (or return cached) mel filterbank matrix."""
        if self._mel_cache is not None and self._mel_cache.shape[0] == n_mels:
            return self._mel_cache

        fmin, fmax = 80.0, float(sr) / 2.0
        mel_min = 2595.0 * np.log10(1.0 + fmin / 700.0)
        mel_max = 2595.0 * np.log10(1.0 + fmax / 700.0)
        mel_pts = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_pts = 700.0 * (10.0 ** (mel_pts / 2595.0) - 1.0)
        bins = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
        bins = np.clip(bins, 0, n_fft // 2)

        fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
        for m in range(1, n_mels + 1):
            lo, mid, hi = bins[m - 1], bins[m], bins[m + 1]
            if mid > lo:
                fb[m - 1, lo:mid] = (np.arange(lo, mid) - lo) / (mid - lo)
            if hi > mid:
                fb[m - 1, mid:hi] = (hi - np.arange(mid, hi)) / (hi - mid)

        self._mel_cache = fb
        return fb

    def diarize_full(
        self, audio: np.ndarray, sample_rate: int = 16_000, window_sec: float = 1.0
    ) -> list:
        """Slide a window over a full audio file and return DiarizationSegment list.

        Used by FileProcessor as a drop-in replacement for pyannote diarize_full.
        Returns a list of DiarizationSegment-compatible dicts (or dataclass instances
        if core.diarization is importable).
        """
        from core.diarization import DiarizationSegment  # lazy import — avoids circular dep

        self.reset(self._num_speakers)
        hop = int(window_sec * sample_rate)
        segments: list[DiarizationSegment] = []

        for start in range(0, len(audio), hop):
            chunk = audio[start: start + hop]
            if len(chunk) < hop // 4:
                break  # too short to be useful
            speaker_id = self.identify(chunk, sample_rate)
            start_ms = start / sample_rate * 1000.0
            end_ms = (start + len(chunk)) / sample_rate * 1000.0
            segments.append(DiarizationSegment(
                speaker_id=speaker_id,
                start_ms=start_ms,
                end_ms=end_ms,
            ))

        # Merge consecutive same-speaker windows into single segments
        if not segments:
            return []

        merged: list[DiarizationSegment] = []
        cur = segments[0]
        for seg in segments[1:]:
            if seg.speaker_id == cur.speaker_id:
                cur = DiarizationSegment(
                    speaker_id=cur.speaker_id,
                    start_ms=cur.start_ms,
                    end_ms=seg.end_ms,
                )
            else:
                merged.append(cur)
                cur = seg
        merged.append(cur)
        return merged

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # both are already L2-normalised
