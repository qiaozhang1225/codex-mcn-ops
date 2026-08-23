$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

$mutex = $null
try {
    $mutex = Enter-WxSessionMutex
    $lease = Read-WxLease
    if ($null -eq $lease) {
        [ordered]@{
            ok = $true
            action = "watchdog"
            decision = "no_session"
            checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        } | ConvertTo-Json -Depth 5
        exit 0
    }
    if ([string]$lease.state -in @("cleaned", "expired")) {
        [ordered]@{
            ok = $true
            action = "watchdog"
            decision = "terminal_session"
            status = Get-WxSanitizedStatus -Lease $lease
        } | ConvertTo-Json -Depth 8
        exit 0
    }
    if (!(Test-WxLeaseExpired -Lease $lease)) {
        [ordered]@{
            ok = $true
            action = "watchdog"
            decision = "lease_valid"
            status = Get-WxSanitizedStatus -Lease $lease
        } | ConvertTo-Json -Depth 8
        exit 0
    }

    # The lease is read again only after this process owns the global mutex.
    # A concurrent renewal therefore either wins before this check or observes
    # the terminal generation after cleanup; an old watchdog cannot close a
    # newly renewed or replacement session.
    $result = Invoke-WxPinnedCleanup `
        -Lease $lease `
        -Reason "lease_timeout" `
        -TerminalState "expired"
    $output = [ordered]@{
        ok = [bool]$result.ok
        action = "watchdog"
        decision = "expired_cleanup"
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
