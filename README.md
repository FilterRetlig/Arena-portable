# Arena Voice (`Arena-portable`)

Модуль и веб-студия для двустороннего голосового общения с ИИ на русском языке.

## Что внутри

- **`arena_voice/server.py`** — FastAPI-сервер и веб-чат в стиле голосового мессенджера (`/`, `/api/chat`, `/api/tts`, `/api/stt`, `/api/health`).
- **`arena_voice/tts.py`** — русский синтез речи через `edge-tts` (`ru-RU-DmitryNeural`, `ru-RU-SvetlanaNeural`), с поддержкой скорости/тона и CLI.
- **`arena_voice/stt.py`** — распознавание загруженных аудиосообщений через OpenAI-совместимый Whisper API или опциональный локальный `faster-whisper`.
- **`arena_voice/chat.py`** — диалоговый модуль с тремя готовыми персонами (*«Уставший от рутины ИИ»*, *«Тёплый собеседник»*, *«Стендапер-нейросеть»*), поддержкой OpenAI / OpenRouter / Groq / локальной Ollama и встроенным тестовым режимом без API-ключа.
- **Веб-интерфейс (`arena_voice/static/`)** — работает прямо в браузере через Web Speech API (`ru-RU`) и автоматически переключается на серверный `edge-tts` при локальном запуске с интернетом.

## Быстрый старт на своём компьютере (1 клик)

1. Скачайте ветку репозитория к себе:
   ```bash
   git clone -b arena/9387a394-arena-portable https://github.com/FilterRetlig/Arena-portable.git
   cd Arena-portable
   ```
2. Запустите локальный сайт:
   - **Windows:** дважды кликните по файлу **`start_windows.bat`**
   - **Linux / macOS:** выполните **`./start_linux_mac.sh`**

Скрипт сам создаст `.venv`, установит зависимости и откроет локальный сайт по ссылке **`http://localhost:8000`** (рекомендуется **Google Chrome** или **Microsoft Edge**, чтобы сразу работала кнопка микрофона 🎙️).

<details>
<summary>Ручной запуск через терминал</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m arena_voice.server --open
```

</details>

## Подключение настоящего ИИ (опционально)

Ключ можно ввести прямо в интерфейсе (кнопка настроек ⚙) или задать переменными окружения перед запуском:

```bash
export ARENA_VOICE_BASE_URL="https://api.openai.com/v1"
export ARENA_VOICE_API_KEY="sk-..."
export ARENA_VOICE_MODEL="gpt-4o-mini"
```

Для полностью локальной работы без ключей можно указать локальную **Ollama**:
- `Base URL`: `http://localhost:11434/v1`
- `Model`: `qwen2.5:7b` (или любая установленная модель)
- `API Key`: оставить пустым

## CLI-озвучка русского текста

```bash
python -m arena_voice.tts "Привет! Наконец-то общаемся голосом." -o reply.mp3 --voice ru-RU-DmitryNeural
```

## Тесты

```bash
pytest -v
```
