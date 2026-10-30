@echo off
title Steuer-Assistent - Heimnetz-Konto verwalten
cd /d "%~dp0"
".venv\Scripts\python.exe" "app\authentifizierung.py" --konto-setzen
echo.
pause
