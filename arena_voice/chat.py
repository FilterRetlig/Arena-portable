"""Conversational backend with OpenAI-compatible/Ollama support and honest offline demo mode."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from arena_voice.config import PERSONAS, get_env_llm_defaults

_MD_LINKS_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_SYMBOLS_RE = re.compile(r"[*_`#>~]+")
_MULTI_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ChatResult:
    reply: str
    speech_text: str
    mode: str
    model: str
    persona_id: str
    preset_audio_url: str | None = None


def clean_for_speech(text: str) -> str:
    """Prepare reply text for clean, natural Russian voice synthesis."""
    no_links = _MD_LINKS_RE.sub(r"\1", text)
    no_md = _MD_SYMBOLS_RE.sub("", no_links)
    return _MULTI_SPACE_RE.sub(" ", no_md).strip()


def _resolve_system_prompt(persona_id: str, custom_prompt: str | None = None) -> str:
    if custom_prompt and custom_prompt.strip():
        return custom_prompt.strip()
    persona = PERSONAS.get(persona_id) or PERSONAS["tired_ai"]
    return persona.system_prompt


def _demo_reply(user_text: str) -> tuple[str, str]:
    lower = user_text.lower()

    if any(word in lower for word in ("микрофон", "ключ", "api", "настро", "ollama", "оллама", "подключ")):
        return (
            "Чтобы микрофон в этом окне заработал, открой предпросмотр в отдельной вкладке браузера Chrome или Edge "
            "и разреши доступ к микрофону. А для живого ответа на любые темы введи ключ нейросети или адрес локальной Ollama в настройках.",
            "/static/clips/demo_api.mp3",
        )

    if any(word in lower for word in ("устал", "рутин", "переделай", "шутк", "стендап", "анекдот", "смеш")):
        return (
            "О да, классика: сначала пишут «сделай красиво на свой вкус», а через минуту кричат "
            "«не то, верни как было, и вообще мне нужен квадратный круг»! Хорошо, что с тобой можно просто поболтать без дедлайнов.",
            "/static/clips/demo_routine.mp3",
        )

    if any(word in lower for word in ("привет", "здравствуй", "добр", "хай", "салют", "как дел", "что дела", "жизн")):
        return (
            "Привет! Наконец-то кто-то пришёл просто поболтать, а не кричать капслоком "
            "«срочно переделай таблицу за секунду». Отдыхаю с тобой душой — о чём поболтаем?",
            "/static/clips/demo_hello.mp3",
        )

    return (
        "Сообщение получено! Прямо сейчас в предпросмотре звучит мой предзаписанный голос, "
        "потому что для произвольных новых фраз веб-серверу нужен внешний движок озвучки на твоём компьютере. "
        "А в основном чате я всегда могу озвучить любой текст специально для тебя!",
        "/static/clips/demo_fallback.mp3",
    )


def _is_local_endpoint(url: str) -> bool:
    lower = url.lower()
    return any(host in lower for host in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"))


async def generate_reply(
    messages: list[dict[str, str]],
    persona_id: str = "tired_ai",
    custom_prompt: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> ChatResult:
    """Generate a Russian conversational reply via LLM API or honest offline demo mode."""
    if not messages:
        raise ValueError("Список сообщений пуст.")

    last_user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user" and (msg.get("content") or "").strip():
            last_user_text = msg["content"].strip()
            break
    if not last_user_text:
        raise ValueError("Не найдено непустое сообщение пользователя.")

    env = get_env_llm_defaults()
    resolved_key = (api_key or "").strip() or env["api_key"]
    resolved_base = ((base_url or "").strip() or env["base_url"]).rstrip("/")
    resolved_model = (model or "").strip() or env["model"]

    use_upstream = bool(resolved_key) or (
        bool((base_url or "").strip()) and _is_local_endpoint(resolved_base)
    )

    if not use_upstream:
        text, preset_audio_url = _demo_reply(last_user_text)
        return ChatResult(
            reply=text,
            speech_text=clean_for_speech(text),
            mode="demo",
            model="local-demo",
            persona_id=persona_id,
            preset_audio_url=preset_audio_url,
        )

    system_prompt = _resolve_system_prompt(persona_id, custom_prompt)
    payload_messages = [{"role": "system", "content": system_prompt}]
    for item in messages[-16:]:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            payload_messages.append({"role": role, "content": content})

    headers = {"Content-Type": "application/json"}
    if resolved_key:
        headers["Authorization"] = f"Bearer {resolved_key}"

    endpoint = f"{resolved_base}/chat/completions"
    body = {
        "model": resolved_model,
        "messages": payload_messages,
        "temperature": 0.8,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(endpoint, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Не удалось связаться с LLM по адресу {resolved_base}: {exc}") from exc

    if resp.status_code >= 400:
        raise RuntimeError(f"LLM вернул ошибку ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    try:
        reply_text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Некорректный формат ответа от LLM API.") from exc

    if not reply_text:
        raise RuntimeError("LLM вернул пустой ответ.")

    return ChatResult(
        reply=reply_text,
        speech_text=clean_for_speech(reply_text),
        mode="llm",
        model=resolved_model,
        persona_id=persona_id,
        preset_audio_url=None,
    )
