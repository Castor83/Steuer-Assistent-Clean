param(
    [int]$Port = 1236,
    [int]$Kontext = 8192,
    [switch]$Stoppen
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lokale_laufzeitpfade.ps1")
$pfade = Get-SteuerAssistentLaufzeitPfade -Quantisierung Q5_K_M
$projekt = $pfade.Projekt
$modell = $pfade.EmbeddingModell
$server = $pfade.Server

if ($Stoppen) {
    $listener = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
    if (-not $listener) { exit 0 }
    Stop-SteuerAssistentRuntimeProfil `
        -Profil Embedding -Port $Port -Server $server -Modell $modell
    Write-Host "Embedding-Runtime wurde fuer den Vision-Peak entladen."
    exit 0
}

if (-not (Test-Path -LiteralPath $modell -PathType Leaf)) {
    throw "Embedding-GGUF fehlt: $modell"
}
if (-not $server -or -not (Test-Path -LiteralPath $server -PathType Leaf)) {
    throw "Die projektlokale CUDA-Runtime ist unvollständig: $server"
}

$listener = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
if ($listener) {
    try {
        $null = Assert-SteuerAssistentRuntimeProfil `
            -Profil Embedding -Port $Port -Server $server -Modell $modell -Kontext $Kontext
    }
    catch {
        throw "Port $Port laeuft nicht mit dem erwarteten Embedding-Profil: $($_.Exception.Message)"
    }
    Write-Host "Embedding-Runtime laeuft bereits auf http://127.0.0.1:$Port"
    exit 0
}

$logOrdner = Join-Path $projekt "logs"
New-Item -ItemType Directory -Path $logOrdner -Force | Out-Null
$stdout = Join-Path $logOrdner "lmstudio_embedding_server.stdout.log"
$stderr = Join-Path $logOrdner "lmstudio_embedding_server.stderr.log"
$argumente = @(
    "-m", $modell,
    "-c", "$Kontext",
    "-np", "1",
    "-ngl", "all",
    "--flash-attn", "on",
    "--embedding",
    "--pooling", "last",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--no-webui"
)
$prozess = Start-Process -FilePath $server -ArgumentList $argumente -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    $null = Wait-SteuerAssistentRuntimeProfil `
        -Profil Embedding `
        -Port $Port `
        -Server $server `
        -Modell $modell `
        -Kontext $Kontext `
        -ErwarteterProzess $prozess `
        -Versuche 120
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
    throw "Embedding-Runtime wurde nicht mit dem erwarteten Profil bereit: $profilFehler$cleanupHinweis`n$details"
}
Write-Host "Embedding-Runtime bereit: Qwen3 4B Q4_K_M, 8k, Port $Port"
