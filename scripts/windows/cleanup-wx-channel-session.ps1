param(
    [Parameter(Mandatory = $true)][string]$SessionId,
    [Parameter(Mandatory = $true)][long]$ExpectedGeneration,
    [string]$Reason = "operator_request",
    [ValidateSet("cleaned", "expired")][string]$TerminalState = "cleaned"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

if ($SessionId -notmatch '^[A-Za-z0-9_-]{8,120}$') {
    throw "SessionId must be 8-120 safe characters"
}
if ($ExpectedGeneration -lt 1) {
    throw "ExpectedGeneration must be positive"
}
if ($Reason -notmatch '^[A-Za-z0-9_.:-]{1,120}$') {
    throw "Reason must be 1-120 safe characters"
}

$mutex = $null
try {
    $mutex = Enter-WxSessionMutex
    $lease = Read-WxLease
    if ($null -eq $lease) {
        throw "Channels session lease is missing"
    }
    Assert-WxSessionIdentity `
        -Lease $lease `
        -SessionId $SessionId `
        -ExpectedGeneration $ExpectedGeneration
    if ([string]$lease.state -in @("cleaned", "expired")) {
        [ordered]@{
            ok = $true
            action = "cleanup"
            reused = $true
            reason = $Reason
            status = Get-WxSanitizedStatus -Lease $lease
        } | ConvertTo-Json -Depth 8
        exit 0
    }
    $result = Invoke-WxPinnedCleanup -Lease $lease -Reason $Reason -TerminalState $TerminalState
    $output = [ordered]@{
        ok = [bool]$result.ok
        action = "cleanup"
        reused = $false
        reason = [string]$result.reason
        status = $result.status
    }
    $output | ConvertTo-Json -Depth 8
    if (!$result.ok) {
        exit 1
    }
} finally {
    Exit-WxSessionMutex -Mutex $mutex
}
