"""Russian text-to-speech synthesis powered by edge-tts."""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import edge_tts

from arena_voice.config import DEFAULT_VOICE

_MARKDOWN_CLEAN_RE = re.compile(r"[*_`~#>]+")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_text_for_tts(text: str) -> str:
    """Strip markdown artifacts so spoken Russian sounds natural."""
    cleaned = _MARKDOWN_CLEAN_RE.sub("", text)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def format_rate(rate_pct: int) -> str:
    clamped = max(-50, min(100, int(rate_pct)))
    return f"{clamped:+d}%"


def format_pitch(pitch_hz: int) -> str:
    clamped = max(-50, min(50, int(pitch_hz)))
    return f"{clamped:+d}Hz"


async def synthesize_speech_bytes(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate_pct: int = 0,
    pitch_hz: int = 0,
) -> bytes:
    """Synthesize Russian speech to MP3 bytes using edge-tts."""
    cleaned = clean_text_for_tts(text)
    if not cleaned:
        raise ValueError("Текст для озвучки не должен быть пустым.")

    communicate = edge_tts.Communicate(
        cleaned,
        voice=voice or DEFAULT_VOICE,
        rate=format_rate(rate_pct),
        pitch=format_pitch(pitch_hz),
    )

    chunks: list[bytes] = []
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.append(chunk["data"])
    except Exception as exc:  # pragma: no cover - network dependent
        raise RuntimeError(
            "Не удалось подключиться к серверу edge-tts. "
            "В изолированной среде используйте браузерную озвучку, а на своём ПК проверьте доступ к сети."
        ) from exc

    audio = b"".join(chunks)
    if not audio:
        raise RuntimeError("Сервис edge-tts вернул пустой аудиопоток.")
    return audio


async def synthesize_to_file(
    text: str,
    output_path: str | Path,
    voice: str = DEFAULT_VOICE,
    rate_pct: int = 0,
    pitch_hz: int = 0,
) -> Path:
    """Synthesize speech and write MP3 audio directly to disk."""
    audio = await synthesize_speech_bytes(
        text=text,
        voice=voice,
        rate_pct=rate_pct,
        pitch_hz=pitch_hz,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Озвучка русского текста через edge-tts")
    parser.add_argument("text", help="Текст на русском языке для озвучки")
    parser.add_argument("-o", "--output", default="output.mp3", help="Путь к MP3-файлу")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="ID голоса edge-tts")
    parser.add_argument("--rate", type=int, default=0, help="Скорость в процентах (-50..100)")
    parser.add_argument("--pitch", type=int, default=0, help="Высота тона в Гц (-50..50)")
    args = parser.parse_args()

    out = asyncio.run(
        synthesize_to_file(
            text=args.text,
            output_path=args.output,
            voice=args.voice,
            rate_pct=args.rate,
            pitch_hz=args.pitch,
        )
    )
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
