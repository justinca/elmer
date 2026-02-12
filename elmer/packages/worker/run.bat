@echo off
REM Elmer Worker — Windows startup script
echo ============================================
echo   Elmer Worker — Starting...
echo ============================================

REM Create venv if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Install / update dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

REM Start the worker
echo Starting Elmer Worker on 0.0.0.0:8101...
python -m uvicorn src.main:app --host 0.0.0.0 --port 8101 --reload
