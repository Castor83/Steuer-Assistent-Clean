$identitaet = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identitaet)
$istAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $istAdministrator) {
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"' + $PSCommandPath + '"')
    )
    exit
}

Add-Type -AssemblyName PresentationFramework
$projekt = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projekt ".venv\Scripts\python.exe"
$regelname = "Steuer-Assistent Heimnetz"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    [System.Windows.MessageBox]::Show(
        "Die Python-Umgebung des Steuer-Assistenten wurde nicht gefunden.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}

try {
    $vorhanden = Get-NetFirewallRule -DisplayName $regelname -ErrorAction SilentlyContinue
    if ($null -eq $vorhanden) {
        New-NetFirewallRule `
            -DisplayName $regelname `
            -Description "Erlaubt den geschützten Steuer-Assistenten nur im privaten lokalen Subnetz." `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 8765 `
            -Profile Private `
            -RemoteAddress LocalSubnet `
            -Program $python | Out-Null
    }
    [System.Windows.MessageBox]::Show(
        "Die Heimnetz-Freigabe ist eingerichtet.`n`nErlaubt: privates Netzwerk, lokales Subnetz, TCP-Port 8765 und nur der Steuer-Assistent.",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
}
catch {
    [System.Windows.MessageBox]::Show(
        "Die Firewallfreigabe konnte nicht eingerichtet werden: $($_.Exception.Message)",
        "Steuer-Assistent Heimnetz"
    ) | Out-Null
    exit 1
}
