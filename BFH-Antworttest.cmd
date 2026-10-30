@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\bfh_antworttest_starten.ps1"
set "TEST_ERGEBNIS=%ERRORLEVEL%"
echo.
if "%TEST_ERGEBNIS%"=="0" (
  echo Alle BFH-Antworttests wurden bestanden.
) else (
  echo Mindestens ein BFH-Antworttest ist fehlgeschlagen.
)
pause
exit /b %TEST_ERGEBNIS%
