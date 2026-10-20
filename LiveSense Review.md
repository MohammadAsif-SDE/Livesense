# **LiveSense - Real-Time Speaker Diarization & Sentiment Analysis using Multimodal AI and NLP** 

## **1. INTRODUCTION** 

LiveSense is an end-to-end, real-time pipeline that combines speaker diarization, automatic speech recognition (ASR), language translation, and multimodal sentiment analysis into a unified system. The project addresses a critical gap in conversational Al: the ability to not only transcribe who said what, but to understand the emotional state of each speaker in real time, across multiple languages, directly from live audio. 

The pipeline ingests streaming audio in 512-millisecond chunks. Each chunk is simultaneously routed through pyannote.audio for speaker labelling and OpenAl Whisper/Gemini Flash or any open model for transcription. Transcribed text is optionally translated via MarianMT (Helsinki-NLP). Two parallel sentiment channels then operate: a text-sentiment classifier based on RoBERTa extracts fine-grained emotions (Positive (joy), Negative (anger, sadness) & neutral) from the transcript, while Librosa extracts acoustic features - MFCC coefficients, fundamental frequency, energy envelope, and speech rate to infer prosodic sentiment. A late-fusion engine combines both channels into a single weighted sentiment score per speaker turn. 

Results are streamed over a FastAPI WebSocket server to a React dashboard that renders a live speaker timeline, per-speaker sentiment trend chart, colour-coded transcript panel, and translation overlay. The system is designed for use in customer service quality monitoring, mental health teletherapy support, multilingual meeting analytics, media broadcast monitoring, and academic emotion-recognition research. 

## **2. SYSTEM CONFIGURATION** 

## **2.1 HARDWARE SPECIFICATION** 

|**Component**|**Specification**|**Notes**|
|---|---|---|
|CPU|Intel Core i7 / AMD Ryzen 7 (8+ cores)|Parallel processing of Whisper + Librosa tasks|
|GPU (Recommended)|NVIDIA RTX 3060 / 4060 (8 GB+<br>VRAM)|Accelerates Whisper inference and RoBERTa fine-tuning<br>via CUDA|
|RAM|Minimum 16 GB (32 GB recommended)|Holds Whisper medium model (~1.5 GB) + RoBERTa +<br>pyannote simultaneously|
|Storage|SSD, 20 GB free space|Model weights, audio buffers, log files, and output exports|
|Audio I/O|USB microphone or built-in mic|Stereo or mono capture; 16 kHz sample rate minimum for<br>Whisper|
|Network|Stable broadband (for initial model<br>downloads)|Models downloaded once from HuggingFace Hub; local<br>inference thereafter|



## **2.2 SOFTWARE SPECIFICATION** 

|**Software**|**Version / Build**|**Purpose**|
|---|---|---|
|Operating System|Ubuntu 22.04 LTS / Windows<br>11 / macOS 13+|Cross-platform; Ubuntu recommended for GPU CUDA support|
|Python|3.10 or 3.11|Core runtime for all ML and backend components|
|CUDA Toolkit|11.8 or 12.1 (GPU path)|Required for GPU-accelerated Whisper and PyTorch inference|
|PyTorch|2.1+ (cu118 / cu121 wheel)|Backend for Whisper, RoBERTa, and pyannote models|
|FastAPI|0.111+|Async API server and WebSocket handler for real-time streaming|
|Node.js / npm|Node 20 LTS|Frontend build toolchain for React dashboard|
|Docker (Optional)|Docker 24+ with NVIDIA<br>Container Toolkit|Containerised deployment for reproducible environments|

