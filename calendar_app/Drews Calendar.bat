@echo off
rem Launch Drew's Calendar without a console window (falls back to python).
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw app.py
) else (
    python app.py
)
