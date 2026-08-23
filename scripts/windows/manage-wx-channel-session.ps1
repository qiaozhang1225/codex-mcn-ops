param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Open", "Renew", "Status", "Close", "Recover", "Refresh")]
    [string]$Action,

    [string]$SessionId = "",
    [long]$ExpectedGeneration = -1,
    [string]$Reason = "operator_request"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "wx-channel-session-common.ps1")

function Read-WxStdinPayload {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "JSON payload is required on stdin"
    }
    try {
        return $raw | ConvertFrom-Json
    } catch {
        throw "stdin payload is not valid JSON"
    }
}

function Assert-WxSessionArgument {
    if ($SessionId -notmatch '^[A-Za-z0-9_-]{8,120}$') {
        throw "SessionId must be 8-120 safe characters"
    }
}

function Assert-WxGenerationArgument {
    if ($ExpectedGeneration -lt 1) {
        throw "ExpectedGeneration must be positive"
    }
}

function Assert-WxTaskId {
    param([Parameter(Mandatory = $true)][string]$TaskId)

    if ($TaskId -notmatch '^[A-Za-z0-9_-]{8,120}$') {
        throw "task_id must be 8-120 safe characters"
    }
}

function Assert-WxReason {
    if ($Reason -notmatch '^[A-Za-z0-9_.:-]{1,120}$') {
        throw "Reason must be 1-120 safe characters"
    }
}

function New-WxLeaseRecord {
    param(
        [Parameter(Mandatory = $true)][string]$TaskId,
        [Parameter(Mandatory = $true)][long]$Generation,
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][DateTimeOffset]$ExpiresAt
    )

    $now = [DateTimeOffset]::UtcNow.ToString("o")
    return [ordered]@{
        schema_version = 1
        session_id = $SessionId
        task_id = $TaskId
        generation = $Generation
        state = $State
        expires_at = $ExpiresAt.ToString("o")
        renewed_at = $now
        closed_at = $null
        cleanup_reason = $null
    }
}

function Assert-WxBootstrapReady {
    foreach ($taskName in @(
        $script:WxWorkerTaskName,
        $script:WxInteractiveCleanupTaskName,
        $script:WxRefreshTaskName,
        $script:WxWatchdogTaskName
    )) {
        if (!(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
            throw "required scheduled task is missing: $taskName; run bootstrap first"
        }
    }
}

function Start-WxPinnedWorkerTask {
    $workerTask = Get-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue
    if ($workerTask -and [string]$workerTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName $script:WxWorkerTaskName -ErrorAction SilentlyContinue
    }
    & schtasks.exe /Run /TN $script:WxWorkerTaskName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to dispatch the pinned Channels worker task"
    }
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 500
        $startingLease = Read-WxLease
        $startingStatus = Get-WxSanitizedStatus -Lease $startingLease
        if (
            [int]$startingStatus.worker_process_count -eq 1 -and
            [int]$startingStatus.current_user_certificate_count -eq 1 -and
            [int]$startingStatus.listener_count -gt 0
        ) {
            return
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "pinned Channels worker did not start"
}

function Set-WxDegradedIfCurrent {
    param(
        [Parameter(Mandatory = $true)][long]$Generation,
        [Parameter(Mandatory = $true)][string]$ErrorMessage
    )

    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        $current = Read-WxLease
        if (
            $null -ne $current -and
            [string]$current.session_id -ceq $SessionId -and
            [long]$current.generation -eq $Generation -and
            [string]$current.state -notin @("cleaned", "expired")
        ) {
            $degraded = [ordered]@{
                schema_version = 1
                session_id = [string]$current.session_id
                task_id = [string]$current.task_id
                generation = [long]$current.generation
                state = "degraded"
                expires_at = [string]$current.expires_at
                renewed_at = [string]$current.renewed_at
                closed_at = $null
                cleanup_reason = $null
                last_error = $ErrorMessage
            }
            Write-WxAtomicJson -Path $script:WxLeasePath -Value $degraded
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }
}

function Invoke-WxOpen {
    Assert-WxSessionArgument
    $payload = Read-WxStdinPayload
    $taskId = [string]$payload.task_id
    Assert-WxTaskId -TaskId $taskId
    $expiresAt = Get-WxLeaseWindow -Payload $payload
    Assert-WxHubUrl -HubUrl ([string]$payload.hub_url)
    Assert-WxSecretValue -Label "cloud_secret" -Value ([string]$payload.cloud_secret)
    Assert-WxSecretValue -Label "secret_token" -Value ([string]$payload.secret_token)
    $lease = $null
    $reused = $null
    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        Assert-WxBootstrapReady
        $existing = Read-WxLease
        if ($null -ne $existing -and [string]$existing.state -notin @("cleaned", "expired")) {
            if (!(Test-WxLeaseExpired -Lease $existing)) {
                if ([string]$existing.session_id -ceq $SessionId -and [string]$existing.task_id -ceq $taskId) {
                    if ([string]$existing.state -in @("cleanup_pending", "cleanup_failed")) {
                        throw "cleanup_required: existing Channels session is not reusable"
                    }
                    $existingStatus = Get-WxSanitizedStatus -Lease $existing
                    if (
                        [string]$existing.state -ne "active" -or
                        [int]$existingStatus.current_user_certificate_count -ne 1 -or
                        [int]$existingStatus.local_machine_certificate_count -ne 0 -or
                        [int]$existingStatus.worker_process_count -ne 1
                    ) {
                        throw "recover_required: existing Channels session is not healthy"
                    }
                    $reused = [ordered]@{
                        ok = $true
                        action = "open"
                        reused = $true
                        status = $existingStatus
                    }
                } else {
                    throw "session_busy: another unexpired Channels session owns the worker"
                }
            } else {
                $expiredCleanup = Invoke-WxPinnedCleanup -Lease $existing -Reason "stale_lease_before_open" -TerminalState "expired"
                if (!$expiredCleanup.ok) {
                    throw "failed to clean expired Channels session before open"
                }
            }
        }
        if ($null -eq $reused) {
            $lease = New-WxLeaseRecord -TaskId $taskId -Generation 1 -State "provisioning" -ExpiresAt $expiresAt
            Write-WxAtomicJson -Path $script:WxLeasePath -Value $lease
            try {
                # Root-store installation must run in the interactive qiaoz
                # session. SSH is non-interactive and Windows rejects the
                # protected CurrentUser Root write with ERROR_NOT_SUPPORTED.
                Assert-WxPinnedArtifacts
                Write-WxWorkerConfig -Payload $payload
            } catch {
                $lease.state = "degraded"
                $lease["last_error"] = [string]$_.Exception.Message
                Write-WxAtomicJson -Path $script:WxLeasePath -Value $lease
                throw
            }
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }
    if ($null -ne $reused) {
        return $reused
    }

    try {
        # The worker Scheduled Task briefly takes the same mutex while it
        # validates the provisioning lease. Do not hold the mutex while waiting
        # for the interactive worker process to appear.
        Start-WxPinnedWorkerTask
    } catch {
        Set-WxDegradedIfCurrent -Generation 1 -ErrorMessage ([string]$_.Exception.Message)
        throw
    }

    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        $current = Read-WxLease
        Assert-WxSessionIdentity -Lease $current -SessionId $SessionId -ExpectedGeneration 1
        if ([string]$current.state -ne "provisioning") {
            throw "Channels session changed state while worker was starting"
        }
        $current.state = "active"
        $current.renewed_at = [DateTimeOffset]::UtcNow.ToString("o")
        Write-WxAtomicJson -Path $script:WxLeasePath -Value $current
        return [ordered]@{
            ok = $true
            action = "open"
            reused = $false
            status = Get-WxSanitizedStatus -Lease $current
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }
}

function Invoke-WxRenew {
    Assert-WxSessionArgument
    Assert-WxGenerationArgument
    $payload = Read-WxStdinPayload
    $lease = Read-WxLease
    if ($null -eq $lease) {
        throw "Channels session lease is missing"
    }
    Assert-WxSessionIdentity -Lease $lease -SessionId $SessionId -ExpectedGeneration $ExpectedGeneration
    if (Test-WxLeaseExpired -Lease $lease) {
        $cleanup = Invoke-WxPinnedCleanup -Lease $lease -Reason "renew_after_expiry" -TerminalState "expired"
        if (!$cleanup.ok) {
            throw "expired Channels session cleanup verification failed"
        }
        throw "Channels session lease already expired"
    }
    if ([string]$lease.state -notin @("active", "degraded")) {
        throw "Channels session is not renewable from state $($lease.state)"
    }
    Assert-WxPinnedArtifacts
    $counts = Get-WxCertificateCounts
    if ([int]$counts.current_user -ne 1 -or [int]$counts.local_machine -ne 0) {
        throw "Channels session certificate state is not healthy; recover is required"
    }
    if ((Get-WxPinnedWorkerProcesses).Count -ne 1) {
        throw "Channels worker state is not healthy; recover is required"
    }
    $expiresAt = Get-WxLeaseWindow -Payload $payload
    $renewed = New-WxLeaseRecord `
        -TaskId ([string]$lease.task_id) `
        -Generation ($ExpectedGeneration + 1) `
        -State "active" `
        -ExpiresAt $expiresAt
    Write-WxAtomicJson -Path $script:WxLeasePath -Value $renewed
    return [ordered]@{
        ok = $true
        action = "renew"
        status = Get-WxSanitizedStatus -Lease $renewed
    }
}

function Invoke-WxStatus {
    $lease = Read-WxLease
    if ($SessionId) {
        Assert-WxSessionArgument
        Assert-WxGenerationArgument
        if ($null -eq $lease) {
            throw "Channels session lease is missing"
        }
        Assert-WxSessionIdentity -Lease $lease -SessionId $SessionId -ExpectedGeneration $ExpectedGeneration
    }
    return [ordered]@{
        ok = $true
        action = "status"
        status = Get-WxSanitizedStatus -Lease $lease
    }
}

function Invoke-WxRefresh {
    Assert-WxSessionArgument
    Assert-WxGenerationArgument
    $lease = Read-WxLease
    if ($null -eq $lease) {
        throw "Channels session lease is missing"
    }
    Assert-WxSessionIdentity -Lease $lease -SessionId $SessionId -ExpectedGeneration $ExpectedGeneration
    if ([string]$lease.state -ne "active") {
        throw "Channels page refresh requires an active session"
    }
    $status = Get-WxSanitizedStatus -Lease $lease
    if (
        [int]$status.current_user_certificate_count -ne 1 -or
        [int]$status.local_machine_certificate_count -ne 0 -or
        [int]$status.worker_process_count -ne 1
    ) {
        throw "Channels page refresh requires a healthy worker session"
    }
    if (Test-Path -LiteralPath $script:WxRefreshResultPath) {
        Remove-Item -LiteralPath $script:WxRefreshResultPath -Force
    }
    & schtasks.exe /Run /TN $script:WxRefreshTaskName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "failed to dispatch the pinned WeChat Channels refresh task"
    }
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        if (Test-Path -LiteralPath $script:WxRefreshResultPath) {
            $refresh = Get-Content -LiteralPath $script:WxRefreshResultPath -Raw -Encoding utf8 | ConvertFrom-Json
            if (
                [bool]$refresh.ok -and
                [string]$refresh.session_id -ceq $SessionId -and
                [long]$refresh.generation -eq $ExpectedGeneration
            ) {
                return [ordered]@{
                    ok = $true
                    action = "refresh"
                    refreshed_at = [string]$refresh.refreshed_at
                    status = Get-WxSanitizedStatus -Lease $lease
                }
            }
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "pinned WeChat Channels refresh did not complete"
}

function Invoke-WxClose {
    Assert-WxSessionArgument
    Assert-WxGenerationArgument
    Assert-WxReason
    $lease = Read-WxLease
    if ($null -eq $lease) {
        throw "Channels session lease is missing"
    }
    Assert-WxSessionIdentity -Lease $lease -SessionId $SessionId -ExpectedGeneration $ExpectedGeneration
    if ([string]$lease.state -in @("cleaned", "expired")) {
        return [ordered]@{
            ok = $true
            action = "close"
            reused = $true
            status = Get-WxSanitizedStatus -Lease $lease
        }
    }
    $result = Invoke-WxPinnedCleanup -Lease $lease -Reason $Reason -TerminalState "cleaned"
    return [ordered]@{
        ok = [bool]$result.ok
        action = "close"
        reused = $false
        reason = [string]$result.reason
        status = $result.status
    }
}

function Invoke-WxRecover {
    Assert-WxSessionArgument
    Assert-WxGenerationArgument
    $payload = Read-WxStdinPayload
    $recovering = $null
    $nextGeneration = $ExpectedGeneration + 1
    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        $lease = Read-WxLease
        if ($null -eq $lease) {
            throw "Channels session lease is missing"
        }
        Assert-WxSessionIdentity -Lease $lease -SessionId $SessionId -ExpectedGeneration $ExpectedGeneration
        if (Test-WxLeaseExpired -Lease $lease) {
            $cleanup = Invoke-WxPinnedCleanup -Lease $lease -Reason "recover_after_expiry" -TerminalState "expired"
            if (!$cleanup.ok) {
                throw "expired Channels session cleanup verification failed"
            }
            throw "Channels session lease already expired"
        }
        if ([string]$lease.state -notin @("active", "degraded")) {
            throw "Channels session is not recoverable from state $($lease.state)"
        }
        $expiresAt = Get-WxLeaseWindow -Payload $payload
        $recovering = New-WxLeaseRecord `
            -TaskId ([string]$lease.task_id) `
            -Generation $nextGeneration `
            -State "provisioning" `
            -ExpiresAt $expiresAt
        Write-WxAtomicJson -Path $script:WxLeasePath -Value $recovering
        try {
            Assert-WxPinnedArtifacts
            Write-WxWorkerConfig -Payload $payload
        } catch {
            $recovering.state = "degraded"
            $recovering["last_error"] = [string]$_.Exception.Message
            Write-WxAtomicJson -Path $script:WxLeasePath -Value $recovering
            throw
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }

    try {
        Start-WxPinnedWorkerTask
    } catch {
        Set-WxDegradedIfCurrent -Generation $nextGeneration -ErrorMessage ([string]$_.Exception.Message)
        throw
    }

    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        $current = Read-WxLease
        Assert-WxSessionIdentity `
            -Lease $current `
            -SessionId $SessionId `
            -ExpectedGeneration $nextGeneration
        if ([string]$current.state -ne "provisioning") {
            throw "Channels session changed state while worker was recovering"
        }
        $current.state = "active"
        $current.renewed_at = [DateTimeOffset]::UtcNow.ToString("o")
        Write-WxAtomicJson -Path $script:WxLeasePath -Value $current
        return [ordered]@{
            ok = $true
            action = "recover"
            status = Get-WxSanitizedStatus -Lease $current
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }
}

$result = $null
if ($Action -in @("Open", "Recover")) {
    $result = if ($Action -eq "Open") { Invoke-WxOpen } else { Invoke-WxRecover }
} else {
    $mutex = $null
    try {
        $mutex = Enter-WxSessionMutex
        $result = switch ($Action) {
            "Renew" { Invoke-WxRenew }
            "Status" { Invoke-WxStatus }
            "Close" { Invoke-WxClose }
            "Refresh" { Invoke-WxRefresh }
        }
    } finally {
        Exit-WxSessionMutex -Mutex $mutex
    }
}
$result | ConvertTo-Json -Depth 8
if ($result.ok -eq $false) {
    exit 1
}
