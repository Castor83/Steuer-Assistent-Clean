$ErrorActionPreference = "Stop"
$protokoll = Join-Path (Split-Path -Parent $PSScriptRoot) "logs\vision_port_freigabe.log"
New-Item -ItemType Directory -Path (Split-Path -Parent $protokoll) -Force | Out-Null
Start-Transcript -Path $protokoll -Force | Out-Null

$urspruenglichAktiv = @{}
try {
    foreach ($dienstname in @("winnat", "hns")) {
        $dienst = Get-Service -Name $dienstname -ErrorAction Stop
        $urspruenglichAktiv[$dienstname] = $dienst.Status -eq "Running"
        if ($dienst.Status -eq "Running") {
            Stop-Service -Name $dienstname -Force -ErrorAction Stop
            (Get-Service -Name $dienstname).WaitForStatus(
                "Stopped", [TimeSpan]::FromSeconds(30)
            )
        }
    }

    foreach ($familie in @("ipv4", "ipv6")) {
        & netsh interface $familie set dynamicportrange `
            protocol=tcp startport=49152 numberofports=16384
        if ($LASTEXITCODE -ne 0) {
            throw "Der dynamische $familie-TCP-Bereich konnte nicht korrigiert werden."
        }
        $ausgabe = & netsh interface $familie show excludedportrange protocol=tcp
        if ($ausgabe -match "(?m)^\s*1237\s+1336\s*$") {
            & netsh interface $familie delete excludedportrange `
                protocol=tcp startport=1237 numberofports=100
            if ($LASTEXITCODE -ne 0) {
                throw "Die $familie-Reservierung 1237-1336 konnte nicht entfernt werden."
            }
        }
    }
    Write-Host "Der dynamische TCP-Bereich wurde auf 49152-65535 korrigiert."
}
finally {
    foreach ($dienstname in @("hns", "winnat")) {
        if ($urspruenglichAktiv[$dienstname]) {
            Start-Service -Name $dienstname -ErrorAction Continue
        }
    }
    Stop-Transcript | Out-Null
}

Start-Sleep -Seconds 2
foreach ($familie in @("ipv4", "ipv6")) {
    $kontrolle = & netsh interface $familie show excludedportrange protocol=tcp
    if ($kontrolle -match "(?m)^\s*1237\s+1336\s*$") {
        throw "HNS hat die $familie-Reservierung 1237-1336 erneut angelegt."
    }
}
Write-Host "TCP-Port 1237 ist fuer IPv4 und IPv6 dauerhaft freigegeben."
