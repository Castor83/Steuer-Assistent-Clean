function Get-SteuerAssistentLaufzeitPfade {
    param(
        [ValidateSet("Q5_K_M", "Q4_K_M")]
        [string]$Quantisierung = "Q5_K_M"
    )

    $projektEintrag = Get-Item -LiteralPath (Split-Path -Parent $PSScriptRoot) -Force
    if ($projektEintrag.LinkType -and $projektEintrag.Target) {
        $ziel = @($projektEintrag.Target)[0]
        if (-not [IO.Path]::IsPathRooted($ziel)) {
            $ziel = Join-Path (Split-Path -Parent $projektEintrag.FullName) $ziel
        }
        $projekt = (Resolve-Path -LiteralPath $ziel).Path
    }
    else {
        $projekt = $projektEintrag.FullName
    }
    $modellOrdner = Join-Path $projekt "models"
    $backendOrdner = Join-Path $projekt "runtime\llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.55.0"

    [pscustomobject]@{
        Projekt = $projekt
        ChatModell = Join-Path $modellOrdner "steuer-assistent-pilot13-$Quantisierung.gguf"
        VisionModell = Join-Path $modellOrdner "steuer-assistent-pilot13-Q5_K_M.gguf"
        VisionProjektor = Join-Path $modellOrdner "steuer-assistent-pilot13-mmproj-BF16.gguf"
        EmbeddingModell = Join-Path $modellOrdner "qwen3-embedding-4b.gguf"
        Server = Join-Path $backendOrdner "llama-server.exe"
    }
}

function Test-SteuerAssistentPfadGleich {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Tatsaechlich,
        [Parameter(Mandatory = $true)]
        [string]$Erwartet
    )

    $tatsaechlicherVollpfad = [IO.Path]::GetFullPath($Tatsaechlich)
    $erwarteterVollpfad = [IO.Path]::GetFullPath($Erwartet)
    return [StringComparer]::OrdinalIgnoreCase.Equals($tatsaechlicherVollpfad, $erwarteterVollpfad)
}

function Test-SteuerAssistentBefehlszeilenWert {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Befehlszeile,
        [Parameter(Mandatory = $true)]
        [string[]]$Option,
        [Parameter(Mandatory = $true)]
        [string]$Wert
    )

    $optionMuster = '(?:' + (($Option | ForEach-Object { [Regex]::Escape($_) }) -join '|') + ')'
    $muster = '(?i)(?<!\S)' + $optionMuster + '(?:\s+|=)(?:"(?<wert>[^"]*)"|(?<wert>\S+))(?=\s|$)'
    $treffer = [Regex]::Matches($Befehlszeile, $muster)
    if ($treffer.Count -ne 1) { return $false }
    return [StringComparer]::OrdinalIgnoreCase.Equals($treffer[0].Groups["wert"].Value, $Wert)
}

function Test-SteuerAssistentBefehlszeilenSchalter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Befehlszeile,
        [Parameter(Mandatory = $true)]
        [string[]]$Schalter
    )

    $schalterMuster = '(?:' + (($Schalter | ForEach-Object { [Regex]::Escape($_) }) -join '|') + ')'
    $muster = '(?i)(?<!\S)' + $schalterMuster + '(?=\s|$)'
    return [Regex]::IsMatch($Befehlszeile, $muster)
}

function Test-SteuerAssistentBefehlszeilenProfil {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Chat", "Embedding", "Vision")]
        [string]$Profil,
        [Parameter(Mandatory = $true)]
        [string]$Befehlszeile,
        [Parameter(Mandatory = $true)]
        [string]$Modell,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [AllowEmptyString()]
        [string]$Projektor = ""
    )

    if (-not (Test-SteuerAssistentBefehlszeilenWert -Befehlszeile $Befehlszeile -Option @("-m", "--model") -Wert $Modell)) { return $false }
    if (-not (Test-SteuerAssistentBefehlszeilenWert -Befehlszeile $Befehlszeile -Option @("-np", "--parallel") -Wert "1")) { return $false }
    if (-not (Test-SteuerAssistentBefehlszeilenWert $Befehlszeile "--host" "127.0.0.1")) { return $false }
    if (-not (Test-SteuerAssistentBefehlszeilenWert $Befehlszeile "--port" "$Port")) { return $false }

    $istEmbedding = Test-SteuerAssistentBefehlszeilenSchalter -Befehlszeile $Befehlszeile -Schalter @("--embedding", "--embeddings")
    $hatProjektor = Test-SteuerAssistentBefehlszeilenSchalter -Befehlszeile $Befehlszeile -Schalter @("-mm", "--mmproj")

    switch ($Profil) {
        "Chat" {
            return (-not $istEmbedding -and -not $hatProjektor)
        }
        "Embedding" {
            return ($istEmbedding -and -not $hatProjektor)
        }
        "Vision" {
            if (-not $Projektor) { return $false }
            return (
                -not $istEmbedding -and
                $hatProjektor -and
                (Test-SteuerAssistentBefehlszeilenWert -Befehlszeile $Befehlszeile -Option @("-mm", "--mmproj") -Wert $Projektor)
            )
        }
    }
}

function Get-SteuerAssistentListenerProzess {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [switch]$FehlendErlaubt
    )

    $alleListener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($alleListener.Count -eq 0) {
        if ($FehlendErlaubt) { return $null }
        throw "Port $Port hat keinen Listener."
    }

    $listener = @($alleListener | Where-Object { $_.LocalAddress -eq "127.0.0.1" })
    if ($listener.Count -ne 1) {
        throw "Port $Port hat kein eindeutiges Listenerprofil auf 127.0.0.1."
    }

    $prozessId = [int]$listener[0].OwningProcess
    $prozess = Get-CimInstance Win32_Process -Filter "ProcessId = $prozessId"
    if (-not $prozess) {
        throw "Der Listenerprozess auf Port $Port konnte nicht gelesen werden."
    }
    try {
        $stoppProzess = [Diagnostics.Process]::GetProcessById($prozessId)
        $startAbweichung = [Math]::Abs(($stoppProzess.StartTime - [datetime]$prozess.CreationDate).TotalSeconds)
    }
    catch {
        throw "Der Listenerprozess auf Port $Port konnte nicht stabil gebunden werden."
    }
    if ($startAbweichung -gt 1) {
        throw "Der Listenerprozess auf Port $Port hat waehrend der Pruefung gewechselt."
    }

    [pscustomobject]@{
        Listener = $listener[0]
        Prozess = $prozess
        ProzessId = $prozessId
        StoppProzess = $stoppProzess
    }
}

function Assert-SteuerAssistentProzessProfil {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Chat", "Embedding", "Vision")]
        [string]$Profil,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Server,
        [Parameter(Mandatory = $true)]
        [string]$Modell,
        [AllowEmptyString()]
        [string]$Projektor = "",
        [Diagnostics.Process]$ErwarteterProzess
    )

    $bindung = Get-SteuerAssistentListenerProzess -Port $Port
    if ($ErwarteterProzess) {
        if ($ErwarteterProzess.HasExited) {
            throw "Der erwartete Prozess wurde vor der Profilpruefung beendet."
        }
        if (
            $bindung.ProzessId -ne $ErwarteterProzess.Id -or
            $bindung.StoppProzess.StartTime -ne $ErwarteterProzess.StartTime
        ) {
            throw "Port $Port gehoert nicht zum zuvor gestarteten Prozess."
        }
    }
    if (-not (Test-SteuerAssistentPfadGleich $bindung.Prozess.ExecutablePath $Server)) {
        throw "Port $Port gehoert nicht zum projektlokalen Serverprogramm."
    }
    if (-not (Test-SteuerAssistentBefehlszeilenProfil `
        -Profil $Profil `
        -Befehlszeile $bindung.Prozess.CommandLine `
        -Modell $Modell `
        -Port $Port `
        -Projektor $Projektor)) {
        throw "Port $Port gehoert nicht zum erwarteten $Profil-Prozessprofil."
    }
    return $bindung
}

function Assert-SteuerAssistentRuntimeProfil {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Chat", "Embedding", "Vision")]
        [string]$Profil,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Server,
        [Parameter(Mandatory = $true)]
        [string]$Modell,
        [Parameter(Mandatory = $true)]
        [int]$Kontext,
        [AllowEmptyString()]
        [string]$Projektor = "",
        [Diagnostics.Process]$ErwarteterProzess
    )

    $bindung = Assert-SteuerAssistentProzessProfil `
        -Profil $Profil `
        -Port $Port `
        -Server $Server `
        -Modell $Modell `
        -Projektor $Projektor `
        -ErwarteterProzess $ErwarteterProzess

    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
    $eigenschaften = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/props" -TimeoutSec 2
    if ($status.status -ne "ok") {
        throw "Die Runtime auf Port $Port ist nicht bereit."
    }
    if ($eigenschaften.default_generation_settings.n_ctx -ne $Kontext) {
        throw "Die Runtime auf Port $Port verwendet nicht den Kontext $Kontext."
    }
    if ($eigenschaften.total_slots -ne 1) {
        throw "Die Runtime auf Port $Port verwendet nicht genau einen Slot."
    }
    if (-not (Test-SteuerAssistentPfadGleich $eigenschaften.model_path $Modell)) {
        throw "Die Runtime auf Port $Port verwendet nicht das erwartete Modell."
    }

    $kontrolle = Assert-SteuerAssistentProzessProfil `
        -Profil $Profil `
        -Port $Port `
        -Server $Server `
        -Modell $Modell `
        -Projektor $Projektor `
        -ErwarteterProzess $bindung.StoppProzess

    [pscustomobject]@{
        ProzessId = $kontrolle.ProzessId
        Modell = $eigenschaften.model_path
        Kontext = $eigenschaften.default_generation_settings.n_ctx
        Slots = $eigenschaften.total_slots
    }
}

function Wait-SteuerAssistentRuntimeProfil {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Chat", "Embedding", "Vision")]
        [string]$Profil,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Server,
        [Parameter(Mandatory = $true)]
        [string]$Modell,
        [Parameter(Mandatory = $true)]
        [int]$Kontext,
        [AllowEmptyString()]
        [string]$Projektor = "",
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$ErwarteterProzess,
        [int]$Versuche = 60
    )

    $letzterFehler = "Noch keine Profilantwort."
    for ($versuch = 0; $versuch -lt $Versuche; $versuch++) {
        Start-Sleep -Milliseconds 500
        if ($ErwarteterProzess.HasExited) {
            $letzterFehler = "Der gestartete Prozess wurde vor der Profilabnahme beendet."
            break
        }
        try {
            return Assert-SteuerAssistentRuntimeProfil `
                -Profil $Profil `
                -Port $Port `
                -Server $Server `
                -Modell $Modell `
                -Kontext $Kontext `
                -Projektor $Projektor `
                -ErwarteterProzess $ErwarteterProzess
        }
        catch {
            $letzterFehler = $_.Exception.Message
        }
    }
    throw "Runtime-Profil auf Port $Port wurde nicht bereit: $letzterFehler"
}

function Stop-SteuerAssistentProzessObjekt {
    param(
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$Prozess,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Beschreibung
    )

    $prozessId = $Prozess.Id
    try {
        if (-not $Prozess.HasExited) {
            $Prozess.Kill()
        }
        if (-not $Prozess.WaitForExit(10000)) {
            $stoppFehler = "Zeitlimit beim Warten auf das Prozessende."
        }
    }
    catch {
        $stoppFehler = $_.Exception.Message
    }

    for ($versuch = 0; $versuch -lt 20; $versuch++) {
        try {
            $prozessAktiv = -not $Prozess.HasExited
        }
        catch {
            $prozessAktiv = $false
        }
        $portBelegt = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if (-not $prozessAktiv -and -not $portBelegt) {
            return
        }
        Start-Sleep -Milliseconds 100
    }

    try {
        $prozessAktiv = -not $Prozess.HasExited
    }
    catch {
        $prozessAktiv = $false
    }
    if ($prozessAktiv) {
        $zusatz = if ($stoppFehler) { " Stopfehler: $stoppFehler" } else { "" }
        throw "$Beschreibung Prozess $prozessId laeuft weiter.$zusatz"
    }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port ist nach dem $Beschreibung weiterhin belegt."
    }
}

function Stop-SteuerAssistentRuntimeProfil {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Chat", "Embedding", "Vision")]
        [string]$Profil,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Server,
        [Parameter(Mandatory = $true)]
        [string]$Modell,
        [AllowEmptyString()]
        [string]$Projektor = ""
    )

    $bindung = Assert-SteuerAssistentProzessProfil `
        -Profil $Profil `
        -Port $Port `
        -Server $Server `
        -Modell $Modell `
        -Projektor $Projektor
    Stop-SteuerAssistentProzessObjekt `
        -Prozess $bindung.StoppProzess `
        -Port $Port `
        -Beschreibung "kontrollierten $Profil-Stopp"
}

function Stop-SteuerAssistentGestartetenProzess {
    param(
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$Prozess,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    Stop-SteuerAssistentProzessObjekt `
        -Prozess $Prozess `
        -Port $Port `
        -Beschreibung "Fehlstart-Cleanup"
}
