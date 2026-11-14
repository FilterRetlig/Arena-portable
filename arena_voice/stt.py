"""Speech-to-text transcription helpers for uploaded audio messages."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from arena_voice.config import get_env_llm_defaults


class STTUnavailableError(RuntimeError):
    """Raised when no server-side speech-to-text backend is configured."""


@dataclass(frozen=True)
class STTResult:
    text: str
    provider: str


def _try_local_faster_whisper(audio_bytes: bytes, suffix: str, language: str) -> str | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None

    with tempfile.NamedTemporaryFile(suffix=suffix or ".webm") as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(tmp.name, language=language)
        return " ".join(seg.text.strip() for seg in segments).strip()


async def transcribe_audio_bytes(
    audio_bytes: bytes,
    filename: str = "voice.webm",
    content_type: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "whisper-1",
    language: str = "ru",
) -> STTResult:
    """Transcribe an audio clip via OpenAI-compatible Whisper API or local faster-whisper."""
    if not audio_bytes:
        raise ValueError("Пустой аудиофайл.")

    env = get_env_llm_defaults()
    resolved_key = (api_key or "").strip() or env["api_key"]
    resolved_base = ((base_url or "").strip() or env["base_url"]).rstrip("/")

    if resolved_key:
        url = f"{resolved_base}/audio/transcriptions"
        mime = content_type or "audio/webm"
        files = {"file": (filename or "voice.webm", audio_bytes, mime)}
        data = {"model": model or "whisper-1", "language": language or "ru"}
        headers = {"Authorization": f"Bearer {resolved_key}"}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code >= 400:
                raise RuntimeError(f"Ошибка STT-сервера ({resp.status_code}): {resp.text[:300]}")
            payload = resp.json()
            text = (payload.get("text") or "").strip()
            if not text:
                raise RuntimeError("Сервер распознавания речи вернул пустой текст.")
            return STTResult(text=text, provider="whisper-api")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Сетевая ошибка при обращении к Whisper API: {exc}") from exc

    suffix = Path(filename).suffix or ".webm"
    local_text = _try_local_faster_whisper(audio_bytes, suffix=suffix, language=language)
    if local_text is not None:
        return STTResult(text=local_text, provider="faster-whisper")

    raise STTUnavailableError(
        "Серверное распознавание аудиофайлов требует API-ключ с поддержкой Whisper "
        "или установленный пакет faster-whisper. Для мгновенного голосового ввода без ключей "
        "используйте кнопку микрофона в Chrome/Edge или диктовку системы."
    )
