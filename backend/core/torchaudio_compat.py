"""
torchaudio_compat.py
─────────────────────
Restores torchaudio APIs removed in 2.x that pyannote 3.x still depends on.
Import this module BEFORE any pyannote import.
"""
from __future__ import annotations

import types
import torchaudio


# ── 1. AudioMetaData ──────────────────────────────────────────────────── #

class AudioMetaData:
    """Minimal reimplementation of torchaudio.AudioMetaData using soundfile."""
    def __init__(self, sample_rate: int, num_frames: int, num_channels: int,
                 bits_per_sample: int = 16, encoding: str = "PCM_S"):
        self.sample_rate = sample_rate
        self.num_frames = num_frames
        self.num_channels = num_channels
        self.bits_per_sample = bits_per_sample
        self.encoding = encoding


if not hasattr(torchaudio, "AudioMetaData"):
    torchaudio.AudioMetaData = AudioMetaData


# ── 2. torchaudio.info() ──────────────────────────────────────────────── #

def _info(path, backend=None):
    """Drop-in for torchaudio.info() backed by soundfile."""
    import soundfile as sf
    i = sf.info(str(path))
    return AudioMetaData(
        sample_rate=i.samplerate,
        num_frames=i.frames,
        num_channels=i.channels,
    )


if not hasattr(torchaudio, "info"):
    torchaudio.info = _info


# ── 3. list_audio_backends() ─────────────────────────────────────────── #

if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["soundfile"]


# ── 4. Also fix the already-patched pyannote io.py shim to return soundfile #
#    (already patched in io.py — this is a no-op if already present)      #

try:
    import pyannote.audio.core.io as _io  # noqa: F401 — triggers the module-level shim
except ImportError:
    pass
