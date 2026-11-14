@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY_CMD=python"
    ) else (
        echo [ОШИБКА] Python 3 не найден. Установите Python 3.10+ с python.org и повторите запуск.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение .venv...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать .venv.
        pause
        exit /b 1
    )
    echo Устанавливаю зависимости...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b 1
    )
)

echo Запускаю локальный сайт Arena Voice...
echo Ссылка: http://localhost:8000
.venv\Scripts\python.exe -m arena_voice.server --open
pause
