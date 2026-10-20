# LiveSense — Setup & Running Guide

---

## 1. Prerequisites

### Tools (already installed on your Mac)

| Tool | Required Version | Verify |
|---|---|---|
| Python 3 | 3.10+ | `python3 --version` |
| Node.js | 18 LTS+ | `node --version` |
| npm | 8+ | `npm --version` |

### HuggingFace Account (free, required for pyannote)

1. Sign up at **https://huggingface.co** (free)
2. Accept the diarization model terms at **https://hf.co/pyannote/speaker-diarization-3.1**  
   → click **"Agree and access repository"**
3. Create an access token at **https://hf.co/settings/tokens**  
   → click **"New token"** → copy the value (starts with `hf_...`)

---

## 2. Project Structure

```
livesense/
├── Makefile                    ← all run commands live here
├── README.md
├── GUIDE.md                    ← you are here
│
├── backend/                    ← Python / FastAPI / ML
│   ├── .env                    ← your config (set HF_TOKEN here)
│   ├── .env.example            ← template
│   ├── requirements.txt        ← Python dependencies
│   ├── pytest.ini
│   ├── tests/
│   │   ├── test_sentiment.py
│   │   └── test_pipeline.py
│   ├── api/
│   │   ├── main.py             ← FastAPI app entry point
│   │   ├── websocket.py        ← WebSocket broadcaster
│   │   └── schemas.py          ← Pydantic data models
│   ├── config/
│   │   └── settings.py         ← reads from .env
│   ├── core/
│   │   ├── audio_ingestion.py  ← microphone capture (512 ms chunks)
│   │   ├── diarization.py      ← pyannote speaker labelling
│   │   ├── transcription.py    ← Whisper ASR
│   │   ├── translation.py      ← Helsinki-NLP MarianMT
│   │   ├── text_sentiment.py   ← distilroberta emotion classifier
│   │   ├── acoustic_sentiment.py ← librosa MFCC / F0 / energy
│   │   └── fusion.py           ← late-fusion engine
│   └── pipeline/
│       └── orchestrator.py     ← asyncio coordinator
│
└── frontend/                   ← React / Vite / TypeScript
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── App.tsx
        ├── index.css
        ├── types/index.ts
        ├── store/liveStore.ts          ← Zustand state
        ├── hooks/useWebSocket.ts       ← auto-reconnecting WS
        └── components/
            ├── ControlBar.tsx          ← Start / Stop button
            ├── SpeakerTimeline.tsx     ← per-speaker bars
            ├── SentimentChart.tsx      ← Recharts line chart
            └── TranscriptPanel.tsx     ← live scrolling transcript
```

---

## 3. Configuration

Open `backend/.env` and set your HuggingFace token:

```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx   ← paste your token here
```

All other values have safe defaults:

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | *(required)* | HuggingFace token for pyannote |
| `WHISPER_MODEL` | `small` | ASR model size: `tiny` / `base` / `small` / `medium` |
| `DEVICE` | `auto` | `auto` detects MPS (Apple Silicon) or CPU |
| `FUSION_ALPHA` | `0.6` | Text channel weight in fusion (0.0 – 1.0) |
| `TRANSLATE_ENABLED` | `false` | Set `true` to enable translation overlay |
| `TARGET_LANG` | `en` | Translation target language |
| `CHUNK_MS` | `512` | Audio chunk size in milliseconds |

---

## 4. One-Time Setup

Run once from the `livesense/` folder. This creates the Python virtual environment and installs all packages:

```bash
cd /Users/entrans/Purple/Live/livesense
make setup
```

This runs:
1. `python3 -m venv backend/.venv` — creates isolated Python environment
2. `pip install -r backend/requirements.txt` — installs PyTorch, Whisper, pyannote, FastAPI, Librosa, etc.
3. `npm install` in `frontend/` — installs React, Vite, Recharts, Zustand, Tailwind

> **Already done on your machine** — skip this if `backend/.venv/` exists.

---

## 5. Running the Project

You need **two terminals open at the same time**, both from the `livesense/` folder.

---

### Terminal 1 — Backend

```bash
cd /Users/entrans/Purple/Live/livesense
make run-backend
```

**What happens:**
- Starts the FastAPI server at `http://localhost:8000`
- Loads all ML models into memory (Whisper, pyannote, distilroberta)
- Opens a WebSocket endpoint at `ws://localhost:8000/ws`

**First run only:** downloads ~900 MB of model weights automatically:

| Model | Size |
|---|---|
| `pyannote/speaker-diarization-3.1` | ~100 MB |
| `openai/whisper-small` | ~244 MB |
| `j-hartmann/emotion-english-distilroberta-base` | ~330 MB |

Models are cached in `~/.cache/huggingface/` and never downloaded again.

**Wait for this message before opening the dashboard:**

```
INFO — All models loaded. Server is up.
```

---

### Terminal 2 — Frontend

```bash
cd /Users/entrans/Purple/Live/livesense
make run-frontend
```

Web Login
Username : admin
Password : admin123

**What happens:**
- Starts the Vite dev server at `http://localhost:5173`
- Ready in under 1 second

---

## 6. Using the Dashboard

1. Open **http://localhost:5173** in your browser
2. The top-right shows a **green dot** when connected to the backend
3. Click **Start** — microphone capture begins
4. Speak (or conduct a conversation) — results appear within ~2–3 seconds:

| Panel | What it shows |
|---|---|
| **Speaker Sentiment** | Horizontal bar per detected speaker, colour-coded with current sentiment score |
| **Sentiment Over Time** | Real-time line chart — one line per speaker across the session |
| **Live Transcript** | Auto-scrolling utterances, coloured by polarity (green = positive, red = negative) |

5. Toggle **Translation** checkbox in the transcript panel to switch between original and translated text
6. Click **Stop** to end recording
7. Click **Clear** to reset all panels

---

## 7. How the Pipeline Works

```
Microphone
    │
    ▼  512 ms audio chunks (16 kHz, mono)
┌───────────────────────────────────────────────────┐
│                  Orchestrator                     │
│                                                   │
│  ┌─────────────┐    ┌─────────────────────────┐  │
│  │  pyannote   │    │   Whisper (small)        │  │
│  │  Diarizer   │    │   Transcription          │  │
│  │ (who spoke) │    │ (what was said)          │  │
│  └──────┬──────┘    └────────────┬────────────┘  │
│         │                        │                │
│         │           ┌────────────┴────────────┐   │
│         │           │       (parallel)        │   │
│         │    ┌──────┴───────┐  ┌─────────────┐│  │
│         │    │ distilroberta│  │   Librosa   ││  │
│         │    │ text emotion │  │  acoustics  ││  │
│         │    └──────┬───────┘  └──────┬──────┘│  │
│         │           └────────┬─────────┘       │  │
│         │                    ▼                 │  │
│         │           ┌─────────────────┐        │  │
│         │           │  Fusion Engine  │        │  │
│         │           │ α·text+(1-α)·ac │        │  │
│         │           └────────┬────────┘        │  │
│         └──────────────────► │                 │  │
│                    SpeakerEvent (JSON)          │  │
└───────────────────────────────────────────────────┘
                        │
                        ▼
              FastAPI WebSocket /ws
                        │
                        ▼
            React Dashboard (port 5173)
```

**Fusion formula:**

$$\text{score} = \alpha \cdot \text{text\_score} + (1 - \alpha) \cdot \text{acoustic\_score}$$

| Score range | Polarity |
|---|---|
| ≥ 0.65 | Positive |
| 0.41 – 0.64 | Neutral |
| ≤ 0.40 | Negative |

---

## 8. Running Tests

```bash
cd /Users/entrans/Purple/Live/livesense
make test
```

Tests use mocked ML models so they run instantly without GPU or downloads.

---

## 9. All Make Commands

| Command | What it does |
|---|---|
| `make setup` | Install Python venv + npm packages |
| `make run-backend` | Start FastAPI server on port 8000 |
| `make run-frontend` | Start Vite dev server on port 5173 |
| `make test` | Run pytest test suite |
| `make lint` | Lint Python (ruff) + TypeScript (eslint) |
| `make clean` | Delete venv, node_modules, build output |

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `make: python3.11: No such file or directory` | Fixed — Makefile now uses `python3` |
| `vite: command not found` | Run `cd frontend && npm install` |
| `HF_TOKEN not set` | Edit `backend/.env`, set your token |
| Backend loads slowly on first run | Normal — downloading ~900 MB of models once |
| Transcript appears with ~3 s delay | Normal for Whisper `small` on CPU. Use `WHISPER_MODEL=base` for faster (less accurate) results |
| No speakers detected | Speak clearly at 16 kHz; increase `CHUNK_MS=1000` in `.env` for longer context |
| Translation not showing | Set `TRANSLATE_ENABLED=true` in `.env` and restart backend |

