# Elmer Worker — PowerShell startup script
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Elmer Worker — Starting..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Create venv if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv
& .\.venv\Scripts\Activate.ps1

# Install / update dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

# Start the worker
Write-Host "Starting Elmer Worker on 0.0.0.0:8101..." -ForegroundColor Green
python -m uvicorn src.main:app --host 0.0.0.0 --port 8101 --reload
