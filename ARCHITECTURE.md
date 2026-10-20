# LiveSense — Architecture & Technical Reference

> Real-time speaker diarization · multimodal sentiment analysis · live + file upload processing

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Layout](#2-repository-layout)
3. [Environment Configuration](#3-environment-configuration)
4. [End-to-End Request Flows](#4-end-to-end-request-flows)
   - 4.1 [Live Session — Deepgram Path](#41-live-session--deepgram-path)
   - 4.2 [Live Session — Local Whisper Path](#42-live-session--local-whisper-path)
   - 4.3 [File Upload Path](#43-file-upload-path)
   - 4.4 [WebSocket Connection Lifecycle](#44-websocket-connection-lifecycle)
   - 4.5 [REST API Request Flow](#45-rest-api-request-flow)
5. [Component Interaction Diagram](#5-component-interaction-diagram)
6. [Backend Module Reference](#6-backend-module-reference)
   - 6.1 [API Layer](#61-api-layer)
   - 6.2 [Pipeline Orchestrator](#62-pipeline-orchestrator)
   - 6.3 [Core Processing Modules](#63-core-processing-modules)
7. [Database Design](#7-database-design)
   - 7.1 [Collections Overview](#71-collections-overview)
   - 7.2 [sessions](#72-sessions-collection)
   - 7.3 [events](#73-events-collection)
   - 7.4 [speakers](#74-speakers-collection)
   - 7.5 [uploads](#75-uploads-collection)
   - 7.6 [Indexes](#76-indexes)
8. [REST API Contract](#8-rest-api-contract)
9. [WebSocket Protocol](#9-websocket-protocol)
10. [Frontend Architecture](#10-frontend-architecture)
    - 10.1 [Component Tree](#101-component-tree)
    - 10.2 [Zustand Store Schema](#102-zustand-store-schema)
    - 10.3 [Vite Proxy Map](#103-vite-proxy-map)
11. [Sentiment Pipeline Detail](#11-sentiment-pipeline-detail)
12. [Data Flow State Machine](#12-data-flow-state-machine)

---

## 1. System Overview

LiveSense is a full-stack application that captures microphone audio (or processes uploaded files), transcribes speech with speaker diarization, and performs real-time multimodal sentiment analysis. Results are streamed to a React dashboard over WebSocket.

```
┌─────────────────────────────────────────────────────────┐
│                     React Dashboard                      │
│  ControlBar · TranscriptPanel · SpeakerTimeline          │
│  SentimentChart · UploadPage · SessionsPage              │
└──────────┬─────────────────────────┬────────────────────┘
           │  REST /api/*            │  WebSocket /ws
           ▼                         ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend :8000                  │
│  POST /start  POST /stop  GET /status                    │
│  POST /api/uploads  GET /api/sessions/**                 │
├─────────────────────────────────────────────────────────┤
│              Pipeline Orchestrator                       │
│  ┌─────────────┐   ┌──────────────────────────────────┐ │
│  │AudioIngestion│  │     Deepgram WebSocket            │ │
│  │(sounddevice) │  │  AsyncDeepgramClient · nova-3     │ │
│  └──────┬───────┘  └──────────────┬───────────────────┘ │
│         │ float32 PCM              │ final transcript    │
│         └──────────┬───────────────┘                    │
│                    ▼                                     │
│      ┌─────────────────────────────┐                    │
│      │  TextSentimentAnalyser      │                    │
│      │  AcousticSentimentAnalyser  │  (parallel)        │
│      │  FusionEngine               │                    │
│      └────────────┬────────────────┘                    │
│                   ▼                                      │
│         SpeakerEvent → broadcast_queue                   │
├─────────────────────────────────────────────────────────┤
│              MongoDB (Motor async driver)                │
│  sessions · events · speakers · uploads                  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Repository Layout

```
livesense/
├── backend/
│   ├── .env                    # secrets + runtime config
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── api/
│   │   ├── main.py             # FastAPI app factory, endpoints, lifespan
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── websocket.py        # ConnectionManager, broadcaster task
│   │   └── uploads.py          # file upload + session REST endpoints
│   ├── config/
│   │   └── settings.py         # pydantic-settings, .env binding, lru_cache
│   ├── core/
│   │   ├── audio_ingestion.py  # sounddevice stream → async queue
│   │   ├── deepgram_transcriber.py  # AsyncDeepgramClient wrapper
│   │   ├── transcription.py    # faster-whisper, rolling buffer, dedup
│   │   ├── speaker_tracker.py  # MFCC cosine live speaker ID
│   │   ├── diarization.py      # pyannote full-file diarization
│   │   ├── file_processor.py   # upload processing pipeline
│   │   ├── text_sentiment.py   # distilroberta emotion classifier
│   │   ├── acoustic_sentiment.py  # prosody / F0 / energy
│   │   ├── fusion.py           # weighted score fusion
│   │   ├── translation.py      # optional translation
│   │   └── torchaudio_compat.py
│   ├── db/
│   │   ├── connection.py       # Motor client, index creation
│   │   ├── models.py           # MongoDB document dataclasses + enums
│   │   └── repositories.py     # CRUD + upsert functions
│   └── pipeline/
│       └── orchestrator.py     # asyncio coordinator
└── frontend/
    ├── vite.config.ts           # proxy: /ws /api /start /stop /status
    ├── tailwind.config.js
    ├── src/
    │   ├── App.tsx              # tab router, theme applicator
    │   ├── index.css            # CSS variable theme system
    │   ├── types/index.ts       # TypeScript interfaces
    │   ├── store/liveStore.ts   # Zustand global store
    │   ├── lib/api.ts           # typed fetch helpers
    │   ├── hooks/
    │   │   ├── useWebSocket.ts  # auto-reconnect WS hook
    │   │   └── useAudioLevel.ts
    │   └── components/
    │       ├── ControlBar.tsx
    │       ├── TranscriptPanel.tsx
    │       ├── SpeakerTimeline.tsx
    │       ├── SentimentChart.tsx
    │       ├── SettingsPanel.tsx
    │       ├── UploadPage.tsx
    │       └── SessionsPage.tsx
```

---

## 3. Environment Configuration

File: `backend/.env`

| Variable | Type | Default | Description |
|---|---|---|---|
| `HF_TOKEN` | string | — | HuggingFace token for pyannote diarization model |
| `DEEPGRAM_API_KEY` | string | — | Deepgram streaming API key |
| `CHUNK_MS` | int | `512` | Audio chunk size in milliseconds (128–2000) |
| `SAMPLE_RATE` | int | `16000` | Microphone sample rate in Hz |
| `AUDIO_CHANNELS` | int | `1` | Microphone channel count |
| `WHISPER_MODEL` | string | `small` | faster-whisper model: tiny / base / small / medium / large |
| `DEVICE` | string | `auto` | Compute device: auto / cpu / mps / cuda |
| `FUSION_ALPHA` | float | `0.6` | Weight of text sentiment in fusion (0.0–1.0) |
| `TRANSLATE_ENABLED` | bool | `false` | Enable post-transcription translation |
| `SOURCE_LANG` | string | `auto` | Default source language for local Whisper |
| `TARGET_LANG` | string | `en` | Translation target language |
| `HOST` | string | `0.0.0.0` | Uvicorn bind address |
| `PORT` | int | `8000` | Uvicorn port |
| `FRONTEND_ORIGIN` | string | `http://localhost:5173` | CORS allowed origin |
| `MONGODB_URL` | string | `mongodb://localhost:27017` | Motor connection URI |
| `MONGODB_DB` | string | `livesense` | Database name |
| `UPLOAD_DIR` | string | `/tmp/livesense_uploads` | File storage directory |
| `MAX_UPLOAD_MB` | int | `500` | Upload size ceiling in MB |

---

## 4. End-to-End Request Flows

### 4.1 Live Session — Deepgram Path

```mermaid
sequenceDiagram
    actor User
    participant Browser as React Dashboard
    participant FastAPI
    participant Orchestrator as PipelineOrchestrator
    participant Ingestion as AudioIngestion
    participant DG as DeepgramTranscriber
    participant Deepgram as Deepgram API (WS)
    participant Sentiment as Sentiment Pipeline
    participant DB as MongoDB
    participant WS as WebSocket Clients

    User->>Browser: Click "Start"
    Browser->>FastAPI: POST /start\n{use_deepgram:true, model:"nova-3", diarize:true, ...}
    FastAPI->>Orchestrator: start(use_deepgram=True, ...)
    Orchestrator->>DB: INSERT sessions {type:live, status:processing}
    Orchestrator->>DG: start(callback=_on_transcript, ...)
    DG->>Deepgram: WS connect\n?model=nova-3&diarize=true&encoding=linear16&...
    Deepgram-->>DG: WS open (HTTP 101)
    DG-->>Orchestrator: ready event set
    Orchestrator->>Ingestion: start() [sounddevice stream]
    FastAPI-->>Browser: {status: "started"}

    loop Every 512ms
        Ingestion->>Orchestrator: float32 PCM chunk → _audio_queue
        Orchestrator->>DG: send_audio(chunk) [int16 PCM bytes]
        DG->>Deepgram: send_media(bytes)
    end

    Deepgram-->>DG: {type:"Results", is_final:true, words:[{word,speaker,start,end}]}
    DG->>DG: _speaker_runs(words) → [(SPEAKER_00, words), (SPEAKER_01, words)]

    loop Each speaker run
        DG->>Orchestrator: _on_transcript(text, speaker_id, language) via run_coroutine_threadsafe
        Orchestrator->>Sentiment: text_analyser.analyse(text)\nacoustic_analyser.analyse(chunk) [parallel]
        Sentiment-->>Orchestrator: EmotionResult, AcousticResult
        Orchestrator->>Orchestrator: fusion.fuse() → FusedSentiment
        Orchestrator->>WS: broadcast_queue.put(SpeakerEvent)
        Orchestrator->>DB: INSERT events {session_id, speaker_id, transcript, polarity, scores, ...}
        Orchestrator->>DB: UPSERT speakers aggregate stats
    end

    WS->>Browser: JSON SpeakerEvent frame
    Browser->>Browser: ingestEvent() → update transcript + speaker state

    User->>Browser: Click "Stop"
    Browser->>FastAPI: POST /stop
    FastAPI->>Orchestrator: stop()
    Orchestrator->>DG: send_close_stream() + cancel task
    Orchestrator->>Ingestion: stop()
    Orchestrator->>DB: UPDATE sessions {status:completed, summary:{...}}
    FastAPI-->>Browser: {status: "stopped"}
```

---

### 4.2 Live Session — Local Whisper Path

```mermaid
sequenceDiagram
    participant Orchestrator as PipelineOrchestrator
    participant Ingestion as AudioIngestion
    participant Queue as _audio_queue
    participant Whisper as Transcriber (faster-whisper)
    participant Tracker as FastSpeakerTracker
    participant Sentiment as Sentiment Pipeline
    participant DB as MongoDB
    participant WS as broadcast_queue

    Note over Orchestrator: use_deepgram=False OR Deepgram key invalid/connection failed

    Orchestrator->>Ingestion: start()

    loop _run_loop_local
        Ingestion-->>Queue: float32 chunk (512ms)
        Queue-->>Orchestrator: await get() chunk
        Orchestrator->>Queue: drain up to 1s more chunks
        Orchestrator->>Orchestrator: np.concatenate(chunks)

        Orchestrator->>Whisper: transcribe(combined, language) [executor thread]
        Note over Whisper: rolling 8s buffer\nVAD + beam decode\ndedup committed segments
        Whisper-->>Orchestrator: TranscriptionResult {full_text, language, segments}

        Orchestrator->>Tracker: identify(combined, sample_rate) [sync]
        Note over Tracker: 39-dim MFCC cosine\nbest 200ms subwindow\n≤8 speaker slots
        Tracker-->>Orchestrator: "SPEAKER_00"

        Orchestrator->>Sentiment: text_analyser.analyse(text)\nacoustic_analyser.analyse(chunk) [parallel]
        Sentiment-->>Orchestrator: EmotionResult + AcousticResult
        Orchestrator->>Orchestrator: fusion.fuse()

        Orchestrator->>WS: put(SpeakerEvent)
        Orchestrator->>DB: INSERT event\nUPSERT speaker stats
    end
```

---

### 4.3 File Upload Path

```mermaid
sequenceDiagram
    actor User
    participant Browser as React Dashboard
    participant FastAPI as FastAPI /api/uploads
    participant BG as BackgroundTask
    participant FileProc as FileProcessor
    participant Diarizer as Diarizer (pyannote)
    participant Whisper as Transcriber.transcribe_full
    participant Sentiment as Sentiment Pipeline
    participant DB as MongoDB

    User->>Browser: Select audio file
    Browser->>FastAPI: POST /api/uploads\nContent-Type: multipart/form-data
    FastAPI->>FastAPI: Validate MIME type
    FastAPI->>FastAPI: Stream to UPLOAD_DIR/{session_id}.ext
    FastAPI->>DB: INSERT uploads {status:uploaded}
    FastAPI->>DB: INSERT sessions {type:upload, status:pending}
    FastAPI->>BG: add_task(processor.process, session_id, path)
    FastAPI-->>Browser: 202 {session_id, status:"accepted"}

    BG->>FileProc: process(session_id, file_path)
    FileProc->>DB: UPDATE sessions {status:processing}\nUPDATE uploads {status:processing}
    FileProc->>FileProc: _load_audio(path) → float32 @ 16kHz

    par Parallel
        FileProc->>Diarizer: diarize_full(audio)\npyannote speaker segments
    and
        FileProc->>Whisper: transcribe_full(audio)\nword-level timestamps + VAD
    end

    FileProc->>FileProc: _align_words_to_speakers(diar_segments, transcript_segments)
    FileProc->>FileProc: _group_words_into_utterances(aligned_words, min_utterance_sec=0.5)

    loop Each utterance
        FileProc->>Sentiment: text_analyser.analyse(utterance.text)\nacoustic_analyser.analyse(utterance.audio_slice) [parallel]
        Sentiment-->>FileProc: EmotionResult + AcousticResult
        FileProc->>FileProc: fusion.fuse()
        FileProc->>DB: INSERT events {session_id, speaker_id, transcript, ...}
        FileProc->>DB: UPSERT speakers {session_id, speaker_id, stats}
    end

    FileProc->>DB: build_session_summary() → SessionSummary
    FileProc->>DB: UPDATE sessions {status:completed, summary:{...}}
    FileProc->>DB: UPDATE uploads {status:completed}
```

---

### 4.4 WebSocket Connection Lifecycle

```mermaid
sequenceDiagram
    participant Browser as React (useWebSocket hook)
    participant Vite as Vite Proxy (:5173)
    participant FastAPI as FastAPI /ws
    participant Manager as ConnectionManager
    participant Broadcaster as broadcaster_task
    participant Queue as broadcast_queue

    Browser->>Vite: WS upgrade /ws
    Vite->>FastAPI: proxy → ws://localhost:8000/ws
    FastAPI->>Manager: connect(ws) → accept + add to _active set
    FastAPI-->>Browser: WS 101 Switching Protocols
    Browser->>Browser: setConnected(true)

    loop Active session
        Queue-->>Broadcaster: SpeakerEvent (from orchestrator)
        Broadcaster->>Manager: broadcast(event)
        Manager->>Manager: event.model_dump_json()
        loop Each client in _active
            Manager->>Browser: send_text(JSON payload)
        end
        Browser->>Browser: parse JSON → ingestEvent()\nupdate transcript + speaker state
    end

    Note over Browser: Idle keepalive
    FastAPI->>Browser: (server sleeps 30s, no-op)

    Browser->>Browser: onclose fired (network drop / server restart)
    Browser->>Browser: setConnected(false)
    Browser->>Browser: setTimeout(reconnect, 3000ms)
    Browser->>Vite: WS upgrade /ws  [retry]
```

---

### 4.5 REST API Request Flow

```mermaid
flowchart TD
    Browser([React Dashboard]) -->|HTTP| Vite[Vite Dev Proxy :5173]
    Vite -->|/start /stop /status| FastAPI_Root[FastAPI root handlers]
    Vite -->|/api/**| FastAPI_Router[APIRouter prefix /api]

    FastAPI_Root --> StartHandler["POST /start\nparse StartRequest\norchestrator.start()"]
    FastAPI_Root --> StopHandler["POST /stop\norchestrator.stop()"]
    FastAPI_Root --> StatusHandler["GET /status\norchestrator._running + device info"]

    FastAPI_Router --> UploadPOST["POST /api/uploads\nvalidate MIME\nstream to disk\ncreate DB records\nschedule BackgroundTask"]
    FastAPI_Router --> UploadGET["GET /api/uploads\nlist_uploads(status,limit,skip)"]
    FastAPI_Router --> SessionsGET["GET /api/sessions\nlist_sessions(type,status,limit,skip)"]
    FastAPI_Router --> SessionDetail["GET /api/sessions/{id}\nget_session()"]
    FastAPI_Router --> SessionEvents["GET /api/sessions/{id}/events\nget_events(speaker_id,limit,skip)"]
    FastAPI_Router --> SessionSpeakers["GET /api/sessions/{id}/speakers\nget_speakers()"]
    FastAPI_Router --> SessionDelete["DELETE /api/sessions/{id}\ndelete file + all DB docs"]

    StartHandler --> Orchestrator[PipelineOrchestrator]
    StopHandler --> Orchestrator
    Orchestrator --> MongoDB[(MongoDB)]
    UploadPOST --> MongoDB
    SessionsGET --> MongoDB
    SessionDetail --> MongoDB
    SessionEvents --> MongoDB
    SessionSpeakers --> MongoDB
    SessionDelete --> MongoDB
```

---

## 5. Component Interaction Diagram

```mermaid
graph TD
    subgraph Frontend [:5173]
        App --> useWebSocket
        App --> ControlBar
        App --> TranscriptPanel
        App --> SpeakerTimeline
        App --> SentimentChart
        App --> UploadPage
        App --> SessionsPage
        ControlBar --> liveStore
        TranscriptPanel --> liveStore
        SpeakerTimeline --> liveStore
        SentimentChart --> liveStore
        useWebSocket --> liveStore
        ControlBar -->|POST /start /stop| Vite_Proxy
        UploadPage -->|POST /api/uploads| Vite_Proxy
        SessionsPage -->|GET /api/sessions/**| Vite_Proxy
        useWebSocket -->|WS /ws| Vite_Proxy
    end

    subgraph Backend [:8000]
        Vite_Proxy -->|proxy| FastAPI
        FastAPI --> Orchestrator
        FastAPI --> UploadsRouter
        FastAPI --> ConnectionManager
        Orchestrator --> AudioIngestion
        Orchestrator --> DeepgramTranscriber
        Orchestrator --> Transcriber
        Orchestrator --> FastSpeakerTracker
        Orchestrator --> TextSentimentAnalyser
        Orchestrator --> AcousticSentimentAnalyser
        Orchestrator --> FusionEngine
        Orchestrator --> broadcast_queue
        broadcast_queue --> broadcaster_task
        broadcaster_task --> ConnectionManager
        ConnectionManager -->|WS frames| useWebSocket
        UploadsRouter --> FileProcessor
        FileProcessor --> Diarizer
        FileProcessor --> Transcriber
        FileProcessor --> TextSentimentAnalyser
        FileProcessor --> AcousticSentimentAnalyser
        FileProcessor --> FusionEngine
        Orchestrator --> MongoDB_Driver
        FileProcessor --> MongoDB_Driver
        UploadsRouter --> MongoDB_Driver
    end

    subgraph External
        DeepgramTranscriber -->|WS PCM| Deepgram_API[Deepgram nova-3 API]
        Deepgram_API -->|JSON transcripts| DeepgramTranscriber
        Diarizer -->|model| HuggingFace[HuggingFace pyannote]
    end

    MongoDB_Driver[(MongoDB)]
```

---

## 6. Backend Module Reference

### 6.1 API Layer

#### `api/main.py` — Endpoints

| Method | Path | Auth | Request Body | Response | Description |
|---|---|---|---|---|---|
| `GET` | `/status` | None | — | `PipelineStatus` | Current pipeline state + device |
| `POST` | `/start` | None | `StartRequest` | `{status: string}` | Start live capture pipeline |
| `POST` | `/stop` | None | — | `{status: string}` | Stop live pipeline, finalize session |
| `WS` | `/ws` | None | — | `SpeakerEvent` stream | Real-time event stream |
| `WS` | `/ws/speaker/{speaker_id}` | None | binary float32 PCM | — | Browser-mic audio input |
| `POST` | `/api/uploads` | None | `multipart/form-data` | `{session_id, status, message}` | Upload audio file (202) |
| `GET` | `/api/uploads` | None | `?status&limit&skip` | `List[dict]` | List upload records |
| `GET` | `/api/uploads/{session_id}` | None | — | `dict` | Single upload record |
| `GET` | `/api/sessions` | None | `?type&status&limit&skip` | `List[dict]` | List sessions |
| `GET` | `/api/sessions/{session_id}` | None | — | `dict` | Session detail + summary |
| `GET` | `/api/sessions/{session_id}/events` | None | `?speaker_id&limit&skip` | `{total, events}` | Paginated events |
| `GET` | `/api/sessions/{session_id}/speakers` | None | — | `List[dict]` | Speaker aggregate stats |
| `DELETE` | `/api/sessions/{session_id}` | None | — | `204` | Delete session + all data |

#### `api/schemas.py` — Pydantic Models

**`StartRequest`**

| Field | Type | Default | Validation |
|---|---|---|---|
| `source_lang` | `str` | `"en"` | ISO-639-1 code or `"auto"` |
| `deepgram_model` | `str` | `"nova-3"` | nova-3 / nova-2 / nova / enhanced / base |
| `diarize` | `bool` | `True` | — |
| `endpointing` | `int` | `300` | `ge=0, le=2000` (ms) |
| `punctuate` | `bool` | `True` | — |
| `use_deepgram` | `bool` | `True` | False = local Whisper path |

**`SpeakerEvent`** (WebSocket payload)

| Field | Type | Nullable | Description |
|---|---|---|---|
| `event_type` | `str` | No | Always `"speaker_event"` |
| `timestamp` | `str` | No | UTC ISO-8601 |
| `speaker_id` | `str` | No | e.g. `SPEAKER_00` |
| `transcript` | `str` | No | Transcribed text |
| `language` | `str` | No | Detected language code |
| `translation` | `str` | Yes | Optional translated text |
| `polarity` | `str` | No | `positive` / `negative` / `neutral` |
| `final_score` | `float` | No | Fused sentiment score [0, 1] |
| `text_score` | `float` | Yes | Text-only sentiment score |
| `acoustic_score` | `float` | Yes | Prosody-based score |
| `dominant_emotion` | `str` | Yes | e.g. `joy`, `anger`, `neutral` |
| `emotions` | `Dict[str,float]` | No | Full emotion distribution |
| `confidence` | `float` | No | Fusion confidence [0, 1] |

---

### 6.2 Pipeline Orchestrator

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Starting: POST /start
    Starting --> Deepgram_Mode: use_deepgram=True AND key valid AND WS connected
    Starting --> Local_Mode: use_deepgram=False OR key missing OR WS failed
    Deepgram_Mode --> Running_DG: AudioIngestion started
    Local_Mode --> Running_Local: AudioIngestion started
    Running_DG --> Stopping: POST /stop
    Running_Local --> Stopping: POST /stop
    Stopping --> Idle: cleanup complete
```

**Mode selection logic:**

```
use_deepgram=True AND DEEPGRAM_API_KEY != ""
    → DeepgramTranscriber.start()
        → success → DEEPGRAM MODE
        → exception → fallback → LOCAL MODE
use_deepgram=False OR key empty
    → LOCAL MODE (faster-whisper + FastSpeakerTracker)
```

---

### 6.3 Core Processing Modules

#### Audio Ingestion (`core/audio_ingestion.py`)

| Parameter | Value |
|---|---|
| Library | `sounddevice` |
| Sample rate | `settings.sample_rate` (default 16 000 Hz) |
| Channels | `settings.audio_channels` (default 1 / mono) |
| dtype | `float32` |
| Block size | `sample_rate × 0.032` = 512 samples @ 16 kHz |
| Emit chunk size | `sample_rate × chunk_ms / 1000` (default 512 ms = 8 192 samples) |
| Internal buffer | `collections.deque` of raw blocks |

#### Deepgram Transcriber (`core/deepgram_transcriber.py`)

| Parameter | Value |
|---|---|
| SDK | `deepgram-sdk >= 7.x` (`AsyncDeepgramClient`) |
| Endpoint | `listen.v1.connect()` (async context manager) |
| Encoding | `linear16` (int16 PCM) |
| Sample rate | 16 000 Hz |
| Diarization | per-word `speaker` field (int) |
| Result filter | `is_final=True` only |
| Speaker split | `_speaker_runs()` — consecutive same-speaker word groups |
| Callback bridge | `asyncio.run_coroutine_threadsafe` (SDK → asyncio event loop) |
| Connect timeout | 10 seconds |

#### Transcriber — Local ASR (`core/transcription.py`)

| Parameter | Value |
|---|---|
| Library | `faster-whisper` |
| Model | `settings.whisper_model` (default `small`) |
| Buffer | Rolling 8 s, minimum 1.2 s before first inference |
| Beam size | 3 |
| VAD filter | Disabled in live mode; enabled in `transcribe_full` |
| Dedup | Timestamp cursor + text ring-buffer (last 20 emissions) |
| Stability margin | 100 ms tail held back |

#### Speaker Tracker — Live (`core/speaker_tracker.py`)

| Parameter | Value |
|---|---|
| Features | 39-dim MFCC + Δ + ΔΔ, L2-normalized |
| Similarity | Cosine distance |
| New-speaker threshold | 0.62 |
| Max speakers | 8 |
| Centroid freeze after | 8 updates |
| Subwindow | Best 200 ms by RMS |
| Silence skip | RMS < 0.005 |

#### Text Sentiment (`core/text_sentiment.py`)

| Parameter | Value |
|---|---|
| Model | `j-hartmann/emotion-english-distilroberta-base` |
| Framework | HuggingFace `transformers` pipeline |
| Output labels | `anger`, `disgust`, `fear`, `joy`, `neutral`, `sadness`, `surprise` |
| Polarity map | positive → joy, surprise; negative → anger, disgust, fear, sadness; neutral → neutral |
| Score formula | `(pos×1 + neu×0.5 + neg×0) / total` |
| Max tokens | 512 (truncation enabled) |

#### Acoustic Sentiment (`core/acoustic_sentiment.py`)

| Feature | Extraction method |
|---|---|
| F0 (pitch) | `librosa.yin`, fmin 75 Hz, fmax 400 Hz |
| Energy (RMS) | Mean of RMS frames |
| Speech rate proxy | `zero_crossing_rate` mean |
| MFCCs | 13 coefficients, mean per frame |
| Prosodic score | `0.45×F0_norm + 0.35×energy_norm + 0.20×rate_norm`, mapped to [0.2, 0.85] |

#### Fusion Engine (`core/fusion.py`)

| Scenario | Formula | Confidence |
|---|---|---|
| Both text + acoustic | `alpha × text_score + (1−alpha) × acoustic_score` | `0.7 + 0.3×min(text_score, 1)` |
| Text only | `text_score` | `0.6 × text_score` |
| Acoustic only | `acoustic_score` | `0.4` |
| Neither | `0.5` | `0.0` |

Polarity thresholds:

| Score range | Polarity |
|---|---|
| ≥ 0.65 | `positive` |
| ≤ 0.40 | `negative` |
| 0.40 – 0.65 | `neutral` |

Default `FUSION_ALPHA = 0.6` (60% text, 40% acoustic).

---

## 7. Database Design

### 7.1 Collections Overview

| Collection | Purpose | Write pattern | Read pattern |
|---|---|---|---|
| `sessions` | One doc per live/upload session | Insert on start; update on stop/complete | List + detail queries |
| `events` | One doc per transcript utterance | Append-only during session | Paginated by session + speaker |
| `speakers` | Aggregate stats per speaker per session | Incremental upsert during session | Per-session speaker list |
| `uploads` | Metadata for uploaded files | Insert on receive; update on processing | List + status polling |

---

### 7.2 `sessions` Collection

| Field | BSON Type | Required | Description |
|---|---|---|---|
| `_id` | ObjectId | Auto | MongoDB document ID |
| `session_id` | String | ✓ | UUID v4 — primary business key |
| `type` | String | ✓ | `live` or `upload` |
| `status` | String | ✓ | `pending` / `processing` / `completed` / `failed` |
| `created_at` | Date | ✓ | UTC creation timestamp |
| `updated_at` | Date | ✓ | UTC last-update timestamp |
| `completed_at` | Date | — | UTC completion timestamp |
| `file` | Object | — | `FileMetadata` sub-document (upload sessions only) |
| `file.original_name` | String | — | Original uploaded filename |
| `file.stored_name` | String | — | Stored filename on disk |
| `file.size_bytes` | Int64 | — | File size |
| `file.duration_seconds` | Double | — | Audio duration |
| `file.sample_rate` | Int32 | — | Detected sample rate |
| `file.channels` | Int32 | — | Channel count |
| `file.format` | String | — | e.g. `mp3`, `wav` |
| `file.content_type` | String | — | MIME type |
| `summary` | Object | — | `SessionSummary` sub-document (post-completion) |
| `summary.event_count` | Int32 | — | Total utterances |
| `summary.speaker_count` | Int32 | — | Unique speakers detected |
| `summary.total_duration_seconds` | Double | — | Session duration |
| `summary.dominant_emotion` | String | — | Most frequent emotion |
| `summary.avg_sentiment_score` | Double | — | Session-level average |
| `summary.polarity_distribution` | Object | — | `{positive, negative, neutral}` counts |
| `summary.languages` | Array[String] | — | Detected language codes |
| `error` | String | — | Error message if `status=failed` |
| `tags` | Array[String] | — | User-defined tags |

---

### 7.3 `events` Collection

| Field | BSON Type | Required | Description |
|---|---|---|---|
| `_id` | ObjectId | Auto | MongoDB document ID |
| `session_id` | String | ✓ | Foreign key → `sessions.session_id` |
| `event_index` | Int32 | ✓ | 0-based sequential index within session |
| `timestamp_utc` | Date | ✓ | UTC time of event creation |
| `offset_seconds` | Double | ✓ | Seconds from session start (0.0 for live) |
| `speaker_id` | String | ✓ | e.g. `SPEAKER_00` |
| `transcript` | String | ✓ | Utterance text |
| `language` | String | ✓ | ISO-639-1 language code |
| `translation` | String | — | Translated text (if enabled) |
| `polarity` | String | ✓ | `positive` / `negative` / `neutral` |
| `final_score` | Double | ✓ | Fused sentiment score [0, 1] |
| `text_score` | Double | — | Text model score |
| `acoustic_score` | Double | — | Acoustic model score |
| `dominant_emotion` | String | — | Top emotion label |
| `emotions` | Object | ✓ | `{anger, disgust, fear, joy, neutral, sadness, surprise}` → float |
| `confidence` | Double | ✓ | Fusion confidence [0, 1] |

---

### 7.4 `speakers` Collection

| Field | BSON Type | Required | Description |
|---|---|---|---|
| `_id` | ObjectId | Auto | MongoDB document ID |
| `session_id` | String | ✓ | Foreign key → `sessions.session_id` |
| `speaker_id` | String | ✓ | e.g. `SPEAKER_00` |
| `total_utterances` | Int32 | ✓ | Count of utterances |
| `total_words` | Int32 | ✓ | Total word count |
| `total_speaking_seconds` | Double | ✓ | Cumulative speaking time |
| `avg_sentiment_score` | Double | ✓ | Running average fused score |
| `sentiment_score_sum` | Double | ✓ | Raw sum for online average computation |
| `dominant_emotion` | String | — | Most frequent emotion label |
| `emotion_counts` | Object | ✓ | `{emotion: count}` map |
| `polarity_counts` | Object | ✓ | `{positive, negative, neutral}` counts |
| `sentiment_timeline` | Array[Object] | ✓ | Capped at 500 points |
| `sentiment_timeline[].offset_seconds` | Double | — | Time from session start |
| `sentiment_timeline[].score` | Double | — | Fused score at this point |
| `sentiment_timeline[].speaker_id` | String | — | Redundant denormalized ID |
| `languages` | Array[String] | ✓ | Distinct language codes detected |
| `updated_at` | Date | ✓ | UTC last-update timestamp |

---

### 7.5 `uploads` Collection

| Field | BSON Type | Required | Description |
|---|---|---|---|
| `_id` | ObjectId | Auto | MongoDB document ID |
| `session_id` | String | ✓ | Foreign key → `sessions.session_id` |
| `original_filename` | String | ✓ | User-provided filename |
| `content_type` | String | ✓ | MIME type (audio/wav, audio/mp3, etc.) |
| `size_bytes` | Int64 | ✓ | File size in bytes |
| `storage_path` | String | ✓ | Absolute path on server disk |
| `status` | String | ✓ | `uploaded` / `processing` / `completed` / `failed` |
| `uploaded_at` | Date | ✓ | UTC receive timestamp |
| `processing_started_at` | Date | — | UTC when BackgroundTask began |
| `processing_completed_at` | Date | — | UTC when processing finished |
| `error` | String | — | Error message if `status=failed` |

---

### 7.6 Indexes

| Collection | Index Fields | Type | Notes |
|---|---|---|---|
| `sessions` | `session_id` | Unique | Primary lookup key |
| `sessions` | `(type, status)` | Compound | List filtering |
| `sessions` | `created_at DESC` | Single | Chronological listing |
| `events` | `(session_id, event_index)` | Unique | Dedup on insert |
| `events` | `(session_id, speaker_id)` | Compound | Speaker-filtered event fetch |
| `events` | `timestamp_utc DESC` | Single | Recent-first ordering |
| `speakers` | `(session_id, speaker_id)` | Unique | Upsert target |
| `uploads` | `session_id` | Unique | Primary lookup |
| `uploads` | `status` | Single | Status filtering |
| `uploads` | `uploaded_at DESC` | Single | Recent-first listing |

---

## 8. REST API Contract

### `POST /start`

**Request**
```json
{
  "source_lang": "en",
  "deepgram_model": "nova-3",
  "diarize": true,
  "endpointing": 300,
  "punctuate": true,
  "use_deepgram": true
}
```

**Response 200**
```json
{ "status": "started" }
```

**Response 200 (already running)**
```json
{ "status": "already running" }
```

---

### `POST /stop`

**Response 200**
```json
{ "status": "stopped" }
```

---

### `GET /status`

**Response 200**
```json
{
  "running": true,
  "device": "mps",
  "whisper_model": "small",
  "source_lang": "en"
}
```

---

### `POST /api/uploads`

**Request** — `multipart/form-data`, field `file`

**Response 202**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "message": "File is being processed"
}
```

**Error 400** — unsupported MIME type  
**Error 413** — file exceeds `MAX_UPLOAD_MB`

---

### `GET /api/sessions/{session_id}/events`

**Query params:** `speaker_id`, `limit` (default 200), `skip` (default 0)

**Response 200**
```json
{
  "total": 42,
  "events": [
    {
      "session_id": "550e8400...",
      "event_index": 0,
      "timestamp_utc": "2026-06-21T20:00:00Z",
      "speaker_id": "SPEAKER_00",
      "transcript": "Hello world.",
      "language": "en",
      "polarity": "positive",
      "final_score": 0.72,
      "text_score": 0.78,
      "acoustic_score": 0.61,
      "dominant_emotion": "joy",
      "emotions": {"joy": 0.65, "neutral": 0.20, "surprise": 0.10, "anger": 0.02, "fear": 0.01, "sadness": 0.01, "disgust": 0.01},
      "confidence": 0.83
    }
  ]
}
```

---

### `GET /api/sessions/{session_id}/speakers`

**Response 200**
```json
[
  {
    "session_id": "550e8400...",
    "speaker_id": "SPEAKER_00",
    "total_utterances": 15,
    "total_words": 180,
    "avg_sentiment_score": 0.64,
    "dominant_emotion": "joy",
    "polarity_counts": {"positive": 9, "neutral": 5, "negative": 1},
    "sentiment_timeline": [
      {"offset_seconds": 0.0, "score": 0.70, "speaker_id": "SPEAKER_00"}
    ],
    "languages": ["en"]
  }
]
```

---

## 9. WebSocket Protocol

### Connection

```
ws://localhost:8000/ws
```

The frontend proxy (`vite.config.ts`) rewrites `/ws` → `ws://localhost:8000/ws` with `ws: true, changeOrigin: true`.

### Message Format (server → client)

All messages are JSON-serialized `SpeakerEvent` objects:

```json
{
  "event_type": "speaker_event",
  "timestamp": "2026-06-21T20:22:21.123456Z",
  "speaker_id": "SPEAKER_01",
  "transcript": "Figure out what you can tolerate.",
  "language": "en",
  "translation": null,
  "polarity": "negative",
  "final_score": 0.35,
  "text_score": 0.30,
  "acoustic_score": 0.43,
  "dominant_emotion": "sadness",
  "emotions": {
    "anger": 0.05, "disgust": 0.02, "fear": 0.03,
    "joy": 0.10, "neutral": 0.20, "sadness": 0.55, "surprise": 0.05
  },
  "confidence": 0.72
}
```

### Reconnect Logic

```
connect()
  onopen  → setConnected(true)
  onclose → setConnected(false)
            if (!unmounted) setTimeout(connect, 3000ms)
  onerror → ws.close()  [triggers onclose]
  cleanup → unmounted = true; clearTimeout; ws.close()
```

The `unmounted` flag prevents React StrictMode's double-mount from creating a spurious extra connection.

---

## 10. Frontend Architecture

### 10.1 Component Tree

```
App
├── useWebSocket()           [singleton hook, auto-reconnect]
├── Header
│   └── ControlBar           [start/stop, settings gear, audio VU]
│       └── SettingsPanel    [slide-in drawer]
├── TabBar (live | upload | sessions)
├── [live tab]
│   ├── SpeakerTimeline      [per-speaker polarity badges]
│   ├── SentimentChart       [recharts time-series]
│   └── TranscriptPanel      [typewriter animation, per-entry colour]
├── [upload tab]
│   └── UploadPage           [drag-drop, progress, session link]
└── [sessions tab]
    └── SessionsPage         [session list, detail, event replay]
```

### 10.2 Zustand Store Schema

```typescript
interface LiveStore {
  // ── Connection ──────────────────────────────────────
  connected: boolean
  pipelineRunning: boolean

  // ── Theme ───────────────────────────────────────────
  theme: 'dark' | 'midnight' | 'ember' | 'forest' | 'light'
  // persisted to localStorage key "ls-theme"

  // ── Deepgram / Pipeline settings ────────────────────
  dgSettings: {
    sourceLang: string          // default "en"
    deepgramModel: string       // default "nova-3"
    diarize: boolean            // default true
    endpointing: number         // default 300 ms
    punctuate: boolean          // default true
    useDeepgram: boolean        // default true
  }

  // ── Speaker state ────────────────────────────────────
  speakers: Map<string, SpeakerState>
  // SpeakerState: { speaker_id, latest_polarity, latest_score,
  //                 dominant_emotion, sentimentHistory: SentimentPoint[] }
  _speakerOrder: string[]       // insertion-order array for colour assignment
  speakerColour(id): string     // cycles 8-colour palette

  // ── Transcript ───────────────────────────────────────
  transcript: TranscriptEntry[]
  // TranscriptEntry: { id, speaker_id, timestamp, text, translation, polarity, language }
  // max 200 entries; deduplicated by id = "${speaker_id}-${timestamp}"
}
```

### 10.3 Vite Proxy Map

| Frontend path | Proxied to | Protocol |
|---|---|---|
| `/ws` | `ws://localhost:8000/ws` | WebSocket |
| `/api/**` | `http://localhost:8000` | HTTP |
| `/start` | `http://localhost:8000` | HTTP |
| `/stop` | `http://localhost:8000` | HTTP |
| `/status` | `http://localhost:8000` | HTTP |

> **Note:** Live pipeline controls (`/start`, `/stop`, `/status`) use the root path, while data endpoints (`/api/**`) use the `/api` prefix handled by the `uploads` APIRouter.

---

## 11. Sentiment Pipeline Detail

```mermaid
flowchart LR
    transcript["transcript text\n(from Deepgram or Whisper)"]
    audio["audio chunk\n(float32 PCM)"]

    transcript --> TextModel["TextSentimentAnalyser\ndistilroberta-base\n7 emotions → polarity + score"]
    audio --> AcousticModel["AcousticSentimentAnalyser\nF0 · RMS · ZCR · MFCC\n→ prosodic_score [0.2, 0.85]"]

    TextModel --> |"EmotionResult\n(label, polarity, score, emotions{})"|Fusion
    AcousticModel --> |"AcousticResult\n(prosodic_score, f0, energy, ...)"|Fusion

    Fusion["FusionEngine\nfinal = α·text + (1-α)·acoustic\nα = 0.6 (FUSION_ALPHA)"]

    Fusion --> |"FusedSentiment\n(polarity, final_score,\nconfidence, emotions)"|Event["SpeakerEvent\n→ broadcast_queue\n→ MongoDB events"]
```

**Emotion-to-polarity mapping:**

| Emotion | Polarity |
|---|---|
| `joy` | positive |
| `surprise` | positive |
| `neutral` | neutral |
| `anger` | negative |
| `disgust` | negative |
| `fear` | negative |
| `sadness` | negative |

---

## 12. Data Flow State Machine

```mermaid
stateDiagram-v2
    [*] --> AppInit: Server startup

    AppInit --> ModelsLoaded: load_models()\nWhisper + TextSentiment
    ModelsLoaded --> DBConnected: init_db()\nMotor ping
    DBConnected --> Ready: broadcaster_task started

    Ready --> SessionActive: POST /start
    SessionActive --> DeepgramMode: use_deepgram=True\nAPI key valid\nWS connected
    SessionActive --> LocalMode: fallback

    DeepgramMode --> Transcribing_DG: AudioIngestion.start()
    LocalMode --> Transcribing_Local: AudioIngestion.start()

    Transcribing_DG --> EventEmitted: Deepgram final result\n_speaker_runs split\n→ _handle_transcript
    Transcribing_Local --> EventEmitted: Whisper decode\nFastSpeakerTracker\n→ _handle_transcript

    EventEmitted --> EventEmitted: sentiment analysis\nfusion\nbroadcast\nDB persist

    EventEmitted --> SessionClosing: POST /stop
    SessionClosing --> Ready: finalize_session()\nbuild_session_summary()

    Ready --> FileProcessing: POST /api/uploads\nBackgroundTask
    FileProcessing --> Ready: completed or failed
```

---

*Generated 2026-06-22 · LiveSense v1.0*
