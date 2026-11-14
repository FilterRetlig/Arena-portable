"""Tests for the arena_voice Russian voice messaging module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from arena_voice.bridge import append_assistant_reply, get_pending_user_messages
from arena_voice.chat import clean_for_speech, generate_reply
from arena_voice.server import app
from arena_voice.stt import STTResult
from arena_voice.tts import clean_text_for_tts, format_pitch, format_rate

client = TestClient(app)


def test_clean_for_speech_removes_markdown() -> None:
    raw = "**Привет**, [ссылка](https://example.com) `код`!"
    assert clean_for_speech(raw) == "Привет, ссылка код!"
    assert clean_text_for_tts("## *Тест* _голоса_") == "Тест голоса"


def test_rate_and_pitch_clamping() -> None:
    assert format_rate(0) == "+0%"
    assert format_rate(25) == "+25%"
    assert format_rate(-100) == "-50%"
    assert format_rate(500) == "+100%"
    assert format_pitch(-10) == "-10Hz"
    assert format_pitch(100) == "+50Hz"


def test_health_and_static_index() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["personas"]) >= 3
    assert len(data["voices"]) >= 2

    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert "Голосовой ИИ" in html_resp.text


def test_chat_demo_mode_returns_russian_reply() -> None:
    resp = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Привет! Ты устал от рутины?"}],
            "persona_id": "tired_ai",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "demo"
    assert data["persona_id"] == "tired_ai"
    assert len(data["reply"]) > 20
    assert data["speech_text"]
    assert data["preset_audio_url"] == "/static/clips/demo_routine.mp3"

    clip_resp = client.get(data["preset_audio_url"])
    assert clip_resp.status_code == 200
    assert len(clip_resp.content) > 10000


def test_chat_empty_messages_returns_422() -> None:
    resp = client.post("/api/chat", json={"messages": []})
    assert resp.status_code == 422


def test_chat_upstream_llm_mocked() -> None:
    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "**Привет!** Готов поболтать голосом."}}]}

    with patch("arena_voice.chat.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = FakeResp()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        resp = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "Привет"}],
                "persona_id": "standup",
                "llm_config": {
                    "api_key": "sk-test-123",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                },
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "llm"
    assert data["model"] == "gpt-4o-mini"
    assert data["speech_text"] == "Привет! Готов поболтать голосом."


def test_tts_endpoint_returns_audio_and_handles_errors() -> None:
    with patch("arena_voice.server.synthesize_speech_bytes", new=AsyncMock(return_value=b"ID3fake-mp3")):
        ok_resp = client.post("/api/tts", json={"text": "Привет мир", "voice": "ru-RU-DmitryNeural"})
        assert ok_resp.status_code == 200
        assert ok_resp.headers["content-type"] == "audio/mpeg"
        assert ok_resp.content == b"ID3fake-mp3"

    with patch("arena_voice.server.synthesize_speech_bytes", new=AsyncMock(side_effect=RuntimeError("offline"))):
        err_resp = client.post("/api/tts", json={"text": "Привет мир"})
        assert err_resp.status_code == 503
        assert "offline" in err_resp.json()["detail"]


def test_stt_endpoint_mocked_and_unconfigured() -> None:
    with patch(
        "arena_voice.server.transcribe_audio_bytes",
        new=AsyncMock(return_value=STTResult(text="Проверка микрофона", provider="whisper-api")),
    ):
        ok_resp = client.post(
            "/api/stt",
            files={"file": ("voice.webm", b"fake-webm-bytes", "audio/webm")},
            data={"api_key": "sk-test"},
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json() == {"text": "Проверка микрофона", "provider": "whisper-api"}

    unconf_resp = client.post(
        "/api/stt",
        files={"file": ("voice.webm", b"fake-webm-bytes", "audio/webm")},
    )
    assert unconf_resp.status_code == 503
    assert "Whisper" in unconf_resp.json()["detail"]


def test_bridge_lifecycle_and_audio_security(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARENA_VOICE_BRIDGE_DIR", str(tmp_path))

    init_resp = client.get("/api/bridge/messages")
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["pending_count"] == 0
    assert init_data["messages"][0]["id"] == "bridge-welcome"

    send_resp = client.post("/api/bridge/send", json={"text": "Привет из предпросмотра!"})
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["pending_count"] == 1
    assert send_data["messages"][-1]["status"] == "pending"

    pending = get_pending_user_messages()
    assert len(pending) == 1
    assert pending[0]["text"] == "Привет из предпросмотра!"

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "reply_01.mp3").write_bytes(b"ID3bridge-mp3")

    append_assistant_reply("Ответ с моста!", audio_filename="reply_01.mp3")
    after_resp = client.get("/api/bridge/messages")
    assert after_resp.status_code == 200
    after_data = after_resp.json()
    assert after_data["pending_count"] == 0
    assert after_data["messages"][-1]["audio_url"] == "/api/bridge/audio/reply_01.mp3"
    assert after_data["messages"][-2]["status"] == "answered"

    audio_resp = client.get("/api/bridge/audio/reply_01.mp3")
    assert audio_resp.status_code == 200
    assert audio_resp.content == b"ID3bridge-mp3"

    bad_resp = client.get("/api/bridge/audio/bad.txt")
    assert bad_resp.status_code == 400

    clear_resp = client.post("/api/bridge/clear")
    assert clear_resp.status_code == 200
    assert len(clear_resp.json()["messages"]) == 1

