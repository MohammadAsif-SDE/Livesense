# LiveSense — Problem Statement

> *Real-time multimodal sentiment analysis and speaker diarization for spoken conversations*

---

## 1. Background

Human communication is inherently multimodal. When people speak, they convey meaning not only through words but through **tone, pitch, rhythm, and emotion**. In meetings, interviews, customer calls, classrooms, and debates, the emotional state of each participant is as important as the content of what is being said.

Yet the vast majority of tools available today treat spoken audio as a **one-dimensional text extraction problem** — convert speech to text, then optionally classify the text. This approach discards the rich acoustic signal that carries stress, urgency, confidence, and affect.

At the same time, the rapid adoption of remote work, virtual collaboration, and AI-powered assistants has created an enormous volume of spoken audio that organisations struggle to analyse at scale.

---

## 2. Problem Definition

### 2.1 Core Problem

> **There is no accessible, real-time system that simultaneously identifies who is speaking, what they are saying, and how they feel — integrating both the linguistic and the acoustic dimensions of emotion — while making this analysis immediately visible to a human observer.**

Existing solutions fail in one or more of the following ways:

| Gap | Description |
|---|---|
| **Batch-only processing** | Most sentiment and diarization tools require a complete audio file. There is no live, streaming analysis with sub-second latency. |
| **Text-only sentiment** | Tools that do offer real-time transcription (e.g. meeting assistants) perform sentiment analysis on transcribed text alone, discarding prosodic cues such as pitch, energy, and speaking rate that are strong indicators of emotional state. |
| **No speaker attribution** | Real-time transcription tools typically produce a single undifferentiated text stream. Identifying *which* speaker expressed a given sentiment is either unavailable or requires post-processing. |
| **Closed, costly infrastructure** | Enterprise solutions for speaker analytics are expensive, proprietary, and inaccessible to researchers, startups, and individuals who need them most. |
| **No unified pipeline** | Diarization, transcription, and sentiment are offered as separate disconnected APIs, forcing developers to build brittle integration glue with high latency overhead. |

### 2.2 Specific Pain Points

**1. Conversation monitoring without insight**
A call-centre manager listening to a live customer call has no automated signal for rising frustration. A therapist conducting a remote session has no objective measure of a patient's emotional trajectory. A debate moderator cannot instantly see which speakers are becoming agitated.

**2. Post-hoc analysis is too slow**
Recordings are reviewed hours or days after the fact. Emotional moments have passed. Interventions that could have changed outcomes are no longer possible. The value of emotional intelligence is time-sensitive.

**3. Speaker confusion in multi-party conversations**
When multiple people speak, automated systems frequently attribute words to the wrong speaker. Sentiment calculated on mis-attributed speech produces misleading results — e.g. flagging a calm listener as angry because their words were merged with an upset speaker's utterance.

**4. Acoustic signal is discarded**
Text models score a sentence like *"That's fine"* as neutral or positive regardless of whether it was spoken calmly or through clenched teeth. The acoustic channel — pitch, energy, speaking rate — must be fused with the linguistic channel to produce a reliable sentiment estimate.

**5. No portable, open baseline**
There is no open-source, self-hostable reference system that combines these capabilities end-to-end. Researchers studying multimodal affect, developers building conversation analytics products, and educators teaching NLP have nowhere to start.

---

## 3. Stakeholders and Use Cases

| Stakeholder | Scenario | Required capability |
|---|---|---|
| **Call centre supervisor** | Monitor live customer service calls for escalating frustration | Real-time per-speaker sentiment with polarity alerts |
| **UX researcher** | Analyse recorded user interviews for emotional responses to product features | File upload processing with timestamped per-utterance sentiment |
| **Clinical researcher** | Study emotional dynamics in therapy or diagnostic sessions | Speaker diarization + longitudinal sentiment timeline |
| **Debate / panel moderator** | Track emotional temperature of a live multi-speaker discussion | Live multi-speaker tracking with sentiment dashboard |
| **Podcast / media producer** | Review recorded content to identify emotionally charged moments | Upload processing with emotion classification and highlight export |
| **Software developer / ML engineer** | Build a conversation analytics product or benchmark multimodal sentiment models | Open, extensible backend with clean REST + WebSocket API |
| **Educator / student** | Learn how real-time NLP pipelines work end-to-end | Documented, runnable system with clear architecture |

---

## 4. Research and Technical Challenges

The problem is non-trivial. Solving it well requires addressing the following hard sub-problems:

### 4.1 Real-time Speaker Diarization
Identifying *who is speaking* in a live audio stream (i.e. without access to the full recording) is fundamentally harder than offline diarization. Speaker embeddings must be built incrementally, centroids must adapt as new speech arrives, and transitions must be detected with minimal latency and without false splits.

### 4.2 Latency vs. Accuracy Trade-off in ASR
Whisper-family models produce high-quality transcriptions but operate on fixed audio windows. Streaming them introduces a rolling-buffer problem: when to commit a segment as final, how to avoid repeating previously emitted text, and how to handle speaker transitions within a window.

### 4.3 Acoustic Feature Extraction at Chunk Granularity
Prosodic features (F0, RMS energy, zero-crossing rate) are meaningful only over sufficient audio duration. Extracting them reliably from 500 ms chunks — with variable speech content, background noise, and microphone variation — introduces estimation noise that must be managed.

### 4.4 Multimodal Fusion
Combining a text-based emotion score with an acoustic prosody score requires careful calibration. The two modalities have different reliability profiles: text is more precise for content-bearing sentiment; acoustics are more revealing for suppressed or ambiguous affect. A fixed linear fusion weighted by a learnable alpha is a tractable first-order approximation.

### 4.5 Scalable Real-time Broadcast
A single audio session may produce tens of events per minute across multiple concurrent WebSocket clients. The event pipeline must be non-blocking, backpressure-aware, and resilient to slow consumers.

---

## 5. Proposed Solution

**LiveSense** is an open-source, full-stack system that addresses all of the above by integrating:

```
Microphone / Uploaded file
        │
        ▼
┌─────────────────────────────────────────────────────┐
│          Speech Recognition + Diarization           │
│  • Deepgram nova-3 (live, neural, per-word speaker) │
│  • faster-whisper + MFCC cosine tracker (local)     │
└─────────────────────────┬───────────────────────────┘
                          │  transcript + speaker_id
                          ▼
┌─────────────────────────────────────────────────────┐
│           Multimodal Sentiment Analysis             │
│  • Text: distilroberta 7-class emotion classifier   │
│  • Acoustic: F0 · RMS · ZCR · MFCC prosody model   │
│  • Fusion: α·text + (1−α)·acoustic  [α = 0.6]      │
└─────────────────────────┬───────────────────────────┘
                          │  SpeakerEvent {polarity, score, emotions}
                          ▼
┌─────────────────────────────────────────────────────┐
│        Real-time Dashboard + Persistent Store       │
│  • WebSocket broadcast → React dashboard            │
│  • Per-speaker sentiment timeline                   │
│  • MongoDB session / event / speaker storage        │
└─────────────────────────────────────────────────────┘
```

### Solution Properties

| Property | How LiveSense achieves it |
|---|---|
| **Real-time** | Deepgram streaming WS delivers final transcripts at ~300–500 ms latency |
| **Speaker-attributed** | Per-word speaker labels from Deepgram diarization; intra-utterance speaker splits via `_speaker_runs()` |
| **Multimodal** | Text + acoustic sentiment fused per utterance |
| **Open & self-hostable** | Runs on a local machine (CPU/MPS/CUDA); no mandatory cloud services |
| **File upload support** | Full pyannote diarization + Whisper word-level alignment for recorded audio |
| **Observable** | Live React dashboard with per-speaker timelines, emotion chart, and scrolling transcript |
| **Persistent** | All sessions, events, and speaker aggregates stored in MongoDB for retrospective analysis |
| **Extensible** | Clean REST + WebSocket API; pluggable sentiment models; configurable fusion alpha |

---

## 6. Success Criteria

The system is considered to solve the stated problem when it satisfies the following measurable outcomes:

| Criterion | Target |
|---|---|
| Live transcript latency (Deepgram path) | < 1 second from speech to displayed transcript |
| Speaker diarization — same speaker continuity | Consecutive utterances from the same speaker assigned identical `SPEAKER_XX` label in > 85% of cases under controlled conditions |
| Sentiment polarity accuracy | > 70% agreement with human-labelled ground truth on a held-out spoken conversation dataset |
| Dashboard update rate | WebSocket events visible in browser within 200 ms of server emission |
| Concurrent WebSocket clients | Dashboard serves ≥ 5 simultaneous observers without dropped events |
| File upload processing | 10-minute audio file fully processed (diarized, transcribed, sentiment-scored) within 3× real-time on CPU |
| System availability | Backend recovers gracefully from Deepgram disconnection and MongoDB unavailability without crashing |

---

## 7. Scope and Boundaries

### In Scope
- Live microphone capture and streaming sentiment analysis
- File upload processing for pre-recorded audio
- Speaker diarization (both neural and local-MFCC)
- Text + acoustic multimodal sentiment fusion
- Real-time WebSocket dashboard
- Session history and event replay via REST API
- Configurable transcription engine (Deepgram / local Whisper)
- Theme-able React frontend

### Out of Scope (current version)
- Speaker identification by name or biometric profile (only anonymous `SPEAKER_XX` labels)
- Multi-language sentiment models (text model is English-only)
- Mobile or desktop native applications
- Automatic alerting or notifications on sentiment thresholds
- Speaker enrollment or voice training
- Video input or facial expression analysis
- Multi-tenant authentication and authorisation

---

## 8. Why This Problem Matters Now

Three converging trends make this problem urgent:

**1. The remote-work inflection point**
More conversations than ever are happening over audio channels — video calls, voice messages, call centres, virtual classrooms. The volume of spoken interaction that could benefit from real-time emotional intelligence has grown by orders of magnitude.

**2. Foundation model accessibility**
Large-scale ASR models (Whisper), neural diarization (pyannote), and fast emotion classifiers (distilroberta) are now publicly available and can run on consumer hardware. The technical barriers to building this system have collapsed in the last two years.

**3. The gap in open tooling**
Despite the availability of individual components, no open, integrated, real-time system exists that combines diarization, transcription, and multimodal sentiment in a single runnable pipeline with a usable interface. LiveSense fills this gap.

---

## 9. Summary

| Dimension | Statement |
|---|---|
| **Problem** | Live conversations produce rich emotional signals that current tools discard, delay, or mis-attribute to speakers |
| **Who is affected** | Anyone who needs to understand the emotional dynamics of spoken multi-party conversations in real time or from recordings |
| **Root cause** | Fragmented tooling, batch-only architectures, and text-only sentiment models that ignore acoustic affect |
| **Solution** | An open-source, real-time, multimodal pipeline that identifies speakers, transcribes speech, analyses text + prosody, fuses both signals, and streams results to an observable dashboard |
| **Value delivered** | Sub-second emotional intelligence, per-speaker attribution, persistent session analytics, and a foundation for building higher-level conversation AI applications |

---
