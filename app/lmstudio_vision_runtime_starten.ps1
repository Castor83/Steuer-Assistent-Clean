param(
    [int]$Port = 1237,
    [int]$Kontext = 8192,
    [switch]$Stoppen
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lokale_laufzeitpfade.ps1")
$pfade = Get-SteuerAssistentLaufzeitPfade -Quantisierung Q5_K_M
$projekt = $pfade.Projekt
$modell = $pfade.VisionModell
$projektor = $pfade.VisionProjektor
$server = $pfade.Server

if ($Stoppen) {
    $listener = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
    if (-not $listener) { exit 0 }
    Stop-SteuerAssistentRuntimeProfil `
        -Profil Vision -Port $Port -Server $server -Modell $modell -Projektor $projektor
    Write-Host "Vision-Runtime kontrolliert entladen."
    exit 0
}

if (-not $server -or -not (Test-Path -LiteralPath $server -PathType Leaf)) {
    throw "Die projektlokale CUDA-Runtime ist unvollständig: $server"
}

foreach ($datei in @($modell, $projektor)) {
    if (-not (Test-Path -LiteralPath $datei -PathType Leaf)) {
        throw "Vision-Komponente fehlt: $datei"
    }
}
$listener = Get-SteuerAssistentListenerProzess -Port $Port -FehlendErlaubt
if ($listener) {
    try {
        $null = Assert-SteuerAssistentRuntimeProfil `
            -Profil Vision `
            -Port $Port `
            -Server $server `
            -Modell $modell `
            -Kontext $Kontext `
            -Projektor $projektor
    }
    catch {
        throw "Port $Port laeuft nicht mit dem erwarteten Vision-Profil: $($_.Exception.Message)"
    }
    Write-Host "Vision-Runtime laeuft bereits auf http://127.0.0.1:$Port"
    exit 0
}

$logOrdner = Join-Path $projekt "logs"
New-Item -ItemType Directory -Path $logOrdner -Force | Out-Null
$stdout = Join-Path $logOrdner "lmstudio_vision_server.stdout.log"
$stderr = Join-Path $logOrdner "lmstudio_vision_server.stderr.log"
$argumente = @(
    "-m", $modell, "--mmproj", $projektor,
    "-c", "$Kontext", "-np", "1", "-ngl", "all",
    "--flash-attn", "on", "--reasoning-budget", "0",
    "--host", "127.0.0.1", "--port", "$Port", "--no-webui"
)
$prozess = Start-Process -FilePath $server -ArgumentList $argumente -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    $null = Wait-SteuerAssistentRuntimeProfil `
        -Profil Vision `
        -Port $Port `
        -Server $server `
        -Modell $modell `
        -Kontext $Kontext `
        -Projektor $projektor `
        -ErwarteterProzess $prozess `
        -Versuche 180
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
    throw "Vision-Runtime wurde nicht mit dem erwarteten Profil bereit: $profilFehler$cleanupHinweis`n$details"
}
Write-Host "Vision-Runtime bereit: Qwen3.5 9B Q5_K_M, Port $Port"
