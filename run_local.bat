@echo off
rem One-click local check on Windows. Double-click this file, or run it from a terminal.
rem It creates a virtual environment, installs the pinned requirements, runs the unit
rem tests and the dry runs, then checks Ollama. Everything is written to logs\local_run.txt.
rem It installs nothing outside this folder and never changes system settings.
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=logs\local_run.txt"
echo ==== run_local.bat  %DATE% %TIME% ==== > "%LOG%"

echo [1/6] Looking for Python 3.11 or newer ...
set "PY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY if exist "%USERPROFILE%\miniconda3\python.exe" "%USERPROFILE%\miniconda3\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set PY="%USERPROFILE%\miniconda3\python.exe"
if not defined PY (
    echo [1/6] FAILED: Python 3.11+ not found >> "%LOG%"
    echo        FAILED: Python 3.11 or newer was not found on this machine.
    goto :finish
)
echo [1/6] python command: %PY% >> "%LOG%"
%PY% --version >> "%LOG%" 2>&1

echo [2/6] Creating the virtual environment (.venv) ...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv >> "%LOG%" 2>&1
if not exist ".venv\Scripts\python.exe" (
    echo [2/6] FAILED: could not create .venv >> "%LOG%"
    echo        FAILED: could not create .venv
    goto :finish
)
echo [2/6] OK >> "%LOG%"

echo [3/6] Installing requirements (needs internet, a few minutes) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG%" 2>&1
echo [3/6] pip exit code: %ERRORLEVEL% >> "%LOG%"
if errorlevel 1 (
    echo        FAILED: pip install. See %LOG%
    goto :finish
)

echo [4/6] Running the unit tests ...
".venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider >> "%LOG%" 2>&1
echo [4/6] pytest exit code: %ERRORLEVEL% >> "%LOG%"

echo [5/6] Dry runs with the mock client (no model needed) ...
".venv\Scripts\python.exe" -m src.evaluate --client mock --golden data\golden_test.jsonl --min-rows 100 >> "%LOG%" 2>&1
echo [5/6] evaluate exit code: %ERRORLEVEL% >> "%LOG%"
".venv\Scripts\python.exe" -m src.safety_check --client mock >> "%LOG%" 2>&1
echo [5/6] safety_check exit code: %ERRORLEVEL% >> "%LOG%"

echo [6/6] Checking Ollama ...
where ollama >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [6/6] OLLAMA NOT INSTALLED: the 'ollama' command was not found >> "%LOG%"
    echo        Ollama is not installed, or it is not on PATH.
    goto :finish
)
ollama --version >> "%LOG%" 2>&1
ollama list >nul 2>&1
if errorlevel 1 (
    echo [6/6] Ollama server not running; starting it >> "%LOG%"
    start "ollama serve" /MIN ollama serve
    timeout /t 8 /nobreak >nul
)
echo [6/6] installed models: >> "%LOG%"
ollama list >> "%LOG%" 2>&1

echo.
echo The base model qwen3:1.7b is needed for a real smoke test (a download of roughly 1-2 GB).
choice /C YN /M "Download qwen3:1.7b now and run the base model on the 10 template sentences"
if errorlevel 2 goto :finish
echo [6/6] pulling qwen3:1.7b >> "%LOG%"
ollama pull qwen3:1.7b
echo [6/6] pull exit code: %ERRORLEVEL% >> "%LOG%"
if errorlevel 1 goto :finish
echo        Running the untuned model on the template sentences (smoke test, not a result) ...
".venv\Scripts\python.exe" -m src.evaluate --systems baseline --base-model qwen3:1.7b --golden data\golden_test.jsonl --min-rows 100 --out results\smoke_base_model >> "%LOG%" 2>&1
echo [6/6] smoke test exit code: %ERRORLEVEL% >> "%LOG%"

:finish
echo ==== finished %DATE% %TIME% ==== >> "%LOG%"
echo.
echo Finished. The full log is in %LOG%
echo To open the app:  .venv\Scripts\streamlit run app\streamlit_app.py
pause
endlocal
