$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

$consoleLog = Join-Path $script:WxWorkDir "worker-console.log"
$mutex = $null
try {
    $mutex = Enter-WxSessionMutex
    $lease = Read-WxLease
    if ($null -eq $lease) {
        throw "Channels worker cannot start without a lease"
    }
    if ([string]$lease.state -notin @("provisioning", "active")) {
        throw "Channels worker cannot start from lease state $($lease.state)"
    }
    if (Test-WxLeaseExpired -Lease $lease) {
        throw "Channels worker cannot start with an expired lease"
    }
    Assert-WxPinnedArtifacts
    $certificateCounts = Get-WxCertificateCounts
    if ([int]$certificateCounts.current_user -ne 1 -or [int]$certificateCounts.local_machine -ne 0) {
        throw "Channels worker cannot start without the isolated CurrentUser certificate"
    }
    if (!(Test-Path -LiteralPath $script:WxConfigPath)) {
        throw "Channels worker config is missing"
    }
    foreach ($process in (Get-WxPinnedWorkerProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }
    New-Item -ItemType Directory -Path (Join-Path $script:WxWorkDir "logs") -Force | Out-Null
    Set-Content -LiteralPath $consoleLog -Value "" -Encoding utf8
    Set-Content -LiteralPath (Join-Path $script:WxWorkDir "logs\wx_channel.log") -Value "" -Encoding utf8
} finally {
    Exit-WxSessionMutex -Mutex $mutex
}

Set-Location $script:WxWorkDir
"[$(Get-Date -Format o)] hardened worker starting" | Add-Content -LiteralPath $consoleLog -Encoding utf8
& $script:WxWorkerPath *>> $consoleLog
"[$(Get-Date -Format o)] worker exited with code $LASTEXITCODE" | Add-Content -LiteralPath $consoleLog -Encoding utf8
