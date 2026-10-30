@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\lmstudio_steuer_runtime_starten.ps1"
if errorlevel 1 pause
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\lmstudio_embedding_runtime_starten.ps1"
if errorlevel 1 pause
