@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"

if not exist "requirements.txt" goto :missing_files
if not exist "arena_voice\server.py" goto :missing_files

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto :use_py3

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto :use_python

python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto :use_python3

echo [ОШИБКА] Python 3.10 или новее не найден.
echo Скачайте Python с https://www.python.org/downloads/ и при установке отметьте "Add python.exe to PATH".
echo.
pause
exit /b 1

:use_py3
set "PY_EXE=py -3"
goto :found_python

:use_python
set "PY_EXE=python"
goto :found_python

:use_python3
set "PY_EXE=python3"
goto :found_python

:missing_files
echo [ОШИБКА] Не найдены файлы проекта рядом с start_windows.bat.
echo Если вы скачали ZIP-архив, сначала полностью распакуйте его в обычную папку (Извлечь все...).
echo.
pause
exit /b 1

:found_python
echo Найден Python: %PY_EXE%
if exist ".venv\Scripts\python.exe" goto :check_deps

echo Создаю виртуальное окружение .venv...
%PY_EXE% -m venv .venv
if errorlevel 1 goto :venv_error

:check_deps
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, httpx, edge_tts, multipart" >nul 2>nul
if not errorlevel 1 goto :start_server

echo Устанавливаю зависимости проекта (один раз при первом запуске)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_error

:start_server
echo.
echo ======================================================
echo   Локальный сайт Arena Voice: http://localhost:8000
echo   Для остановки закройте это окно или нажмите Ctrl+C
echo ======================================================
echo.
".venv\Scripts\python.exe" -m arena_voice.server --open
if errorlevel 1 goto :server_error
pause
exit /b 0

:venv_error
echo.
echo [ОШИБКА] Не удалось создать виртуальное окружение .venv.
pause
exit /b 1

:pip_error
echo.
echo [ОШИБКА] Не удалось установить библиотеки из requirements.txt. Проверьте интернет.
pause
exit /b 1

:server_error
echo.
echo [ОШИБКА] Сервер завершился с ошибкой. Возможно, порт 8000 уже занят другой программой.
pause
exit /b 1
