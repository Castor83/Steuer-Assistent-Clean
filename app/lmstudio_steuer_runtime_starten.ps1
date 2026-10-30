param(
    [ValidateSet("Q5_K_M", "Q4_K_M")]
    [string]$Quantisierung,
    [int]$Port = 1235,
    [int]$Kontext = 32768,
    [switch]$Stoppen
)

$ErrorActionPreference = "Stop"
$quantisierungWurdeAngegeben = $PSBoundParameters.ContainsKey("Quantisierung")
if (-not $Quantisierung) {
    $Quantisierung = "Q5_K_M"
}
. (Join-Path $PSScriptRoot "lokale_laufzeitpfade.ps1")
$pfade = Get-SteuerAssistentLaufzeitPfade -Quantisierung $Quantisierung
$projekt = $pfade.Projekt
$modell = $pfade.ChatModell
$server = $pfade.Server

if ($Stoppen) {
    $vorhanden = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
    if (-not $vorhanden) { exit 0 }
    $stopModelle = @($modell)
    if (-not $quantisierungWurdeAngegeben) {
        $stopModelle = @(
            (Get-SteuerAssistentLaufzeitPfade -Quantisierung Q5_K_M).ChatModell,
            (Get-SteuerAssistentLaufzeitPfade -Quantisierung Q4_K_M).ChatModell
        )
    }
    $gestoppt = $false
    $profilFehler = @()
    foreach ($stopModell in $stopModelle) {
        try {
            Stop-SteuerAssistentRuntimeProfil `
                -Profil Chat -Port $Port -Server $server -Modell $stopModell
            $gestoppt = $true
            break
        }
        catch {
            $profilFehler += $_.Exception.Message
        }
    }
    if (-not $gestoppt) {
        throw "Port $Port gehoert zu keinem erlaubten Chatprofil: $($profilFehler -join ' | ')"
    }
    Write-Host "Chat-Runtime kontrolliert fuer den Vision-Peak entladen."
    exit 0
}

if (-not (Test-Path -LiteralPath $modell -PathType Leaf)) {
    throw "Das projektlokale Modell fehlt: $modell"
}
if (-not (Test-Path -LiteralPath $server -PathType Leaf)) {
    throw "Die projektlokale CUDA-Runtime ist unvollständig: $server"
}

$vorhanden = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
if ($vorhanden) {
    try {
        $null = Assert-SteuerAssistentRuntimeProfil `
            -Profil Chat -Port $Port -Server $server -Modell $modell -Kontext $Kontext
    }
    catch {
        throw "Port $Port läuft nicht mit dem erwarteten Steuer-Runtime-Profil: $($_.Exception.Message)"
    }
    Write-Host "Steuer-Runtime läuft bereits auf http://127.0.0.1:$Port"
    exit 0
}

$logOrdner = Join-Path $projekt "logs"
New-Item -ItemType Directory -Force -Path $logOrdner | Out-Null
$stdout = Join-Path $logOrdner "lmstudio_${Quantisierung}_server.stdout.log"
$stderr = Join-Path $logOrdner "lmstudio_${Quantisierung}_server.stderr.log"
$argumente = @(
    "-m", $modell,
    "-c", "$Kontext",
    "-np", "1",
    "-ngl", "all",
    "--flash-attn", "on",
    "--reasoning", "off",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--no-webui"
)

$prozess = Start-Process -FilePath $server -ArgumentList $argumente `
    -WorkingDirectory $projekt -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    $null = Wait-SteuerAssistentRuntimeProfil `
        -Profil Chat `
        -Port $Port `
        -Server $server `
        -Modell $modell `
        -Kontext $Kontext `
        -ErwarteterProzess $prozess `
        -Versuche 60
}
catch {
    $profilFehler = $_.Exception.Message
    $cleanupFehler = $null
    try {
        Stop-SteuerAssistentGestartetenProzess -Prozess $prozess -Port $Port
    }
    catch {
        $cleanupFehler = $_.Exception.Message
    }
    $details = if (Test-Path -LiteralPath $stderr) {
        (Get-Content -LiteralPath $stderr -Tail 20) -join "`n"
    } else {
        "Kein Fehlerprotokoll vorhanden."
    }
    $cleanupHinweis = if ($cleanupFehler) { "`nFehlstart-Cleanup nicht abgeschlossen: $cleanupFehler" } else { "" }
    throw "Die Steuer-Runtime wurde nicht mit dem erwarteten Profil bereit: $profilFehler$cleanupHinweis`n$details"
}

Write-Host "Steuer-Runtime bereit."
Write-Host "Modell: steuer-assistent-pilot13-$Quantisierung"
Write-Host "API: http://127.0.0.1:$Port/v1"
Write-Host "Kontext: $Kontext | parallele Slots: 1 | GPU-Layer: alle"
