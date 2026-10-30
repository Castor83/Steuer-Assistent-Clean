@echo off
cd /d "%~dp0"
echo Starte den QLoRA-Piloten fuer Qwen 3.5 9B.
echo Basismodell: C:\Steuer-Assistent-Modelle\Qwen3.5-9B
echo Startadapter: C:\Steuer-Assistent-Modelle\adapter-umgangssprache-pilot-01\checkpoint-25
echo Ausgabe:      C:\Steuer-Assistent-Modelle\adapter-umgangssprache-pilot-01-fortsetzung
echo.
".venv-training\Scripts\python.exe" "training\qlora_pilot.py" --max-steps 175 --max-train-samples 0 --max-eval-samples 0 --gradient-accumulation 1 --max-length 88 --save-steps 25 --adapter-start "C:\Steuer-Assistent-Modelle\adapter-umgangssprache-pilot-01\checkpoint-25" --resume-latest --ausgabe "C:\Steuer-Assistent-Modelle\adapter-umgangssprache-pilot-01-fortsetzung" --bericht "tests\ergebnisse\qlora_umgangssprache_pilot_01.json"
echo.
if errorlevel 1 (
  echo Der Pilot wurde nicht erfolgreich beendet. Der letzte 25er-Checkpoint bleibt erhalten.
) else (
  echo Der Pilot wurde erfolgreich beendet.
)
pause
