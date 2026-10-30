# Führt den echten BFH-Antworttest aus und stellt danach den Normalbetrieb wieder her.
$projekt = Split-Path -Parent $PSScriptRoot
$starter = Join-Path $PSScriptRoot "ui_neu_starten.ps1"
$python = Join-Path $projekt ".venv\Scripts\python.exe"
$test = Join-Path $projekt "tests\bfh_antworttest.py"
$ergebnis = 1

try {
    & $starter -BfhTestmodus -KeinBrowser
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 2
    if (-not $status.bereit -or -not $status.bfh_testmodus) {
        throw "Der BFH-Testmodus konnte nicht gestartet werden."
    }
    & $python $test
    $ergebnis = $LASTEXITCODE
}
catch {
    Write-Host "BFH-Antworttest fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    $ergebnis = 1
}
finally {
    & $starter -KeinBrowser
    try {
        $normalstatus = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 2
        $normalbetrieb = $normalstatus.bereit -and -not $normalstatus.bfh_testmodus
    }
    catch {
        $normalbetrieb = $false
    }
    if (-not $normalbetrieb) {
        Write-Host "Achtung: Der normale Steuer-Assistent konnte nicht wieder gestartet werden." -ForegroundColor Red
        $ergebnis = 1
    }
}

if ($ergebnis -eq 0) {
    Write-Host "BFH-Antworttest erfolgreich. Der normale 9B-Betrieb ist wieder aktiv." -ForegroundColor Green
}
exit $ergebnis
