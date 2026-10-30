@echo off
setlocal
if "%~1"=="" (
  echo Ziehe die JSON-Datei aus der ELSTER-Eingabehilfe auf diese Datei.
  pause
  exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0app\mein_elster_browser.py" --eingabe "%~1" --ausfuellen
if errorlevel 1 pause
