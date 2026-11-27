@echo off
rem Double-click to start Teach Bot. Close this window (or press Ctrl+C) to stop it.
cd /d "%~dp0"
title Teach Bot
if not exist ".env" (
  echo No .env file found. Copy .env.example to .env and put your API key in it.
  pause
  exit /b 1
)
echo Starting Teach Bot... your browser will open in a moment.
echo Keep this window open while you use the app.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:7860"
py -m uvicorn app.server:app --port 7860
if errorlevel 1 (
  echo.
  echo The app stopped with an error. The message above says why.
  pause
)
