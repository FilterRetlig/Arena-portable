#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ОШИБКА] python3 не найден. Установите Python 3.10+ и повторите запуск."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Создаю виртуальное окружение .venv..."
  python3 -m venv .venv
  echo "Устанавливаю зависимости..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

echo "Запускаю локальный сайт Arena Voice: http://localhost:8000"
exec .venv/bin/python -m arena_voice.server --open
