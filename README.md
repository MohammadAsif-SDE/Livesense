# LiveSense

Real-time speaker diarization and multimodal sentiment analysis — fully offline, open-source.

```
Mic → pyannote diarization → Whisper ASR → RoBERTa (text) + Librosa (acoustic)
    → Late-fusion → FastAPI WebSocket → React dashboard
```

---

## Prerequisites

| | |
|---|---|
| Python | 3.11 |
| Node.js | 20 LTS |
| HuggingFace account | Free token required for pyannote |

### Get a free HuggingFace token

1. Create a free account at <https://huggingface.co>
2. Accept the pyannote model terms at <https://hf.co/pyannote/speaker-diarization-3.1>
3. Generate a token at <https://hf.co/settings/tokens>

---

## Quick Start

```bash
# 1. Clone / open the project
cd livesense

# 2. Copy env template and set your token
cp backend/.env.example backend/.env
# Edit backend/.env — set HF_TOKEN=hf_your_token_here

# 3. Install everything
make setup

# 4. In terminal 1 — start the backend
make run-backend

# 5. In terminal 2 — start the frontend
make run-frontend

# 6. Open http://localhost:5173 and click Start
```

First run downloads ~900 MB of model weights (Whisper small, pyannote, distilroberta).  
Subsequent runs load from cache instantly.

---

## Project Structure

```
livesense/
├── backend/
│   ├── .env.example          ← copy to .env and set HF_TOKEN
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── tests/
│   │   ├── test_sentiment.py
│   │   └── test_pipeline.py
│   │   ├── websocket.py      ConnectionManager + broadcaster task
│   │   └── schemas.py        Pydantic SpeakerEvent model
│   ├── core/
│   │   ├── audio_ingestion.py   sounddevice → asyncio.Queue (512 ms chunks)
│   │   ├── diarization.py       pyannote.audio sliding 5 s buffer
│   │   ├── transcription.py     Whisper small ASR
│   │   ├── translation.py       Helsinki-NLP MarianMT (lazy, cached)
│   │   ├── text_sentiment.py    distilroberta 7-class emotion
│   │   ├── acoustic_sentiment.py  librosa MFCC/F0/energy/ZCR
│   │   └── fusion.py            α·text + (1-α)·acoustic
│   ├── config/settings.py    pydantic-settings (.env driven)
│   ├── pipeline/orchestrator.py  asyncio coordinator
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ControlBar.tsx       Start/Stop + connection status
│       │   ├── SpeakerTimeline.tsx  Per-speaker sentiment bars
│       │   ├── SentimentChart.tsx   Recharts line chart
│       │   └── TranscriptPanel.tsx  Live scrolling transcript
│       ├── hooks/useWebSocket.ts    Auto-reconnecting WS client
│       ├── store/liveStore.ts       Zustand state
│       └── types/index.ts
├── tests/
│   ├── test_sentiment.py     Unit tests (mocked models)
│   └── test_pipeline.py      Integration test (mocked ML, real asyncio)
├── .env.example
├── Makefile
└── pytest.ini
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | *(required)* | Set in `backend/.env` |
| `WHISPER_MODEL` | `small` | `tiny` / `base` / `small` / `medium` |
| `DEVICE` | `auto` | `auto` / `cpu` / `mps` / `cuda` |
| `FUSION_ALPHA` | `0.6` | Text weight in fusion (0–1) |
| `TRANSLATE_ENABLED` | `false` | Enable MarianMT translation |
| `TARGET_LANG` | `en` | Translation target language |
| `CHUNK_MS` | `512` | Audio chunk size in milliseconds |

---

## Running Tests

```bash
make test
```

---

## Sentiment Score Interpretation

| Score | Polarity |
|---|---|
| ≥ 0.65 | Positive |
| 0.41 – 0.64 | Neutral |
| ≤ 0.40 | Negative |

The final score is a weighted blend:

$$\text{score} = \alpha \cdot \text{text\_score} + (1-\alpha) \cdot \text{acoustic\_score}$$

Default α = 0.6 (text-dominant), configurable via `FUSION_ALPHA`.

---

## Models Used

| Model | Source | Size |
|---|---|---|
| `pyannote/speaker-diarization-3.1` | HuggingFace | ~100 MB |
| `openai/whisper-small` | HuggingFace | ~244 MB |
| `j-hartmann/emotion-english-distilroberta-base` | HuggingFace | ~330 MB |
| `Helsinki-NLP/opus-mt-{src}-en` | HuggingFace | ~300 MB/pair |

All models are downloaded once and cached in `~/.cache/huggingface/`.
