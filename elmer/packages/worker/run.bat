@echo off
REM Elmer Worker — Windows startup script
echo Starting Elmer Worker...

REM Activate venv if it exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -m uvicorn src.main:app --host 0.0.0.0 --port 8101 --reload
