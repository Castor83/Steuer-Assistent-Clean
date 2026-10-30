param([switch]$KeinBrowser)

# Startet den Steuer-Assistenten im privaten Heimnetz.
$projekt = Split-Path -Parent $PSScriptRoot
$webApp = Join-Path $PSScriptRoot "web_ui.py"
$python = Join-Path $projekt ".venv\Scripts\python.exe"
$lmStudioStart = Join-Path $PSScriptRoot "lmstudio_steuer_runtime_starten.ps1"
$lmStudioEmbeddingStart = Join-Path $PSScriptRoot "lmstudio_embedding_runtime_starten.ps1"

Add-Type -AssemblyName PresentationFramework
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    [System.Windows.MessageBox]::Show(
        "Die lokale Programmlaufzeit fehlt. Der Steuer-Assistent muss repariert oder neu eingerichtet werden.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $projekt "daten\anmeldung.json") -PathType Leaf)) {
    [System.Windows.MessageBox]::Show(
        "Die Heimnetz-Anmeldung ist noch nicht eingerichtet. Starte zuerst 'Heimnetz-Konto-verwalten.cmd'.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*$projekt*" -and
        $_.CommandLine -like "*web_ui.py*"
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$chatBackend = "lmstudio"
try {
    & $lmStudioStart
}
catch {
    try {
        & $lmStudioStart -Stoppen
        & $lmStudioStart -Quantisierung Q4_K_M
    }
    catch {
        [System.Windows.MessageBox]::Show(
            "Weder das Q5-Hauptmodell noch das Q4-GGUF-Ausfallmodell konnte gestartet werden.`n`n$($_.Exception.Message)",
            "Steuer-Assistent Heimnetz - Modellstart fehlgeschlagen"
        ) | Out-Null
        exit 1
    }
}
try {
    & $lmStudioEmbeddingStart
}
catch {
    [System.Windows.MessageBox]::Show(
        "Die lokale GGUF-Embedding-Runtime konnte nicht gestartet werden.`n`n$($_.Exception.Message)",
        "Steuer-Assistent Heimnetz - Embedding-Start fehlgeschlagen"
    ) | Out-Null
    exit 1
}
$env:STEUER_ASSISTENT_HEIMNETZ = "1"
$env:STEUER_CHAT_BACKEND = $chatBackend
$env:STEUER_CHAT_FALLBACK_BACKEND = "gguf"
$env:STEUER_GGUF_FALLBACK_QUANTISIERUNG = "Q4_K_M"
$env:STEUER_EMBEDDING_BACKEND = "lmstudio"
$env:STEUER_LMSTUDIO_URL = "http://127.0.0.1:1235/v1"
$env:STEUER_LMSTUDIO_MODELL = "steuer-assistent-q5"
$env:STEUER_LMSTUDIO_KONTEXT = "32768"
$env:STEUER_LMSTUDIO_EMBEDDING_URL = "http://127.0.0.1:1236/v1"
$env:STEUER_LMSTUDIO_EMBEDDING_MODELL = "qwen3-embedding-4b"
$env:STEUER_VISION_BACKEND = "lmstudio"
$env:STEUER_LMSTUDIO_VISION_URL = "http://127.0.0.1:1237/v1"
try {
    $prozess = Start-Process -FilePath $python -ArgumentList ('"' + $webApp + '"') -WorkingDirectory $projekt -WindowStyle Hidden -PassThru -ErrorAction Stop
}
catch {
    [System.Windows.MessageBox]::Show(
        "Der Heimnetz-Server konnte nicht gestartet werden.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}
finally {
    Remove-Item Env:STEUER_ASSISTENT_HEIMNETZ -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_CHAT_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_CHAT_FALLBACK_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_GGUF_FALLBACK_QUANTISIERUNG -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_EMBEDDING_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_URL -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_MODELL -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_KONTEXT -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_EMBEDDING_URL -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_EMBEDDING_MODELL -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_VISION_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:STEUER_LMSTUDIO_VISION_URL -ErrorAction SilentlyContinue
}

$bereit = $false
for ($versuch = 0; $versuch -lt 30; $versuch++) {
    Start-Sleep -Milliseconds 500
    try {
        $antwort = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 1
        if ($antwort.bereit -and $antwort.heimnetz_modus) { $bereit = $true; break }
    }
    catch {}
}
if (-not $bereit) {
    [System.Windows.MessageBox]::Show(
        "Der Heimnetz-Server ist nach 15 Sekunden noch nicht bereit.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}

$adresse = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254*" -and
        $_.InterfaceAlias -notmatch "vEthernet|WSL|Hyper-V|Virtual|Loopback" -and
        $_.AddressState -eq "Preferred"
    } |
    Sort-Object -Property InterfaceMetric |
    Select-Object -First 1 -ExpandProperty IPAddress
if ([string]::IsNullOrWhiteSpace($adresse)) { $adresse = "IP-DIESES-RECHNERS" }
$url = "http://${adresse}:8765/"
$firewallRegel = Get-NetFirewallRule -DisplayName "Steuer-Assistent Heimnetz" -ErrorAction SilentlyContinue
$firewallHinweis = if ($null -eq $firewallRegel) {
    "`n`nWichtig: Führe einmal 'Steuer-Assistent-Heimnetz-Firewall-einrichten.cmd' aus und bestätige die Windows-Administratorabfrage."
} else { "" }

if (-not $KeinBrowser) {
    [System.Windows.MessageBox]::Show(
        "Der Steuer-Assistent läuft jetzt passwortgeschützt im Heimnetz.`n`nAdresse: $url`n`nMelde dich mit deinem eingerichteten Konto an. Keine Portfreigabe im Router einrichten.$firewallHinweis",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    Start-Process "http://127.0.0.1:8765/"
}
