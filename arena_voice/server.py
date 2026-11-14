"""FastAPI server for the Russian voice messaging studio."""

from __future__ import annotations

import os
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from arena_voice.bridge import (
    append_user_message,
    clear_bridge_state,
    get_bridge_audio_dir,
    load_bridge_state,
)
from arena_voice.chat import generate_reply
from arena_voice.config import DEFAULT_VOICE, PERSONAS, RUSSIAN_VOICES, get_env_llm_defaults
from arena_voice.stt import STTUnavailableError, transcribe_audio_bytes
from arena_voice.tts import synthesize_speech_bytes

STATIC_DIR = Path(__file__).resolve().parent / "static"
_SAFE_AUDIO_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.(mp3|wav|ogg|m4a)$")

app = FastAPI(
    title="Arena Voice Studio",
    description="Русский голосовой чат-модуль для Arena-portable",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def disable_ui_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


class ChatMessageIn(BaseModel):
    role: str
    content: str


class LLMConfigIn(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ChatRequestIn(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1)
    persona_id: str = "tired_ai"
    custom_prompt: str | None = None
    llm_config: LLMConfigIn | None = None


class TTSRequestIn(BaseModel):
    text: str = Field(min_length=1)
    voice: str = DEFAULT_VOICE
    rate_pct: int = 0
    pitch_hz: int = 0


class BridgeMessageIn(BaseModel):
    text: str = Field(min_length=1)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    env = get_env_llm_defaults()
    return {
        "status": "ok",
        "has_env_llm": bool(env["api_key"]),
        "default_base_url": env["base_url"],
        "default_model": env["model"],
        "personas": [asdict(p) for p in PERSONAS.values()],
        "voices": [asdict(v) for v in RUSSIAN_VOICES],
    }


@app.get("/api/personas")
async def get_personas() -> list[dict]:
    return [asdict(p) for p in PERSONAS.values()]


@app.get("/api/voices")
async def get_voices() -> list[dict]:
    return [asdict(v) for v in RUSSIAN_VOICES]


@app.post("/api/chat")
async def api_chat(req: ChatRequestIn) -> dict:
    cfg = req.llm_config or LLMConfigIn()
    try:
        result = await generate_reply(
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            persona_id=req.persona_id,
            custom_prompt=req.custom_prompt,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "reply": result.reply,
        "speech_text": result.speech_text,
        "mode": result.mode,
        "model": result.model,
        "persona_id": result.persona_id,
        "preset_audio_url": result.preset_audio_url,
    }


@app.post("/api/tts")
async def api_tts(req: TTSRequestIn) -> Response:
    try:
        audio_bytes = await synthesize_speech_bytes(
            text=req.text,
            voice=req.voice,
            rate_pct=req.rate_pct,
            pitch_hz=req.pitch_hz,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/stt")
async def api_stt(
    file: UploadFile = File(...),
    api_key: str = Form(default=""),
    base_url: str = Form(default=""),
    model: str = Form(default="whisper-1"),
    language: str = Form(default="ru"),
) -> dict:
    audio_bytes = await file.read()
    try:
        result = await transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            filename=file.filename or "voice.webm",
            content_type=file.content_type,
            api_key=api_key,
            base_url=base_url,
            model=model,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except STTUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"text": result.text, "provider": result.provider}


@app.get("/api/bridge/messages")
async def api_bridge_messages() -> JSONResponse:
    state = load_bridge_state()
    pending_count = sum(
        1 for m in state["messages"]
        if m.get("role") == "user" and m.get("status") == "pending"
    )
    return JSONResponse(
        content={
            "version": state.get("version", 1),
            "updated_at": state.get("updated_at"),
            "pending_count": pending_count,
            "messages": state["messages"],
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/bridge/send")
async def api_bridge_send(req: BridgeMessageIn) -> JSONResponse:
    try:
        state = append_user_message(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pending_count = sum(
        1 for m in state["messages"]
        if m.get("role") == "user" and m.get("status") == "pending"
    )
    return JSONResponse(
        content={
            "version": state.get("version", 1),
            "updated_at": state.get("updated_at"),
            "pending_count": pending_count,
            "messages": state["messages"],
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/bridge/clear")
async def api_bridge_clear() -> JSONResponse:
    state = clear_bridge_state()
    return JSONResponse(
        content={
            "version": state.get("version", 1),
            "updated_at": state.get("updated_at"),
            "pending_count": 0,
            "messages": state["messages"],
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/bridge/audio/{filename}")
async def api_bridge_audio(filename: str) -> FileResponse:
    if not _SAFE_AUDIO_NAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Недопустимое имя аудиофайла.")

    audio_dir = get_bridge_audio_dir().resolve()
    target = (audio_dir / filename).resolve()
    if target.parent != audio_dir:
        raise HTTPException(status_code=400, detail="Недопустимый путь.")

    if not target.exists():
        if filename == "bridge_welcome.mp3":
            fallback = STATIC_DIR / "clips" / "welcome.mp3"
            if fallback.exists():
                return FileResponse(fallback, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
        raise HTTPException(status_code=404, detail="Аудиофайл не найден.")

    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type, headers={"Cache-Control": "no-store"})


def run() -> None:
    import argparse
    import threading
    import webbrowser
    import uvicorn

    parser = argparse.ArgumentParser(description="Arena Voice Studio server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("ARENA_VOICE_PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("ARENA_VOICE_HOST", "0.0.0.0"))
    parser.add_argument(
        "--open",
        action="store_true",
        default=os.environ.get("ARENA_VOICE_OPEN_BROWSER", "").lower() in {"1", "true", "yes"},
        help="Автоматически открыть http://localhost:<port> в браузере",
    )
    args = parser.parse_args()

    local_url = f"http://localhost:{args.port}"
    print(f"\n>>> Локальный сайт Arena Voice запущен: {local_url}\n")
    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(local_url)).start()

    uvicorn.run("arena_voice.server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    run()
