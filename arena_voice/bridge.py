"""Shared workspace file bridge between Live Preview and Arena chat turns."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def get_bridge_dir() -> Path:
    env_dir = os.environ.get("ARENA_VOICE_BRIDGE_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent / "bridge"


def get_bridge_file() -> Path:
    return get_bridge_dir() / "chat.json"


def get_bridge_audio_dir() -> Path:
    return get_bridge_dir() / "audio"


def _now_hhmm() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M")


def _default_state() -> dict:
    return {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "messages": [
            {
                "id": "bridge-welcome",
                "role": "assistant",
                "text": (
                    "Мост с Arena запущен! Напиши или надиктуй (Win + H) сообщение прямо сюда, "
                    "затем отправь в чат Arena короткий сигнал вроде «ответь» — и мой голосовой ответ появится здесь автоматически."
                ),
                "audio_url": "/api/bridge/audio/bridge_welcome.mp3",
                "created_at": _now_hhmm(),
                "status": "done",
            }
        ],
    }


def load_bridge_state() -> dict:
    bridge_file = get_bridge_file()
    if not bridge_file.exists():
        state = _default_state()
        save_bridge_state(state)
        return state
    try:
        data = json.loads(bridge_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise ValueError("Invalid bridge schema")
        return data
    except Exception:
        state = _default_state()
        save_bridge_state(state)
        return state


def save_bridge_state(state: dict) -> dict:
    bridge_dir = get_bridge_dir()
    audio_dir = get_bridge_audio_dir()
    bridge_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    bridge_file = get_bridge_file()
    tmp_file = bridge_dir / f".chat.{os.getpid()}.{time.time_ns()}.tmp"
    tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_file, bridge_file)
    return state


def append_user_message(text: str) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise ValueError("Сообщение не должно быть пустым.")

    state = load_bridge_state()
    state["version"] = int(state.get("version", 0)) + 1
    msg = {
        "id": f"bu-{time.time_ns()}",
        "role": "user",
        "text": clean,
        "audio_url": None,
        "created_at": _now_hhmm(),
        "status": "pending",
    }
    state["messages"].append(msg)
    return save_bridge_state(state)


def append_assistant_reply(
    text: str,
    audio_filename: str | None = None,
    mark_pending_done: bool = True,
) -> dict:
    clean = (text or "").strip()
    if not clean:
        raise ValueError("Текст ответа не должен быть пустым.")

    state = load_bridge_state()
    if mark_pending_done:
        for msg in state["messages"]:
            if msg.get("role") == "user" and msg.get("status") == "pending":
                msg["status"] = "answered"

    audio_url = None
    if audio_filename:
        safe_name = Path(audio_filename).name
        audio_url = f"/api/bridge/audio/{safe_name}"

    state["version"] = int(state.get("version", 0)) + 1
    state["messages"].append(
        {
            "id": f"ba-{time.time_ns()}",
            "role": "assistant",
            "text": clean,
            "audio_url": audio_url,
            "created_at": _now_hhmm(),
            "status": "done",
        }
    )
    return save_bridge_state(state)


def get_pending_user_messages() -> list[dict]:
    state = load_bridge_state()
    return [
        m for m in state["messages"]
        if m.get("role") == "user" and m.get("status") == "pending"
    ]


def clear_bridge_state() -> dict:
    state = _default_state()
    state["version"] = int(load_bridge_state().get("version", 1)) + 1
    return save_bridge_state(state)


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI управления мостом Arena Live Preview")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pending", help="Показать неотвеченные сообщения из предпросмотра")

    reply_p = sub.add_parser("reply", help="Отправить голосовой ответ в предпросмотр")
    reply_p.add_argument("--text", required=True, help="Текст ответа")
    reply_p.add_argument("--audio", default=None, help="Имя или путь к MP3-файлу внутри bridge/audio/")

    sub.add_parser("clear", help="Очистить историю моста")

    args = parser.parse_args()
    if args.cmd == "pending":
        pending = get_pending_user_messages()
        print(json.dumps(pending, ensure_ascii=False, indent=2))
    elif args.cmd == "reply":
        updated = append_assistant_reply(text=args.text, audio_filename=args.audio)
        print(f"Отправлено (версия {updated['version']}).")
    elif args.cmd == "clear":
        updated = clear_bridge_state()
        print(f"Очищено (версия {updated['version']}).")


if __name__ == "__main__":
    main()
