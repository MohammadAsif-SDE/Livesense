"""
main.py
───────
FastAPI application factory.

Endpoints:
  GET  /status        — pipeline status
  POST /start         — begin audio capture & pipeline
  POST /stop          — stop pipeline
  WS   /ws            — real-time SpeakerEvent stream
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import ErrorResponse, PipelineStatus, StartRequest
from api.websocket import broadcaster_task, websocket_endpoint
from api.uploads import router as uploads_router
from api.auth import router as auth_router, get_optional_user
from api.users import router as users_router
from config.settings import get_settings
from pipeline.orchestrator import PipelineOrchestrator
from db.connection import init_db, close_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Shared broadcast queue between orchestrator and WS broadcaster
_broadcast_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
_orchestrator: PipelineOrchestrator | None = None
_broadcaster_task_handle: asyncio.Task | None = None


# ── Lifespan ──────────────────────────────────────────────────────────── #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models at startup; clean up on shutdown."""
    global _orchestrator, _broadcaster_task_handle

    _orchestrator = PipelineOrchestrator(_broadcast_queue)
    logger.info("Loading ML models (this may take a minute on first run) …")
    # Run blocking model loading in a thread so we don't block the event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _orchestrator.load_models)
    logger.info("Models ready.  Server is up.")

    # Connect to MongoDB
    try:
        await init_db()
        # Seed default admin user
        from core.auth_utils import hash_password
        from db.connection import get_db
        from db.repositories import ensure_admin_user
        db = get_db()
        await ensure_admin_user(
            db,
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
        )
    except Exception as exc:
        logger.warning("MongoDB unavailable (%s) — DB features disabled", exc)

    _broadcaster_task_handle = asyncio.create_task(
        broadcaster_task(_broadcast_queue)
    )

    yield

    # Shutdown
    if _orchestrator:
        await _orchestrator.stop()
    if _broadcaster_task_handle:
        _broadcaster_task_handle.cancel()
    await close_db()


# ── App ───────────────────────────────────────────────────────────────── #

app = FastAPI(
    title="LiveSense API",
    description="Real-time speaker diarization and multimodal sentiment analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Vite dev server (http + https + LAN IPs)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads_router)
app.include_router(auth_router)
app.include_router(users_router)


# ── REST endpoints ────────────────────────────────────────────────────── #

@app.get("/status", response_model=PipelineStatus)
async def get_status() -> PipelineStatus:
    orc = _orchestrator
    return PipelineStatus(
        running=orc._running if orc else False,
        device=settings.resolved_device,
        whisper_model=settings.whisper_model,
        source_lang=orc._dg_language if orc else None,
    )


@app.post("/start", response_model=dict)
async def start_pipeline(
    req: StartRequest = StartRequest(),
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    if _orchestrator is None:
        return {"error": "Orchestrator not initialised"}
    if _orchestrator._running:
        return {"status": "already running"}
    await _orchestrator.start(
        source_lang=req.source_lang,
        deepgram_model=req.deepgram_model,
        diarize=req.diarize,
        endpointing=req.endpointing,
        punctuate=req.punctuate,
        use_deepgram=req.use_deepgram,
        created_by=current_user["username"] if current_user else None,
    )
    return {"status": "started"}


@app.post("/stop", response_model=dict)
async def stop_pipeline() -> dict:
    if _orchestrator is None:
        return {"error": "Orchestrator not initialised"}
    await _orchestrator.stop()
    return {"status": "stopped"}


# ── WebSocket endpoint ────────────────────────────────────────────────── #

@app.websocket("/ws")
async def ws_handler(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket, _broadcast_queue)


@app.websocket("/ws/speaker/{speaker_id}")
async def ws_browser_mic(websocket: WebSocket, speaker_id: str) -> None:
    """Browser-mic audio stream for a specific speaker.

    The client sends raw PCM chunks (float32, 16kHz, mono) as binary frames.
    Each chunk is transcribed in isolation via the speaker's own Transcriber.
    """
    await websocket.accept()
    logger.info("Browser mic connected: %s", speaker_id)
    loop = asyncio.get_running_loop()
    import numpy as np
    try:
        while True:
            data = await websocket.receive_bytes()
            if _orchestrator is None or not _orchestrator._running:
                continue
            # PCM float32 LE
            chunk = np.frombuffer(data, dtype=np.float32)
            if chunk.size == 0:
                continue
            asyncio.create_task(
                _orchestrator.process_external_chunk(chunk, speaker_id, loop)
            )
    except WebSocketDisconnect:
        logger.info("Browser mic disconnected: %s", speaker_id)


# ── Entry point ───────────────────────────────────────────────────────── #

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
