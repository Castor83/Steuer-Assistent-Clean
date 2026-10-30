@echo off
title Steuer-Assistent - ELSTER-Leitfaden aktualisieren
cd /d "%~dp0"
echo Der amtliche ELSTER-Leitfaden wird geprueft und aktualisiert.
echo Dies kann wegen der lokalen Verarbeitung einige Minuten dauern.
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0app\elster_leitfaden_aktualisieren.py"
echo.
if errorlevel 1 (
  echo Die Aktualisierung konnte nicht abgeschlossen werden.
) else (
  echo Der ELSTER-Leitfaden ist vollstaendig aktualisiert.
)
pause
